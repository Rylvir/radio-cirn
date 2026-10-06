#!/usr/bin/env python3
"""Watch Trunk Recorder and turn major incidents into dashboard alerts.

Fire channels are chosen by frequency, not by the CSV row number, so a
renumber (Air Tactics removed, Roseville added) does not mislabel them:

  151.325 NEU West, 154.355 Placer, 153.965 Nevada,
  151.190 El Dorado (AEU), 154.040 Roseville

Law dispatch is 2001 PCSO West, 2003 PCSO East, 10201 Lincoln PD,
10601 Auburn PD, from both PIRCS sites: trunk-recorder files a call under
cirn/ or cirn80/ depending on which site carried it, and about one PCSO
call in five is only on cirn80. Fire is always transcribed before law, and each pass
takes at most one law call so PCSO traffic cannot bury a fire dispatch.

Startup is quiet: recordings already on disk are seeded as seen, so a
restart does not replay history into the alert list, and anything over
STARTUP_MAX_AGE old that is still unseen (a long outage, a newly added
folder) is skipped rather than queued ahead of live calls. --backfill N
transcribes the newest N matching files anyway.

One process, one model, flock on /tmp/transcribe.lock. Alerts are written
to /home/scribe/trunk-build/incident_alerts.json for the Fire Monitor
dashboard. Transcripts also land in radio_calls.db.
"""

import argparse
import fcntl
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import notify
from incident_classify import (FIRE_HOTWORDS, LAW_HOTWORDS, classify,
                               follow_up, record_alert, strip_prompt_echo)
from radio_numbers import spoken_numbers_to_digits

FIRE_DIR = Path("/home/scribe/trunk-build/fire")
CIRN_DIRS = (Path("/home/scribe/trunk-build/cirn"),
             Path("/home/scribe/trunk-build/cirn80"))
LAW_SYSTEMS = {d.name for d in CIRN_DIRS}
# MHz -> name. Row numbers in fire.csv change; the frequency does not.
FIRE_MHZ = {
    151.325: "NEU West",
    154.355: "Placer",
    153.965: "Nevada",
    151.190: "El Dorado",
    154.040: "Roseville",
}
LAW_TG = {
    2001: "PCSO West",
    2003: "PCSO East",
    10201: "Lincoln PD",
    10601: "Auburn PD",
}
LAW_PER_PASS = 1

STATE_FILE = Path("/home/scribe/trunk-build/transcribe_state.json")
DB_FILE = Path("/home/scribe/radio-transcriber/radio_calls.db")
LOG_FILE = Path("/home/scribe/trunk-build/transcribe_alerts.log")
LOCK_FILE = "/tmp/transcribe.lock"
TRUNK_ROOT = Path("/home/scribe/trunk-build")

POLL_INTERVAL = 6
DATE_DIR_DAYS = 2
MIN_CALL_MS = 1500
MAX_CALL_MS = 180_000
STATE_CAP = 20000
STARTUP_MAX_AGE = 30 * 60
MODEL_SIZE = "medium"
INITIAL_PROMPT = "Fire and police dispatch in Placer County, California."
# Hotwords bias the decoder toward local radio vocabulary without being
# written into the transcript the way a long initial prompt often is.
# The lists live in incident_classify so the echo stripper knows them.
HOTWORDS = {"fire": FIRE_HOTWORDS, "cirn": LAW_HOTWORDS}

log = logging.getLogger("watch_transcribe")


def system_of(path: Path) -> str:
    return "cirn" if LAW_SYSTEMS & set(path.parts) else "fire"


def parse_tg(name: str):
    try:
        return int(name.split("-", 1)[0])
    except (TypeError, ValueError):
        return None


def file_mhz(name: str):
    """Radio channel in MHz from '{tg}-{epoch}_{freqHz}-call_n.wav'."""
    try:
        hz = float(name.split("_", 1)[1].split("-", 1)[0])
        return round(hz / 1_000_000, 3)
    except (IndexError, ValueError):
        return None


def channel_of(path: Path):
    """Return (system, stable_key, display_name) or None if we do not transcribe it.

    Fire is matched on frequency so fire.csv row numbers can change.
    Law is matched on the P25 talkgroup, which does not move.
    """
    if system_of(path) == "fire":
        mhz = file_mhz(path.name)
        if mhz is None:
            return None
        for freq, name in FIRE_MHZ.items():
            if abs(mhz - freq) < 0.002:
                return ("fire", int(round(freq * 1000)), name)
        return None
    tg = parse_tg(path.name)
    name = LAW_TG.get(tg)
    if not name:
        return None
    return ("cirn", tg, name)


def recent_wavs(days: int = DATE_DIR_DAYS):
    out = []
    for root in (FIRE_DIR, *CIRN_DIRS):
        if not root.exists():
            continue
        for i in range(days):
            d = datetime.now() - timedelta(days=i)
            day = root / str(d.year) / str(d.month) / str(d.day)
            if day.is_dir():
                out.extend(day.glob("*.wav"))
    return out


def mtime_or_zero(f: Path) -> float:
    """Sort key that survives a recording pruned mid-scan."""
    try:
        return f.stat().st_mtime
    except OSError:
        return 0.0


def file_is_stable(f: Path, min_age: float = 2.0) -> bool:
    try:
        return (time.time() - f.stat().st_mtime) >= min_age
    except FileNotFoundError:
        return False


def load_sidecar(wav: Path) -> dict:
    try:
        return json.loads(wav.with_suffix(".json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def load_state() -> dict:
    if STATE_FILE.exists() and STATE_FILE.stat().st_size:
        try:
            return dict.fromkeys(json.loads(STATE_FILE.read_text()))
        except json.JSONDecodeError:
            log.error("transcribe state corrupt; reseeding from disk")
    wavs = sorted(recent_wavs(), key=mtime_or_zero)
    names = [p.name for p in wavs]
    log.info("quiet start: seeding %d existing recordings, no historical alerts",
             len(names))
    return dict.fromkeys(names)


def save_state(seen: dict):
    keep = list(seen)[-STATE_CAP:]
    tmp = STATE_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w") as fh:
            json.dump(keep, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, STATE_FILE)
    except OSError as e:
        log.error("save_state failed (%s)", e)
        try:
            tmp.unlink()
        except OSError:
            pass


def init_db():
    # WAL lets the dashboard read while a transcript is being written, and
    # the long busy timeout keeps a slow reader from failing the commit
    # (a failed call is marked seen and never retried).
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute('''CREATE TABLE IF NOT EXISTS calls (
                    filename TEXT UNIQUE PRIMARY KEY,
                    talkgroup INTEGER,
                    talkgroup_name TEXT,
                    start_time TEXT,
                    epoch INTEGER,
                    frequency REAL,
                    transcription TEXT,
                    audio_url TEXT)''')
    cols = [r[1] for r in conn.execute("PRAGMA table_info(calls)")]
    if "alert_category" not in cols:
        conn.execute("ALTER TABLE calls ADD COLUMN alert_category TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_epoch ON calls(epoch)")
    conn.commit()
    return conn


def save_transcript(conn, wav: Path, tg: int, name: str, text: str, meta: dict,
                    alert_category: str = ""):
    try:
        epoch = int(float(meta.get("start_time")))
    except (TypeError, ValueError):
        epoch = 0
    if epoch <= 0:
        epoch = int(mtime_or_zero(wav)) or int(time.time())
    freq = meta.get("freq") or 0
    try:
        freq = float(freq)
    except (TypeError, ValueError):
        freq = 0
    start = datetime.fromtimestamp(epoch).isoformat(timespec="seconds")
    conn.execute(
        '''INSERT OR REPLACE INTO calls
           (filename, talkgroup, talkgroup_name, start_time, epoch, frequency,
            transcription, audio_url, alert_category)
           VALUES (?,?,?,?,?,?,?,?,?)''',
        (wav.name, tg, name, start, epoch, freq, text, None, alert_category or ""),
    )
    conn.commit()
    return start


def rel_of(wav: Path) -> str:
    try:
        rel = wav.resolve().relative_to(TRUNK_ROOT.resolve())
    except ValueError:
        return ""
    text = str(rel)
    if text.startswith("/") or ".." in text.split("/"):
        return ""
    return text


def _transcribe(model, wav: Path, vad: bool, sysname: str = "fire") -> str:
    segments, _info = model.transcribe(
        str(wav),
        beam_size=5,
        language="en",
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=INITIAL_PROMPT,
        hotwords=HOTWORDS.get(sysname, FIRE_HOTWORDS),
        vad_filter=vad,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    return " ".join(seg.text for seg in segments).strip()


def transcribe_wav(model, wav: Path, sysname: str = "fire") -> str:
    text = _transcribe(model, wav, vad=True, sysname=sysname)
    if text:
        return text
    # Silero sometimes marks an entire noisy transmission as non-speech.
    log.info("empty after VAD, retrying full audio: %s", wav.name)
    return _transcribe(model, wav, vad=False, sysname=sysname)


def consider(wav: Path, seen: dict):
    """Return 'wait' to retry later, or a terminal status after deciding."""
    channel = channel_of(wav)
    if not channel:
        return "skip"
    sysname, tg, name = channel
    if not file_is_stable(wav):
        return "wait"
    meta = load_sidecar(wav)
    if not meta:
        age = time.time() - mtime_or_zero(wav)
        if age < 30:
            return "wait"
        return "skip"
    if meta.get("encrypted"):
        return "skip"
    length = meta.get("call_length_ms")
    try:
        length = int(length) if length is not None else None
    except (TypeError, ValueError):
        length = None
    if length is not None and (length < MIN_CALL_MS or length > MAX_CALL_MS):
        return "skip"
    return "ready", sysname, tg, name, meta


def process(model, conn, wav: Path, seen: dict) -> str:
    decision = consider(wav, seen)
    if decision == "wait":
        return "wait"
    if decision == "skip":
        return "skip"
    _ready, sysname, tg, name, meta = decision
    if meta.get("talkgroup_tag") and sysname == "cirn":
        name = meta.get("talkgroup_tag") or name
    try:
        text = strip_prompt_echo(transcribe_wav(model, wav, sysname))
        # "Engine twenty-three sixty-three" -> "Engine 2363", so search and
        # unit following see the ID the way Whisper usually writes it.
        text = spoken_numbers_to_digits(text)
        hit = classify(text)
        start = save_transcript(
            conn, wav, tg, name, text, meta,
            alert_category=(hit or {}).get("category", ""),
        )
    except Exception:
        log.exception("transcribe failed: %s", wav.name)
        return "error"
    if hit:
        try:
            record = record_alert(
                hit,
                talkgroup=tg,
                talkgroup_name=name,
                system=sysname,
                when_iso=start,
                rel=rel_of(wav),
                text=text,
            )
        except Exception:
            log.exception("alert write failed: %s", wav.name)
            return "error"
        log.info("ALERT %s (%s) ← %s | %s",
                 hit["category"], hit["evidence"], wav.name, text[:140])
        notify.send(record)
        if record.get("first_confirmation"):
            notify.send_confirmation(record)
        return "alert"
    try:
        followed, confirmed = follow_up(
            talkgroup=tg, talkgroup_name=name, system=sysname,
            when_iso=start, rel=rel_of(wav), text=text,
        )
    except Exception:
        log.exception("follow-up failed: %s", wav.name)
        followed, confirmed = None, False
    if followed:
        log.info("%s %s ← %s | %s", "CONFIRMED" if confirmed else "follow-up",
                 followed.get("category"), wav.name, text[:140])
        if confirmed:
            notify.send_confirmation(followed)
        return "followup"
    log.info("routine %s %s: %s", tg, name, (text or "")[:100])
    return "routine"


def matching_newest(n: int):
    files = [wav for wav in recent_wavs() if channel_of(wav)]
    files.sort(key=mtime_or_zero, reverse=True)
    return files[:n]


def hold_lock():
    fh = open(LOCK_FILE, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error("another transcriber holds %s; exiting", LOCK_FILE)
        sys.exit(1)
    return fh


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(),
        ],
    )


def main(backfill: int = 0, once: bool = False):
    setup_logging()
    hold_lock()
    log.info("=== radio transcriber started ===")
    log.info("fire MHz: %s", sorted(FIRE_MHZ))
    log.info("law talkgroups: %s", sorted(LAW_TG))
    log.info("ntfy: %s", "on" if notify.enabled() else "off (set NTFY_URL)")
    seen = load_state()
    stale = [p for p in recent_wavs()
             if p.name not in seen and time.time() - mtime_or_zero(p) > STARTUP_MAX_AGE]
    if stale:
        log.info("quiet start: skipping %d unseen recordings older than %d min",
                 len(stale), STARTUP_MAX_AGE // 60)
        for p in sorted(stale, key=mtime_or_zero):
            seen[p.name] = None
    save_state(seen)

    need_model = backfill > 0 or not once
    model = None
    conn = None
    if need_model:
        from faster_whisper import WhisperModel
        log.info("loading faster-whisper %s (cpu, int8)", MODEL_SIZE)
        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        conn = init_db()

    if backfill > 0:
        files = list(reversed(matching_newest(backfill)))
        log.info("backfill %d matching recordings", len(files))
        for wav in files:
            seen.pop(wav.name, None)
            status = process(model, conn, wav, seen)
            if status != "wait":
                seen[wav.name] = None
                save_state(seen)
            log.info("backfill %s -> %s", wav.name, status)
        if once:
            return

    while True:
        dirty = False
        fire_q = []
        law_q = []
        for wav in recent_wavs():
            if wav.name in seen:
                continue
            if not file_is_stable(wav):
                continue
            channel = channel_of(wav)
            if not channel:
                seen[wav.name] = None
                dirty = True
                continue
            (fire_q if channel[0] == "fire" else law_q).append(wav)
        fire_q.sort(key=mtime_or_zero)
        law_q.sort(key=mtime_or_zero)
        batch = fire_q + law_q[:LAW_PER_PASS]
        for wav in batch:
            status = process(model, conn, wav, seen)
            if status == "wait":
                continue
            seen[wav.name] = None
            dirty = True
            if status in ("alert", "followup", "routine", "error"):
                save_state(seen)
                dirty = False
        if dirty:
            save_state(seen)
        if once:
            return
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Transcribe dispatch and classify alerts")
    ap.add_argument("--backfill", type=int, default=0, metavar="N",
                    help="Transcribe the newest N matching recordings on startup")
    ap.add_argument("--once", action="store_true",
                    help="One pass, then exit")
    ap.add_argument("--test-ntfy", action="store_true",
                    help="Send one sample alert to NTFY_URL, then exit")
    args = ap.parse_args()
    if args.test_ntfy:
        if not notify.enabled():
            sys.exit("NTFY_URL is not set")
        logging.basicConfig(level=logging.INFO)
        notify.send({
            "category": "motor_vehicle_accident", "label": "MVA (test)",
            "channels": ["NEU West"],
            "text": "Test from radio-transcriber. High level TC, Highway 49 at Dry Creek.",
        }, wait=True)
        print("sent test to", notify.NTFY_URL)
        sys.exit(0)
    main(backfill=args.backfill, once=args.once)
