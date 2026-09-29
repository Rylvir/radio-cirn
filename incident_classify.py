"""Classify a radio transcript as a major incident, or not.

A hit requires both an incident type and the severity bar for that type.
Routine traffic ("smoke investigation, nothing showing", a minor TC, a
small grass fire) returns None. The dashboard shows hits only.

record_alert() merges a hit into incident_alerts.json. Repeated traffic
about the same incident updates one alert instead of filling the list.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

ALERTS_PATH = Path("/home/scribe/trunk-build/incident_alerts.json")
ALERT_CAP = 200
MERGE_SAME_TG_SEC = 30 * 60
MERGE_LOCATION_SEC = 2 * 60 * 60
# Fire and law often report the same incident in different words
# ("High level TC, Highway 49" on NEU, "major vehicle accident, 49 and Dry
# Creek" on PCSO West). Same category on another channel within this window
# merges unless both name places and none of them overlap.
MERGE_CROSS_CHANNEL_SEC = 15 * 60

# id, label, detail (the severity bar), short chip for the dashboard filter.
CATEGORIES = [
    ("structure_fire", "Structure Fire",
     "Smoke Showing / Working Fire / Multiple Alarm / Defensive Operations", "Structure"),
    ("other_fire", "Other Fire",
     "Smoke Showing / Working Fire (vehicle, dumpster, pallet, unknown)", "Other fire"),
    ("brush_grass_fire", "Brush/Grass Fire",
     "Major Brush Fire", "Brush"),
    ("motor_vehicle_accident", "MVA",
     "Rollover / Extrication / Major Damage / Multiple Vehicles", "MVA"),
    ("shooting", "Shooting",
     "Shots fired", "Shooting"),
    ("firefighter_down", "Firefighter Down",
     "Mayday / Firefighter Down", "FF down"),
    ("building_collapse", "Building Collapse",
     "Structural collapse", "Collapse"),
    ("mass_casualty", "Mass Casualty",
     "MCI / multiple casualties", "MCI"),
    ("airport_alert", "Airport Alert",
     "Aircraft emergency", "Airport"),
    ("technical_rescue", "Technical Rescue",
     "Confined space / trench / high angle / swift water", "Tech rescue"),
    # Geographic watch on every transcribed fire and law channel.
    # A real major incident in town still keeps its own category.
    ("foresthill", "Foresthill",
     "Any dispatch that names Foresthill", "Foresthill"),
]

_BY_ID = {c[0]: c for c in CATEGORIES}

_NEG = re.compile(
    r"\b(no|not|n't|nothing|without|negative|cancel(?:l?ed)?|"
    r"unfounded|false alarm|disregard|unable)\b"
)

_FIREFIGHTER = re.compile(
    r"\b(firefighter down|fire fighter down|fireman down|ff down)\b"
)
# A single "mayday" is often a business name ("Mayday dealership").
# The radio distress call is repeated, or paired with a firefighter.
_MAYDAY_REPEAT = re.compile(r"\bmayday(?:\s+mayday)+\b")
_MAYDAY = re.compile(r"\bmayday\b")
_FF_WORD = re.compile(r"\b(firefighter|fire fighter|fireman)\b")
_COLLAPSE = re.compile(
    r"\b((?:building|structural|structure|roof|floor) collapse|"
    r"collapse of the (?:building|roof|structure|floor))\b"
)
_MCI = re.compile(
    r"\b(mass casualty|mass-casualty|mci|multiple (?:casualt(?:y|ies)|victims))\b"
)
_AIRPORT = re.compile(
    r"\b(airport alert|aircraft (?:down|emergency|crash)|plane crash|"
    r"downed aircraft)\b"
)
_AIRPORT_ALERT_N = re.compile(r"\balert\s*(?:2|3|ii|iii|two|three)\b")
_AIRPORT_CTX = re.compile(r"\b(airport|aircraft|airliner|runway|plane)\b")
_SHOOTING = re.compile(
    r"\b(shots? fired|gunshot|gsw|active shooter|"
    r"(?:report of |it's |it is |a )shooting|"
    r"shooting (?:in progress|at\b|incident)|"
    r"person shot|(?:has |been |was |got )shot|"
    r"shot (?:a |the )?(?:person|victim|male|female|man|woman))\b"
)
_SHOOTING_PAIN = re.compile(r"\bshooting\b(?:\s+\w+){0,2}\s+pain\b")
_TECH = re.compile(
    r"\b(technical rescue|confined space|trench rescue|trench collapse|"
    r"high angle|swift\s?water|rope rescue)\b"
)
_MVA_STRONG = re.compile(
    r"\b(roll[\s-]?over|extrication|ejected|entrapp?ed)\b"
)
_MVA_CONTEXT = re.compile(
    r"\b(traffic collision|\btc\b|vehicle accident|injury accident|"
    r"\bmva\b|\bcrash\b|\bwreck\b|11-80|1182)\b"
)
_MVA_EXTRA = re.compile(
    r"\b(major damage|multiple vehicles)\b"
)
# "Major vehicle accident", "high level TC": the dispatcher's own severity.
_MVA_MAJOR = re.compile(
    r"\b((?:major|high[\s-]level)\s+(?:\w+\s+){0,2}?"
    r"(?:accident|collision|tc|mva|crash|wreck))\b"
)
_HIGH_LEVEL = re.compile(r"\bhigh[\s-]level\b")
_CRASH_WORD = re.compile(
    r"\b(accident|collision|tc|mva|crash|wreck)\b"
)
_SEVERITY = re.compile(
    r"\b(smoke (?:is )?showing|showing smoke|working (?:a )?fire|"
    r"fully involved|flames showing|fire showing|"
    r"(?:multiple|second|third|fourth|2nd|3rd|4th|two|three|four) alarm|"
    r"defensive (?:operations|mode)|going defensive)\b"
)
_BRUSH = re.compile(
    r"\b((?:brush|grass|vegetation|wildland|timber) fire)\b"
)
_BRUSH_MAJOR = re.compile(
    r"\b(major|extended|large|campaign|evacuation|acres?|"
    r"working (?:a )?(?:brush |grass |vegetation |wildland )?fire|"
    r"fully involved)\b"
)
_OTHER_OBJECT = re.compile(
    r"\b((?:vehicle|car|truck|auto|rv|semi|dumpster|pallet|rubbish|trash|garbage) fire|"
    r"dumpster|pallet fire|rubbish fire|trash fire|"
    r"unknown (?:type )?fire|fire of unknown origin)\b"
)
# Foresthill as Whisper actually writes it in radio_calls.db: "Forest Hill",
# "Forrest Hill Road", "Forest Hills", "forest hillside" (the bridge),
# "80 West at 4th Hill" (the I-80 exit), "Poster Hills Road", "Posterhills".
_FORESTHILL = re.compile(
    r"\b(?:"
    r"forr?[ae]?st[\s-]*hill\w*"
    r"|(?:4th|fourth|forth)[\s-]*hill"
    r"|[fp]oster[\s-]*hills?"
    r")\b"
)
# A place watch ignores the wide negation window ("negative contact,
# en route to Foresthill"). Only "not Foresthill" / "no Foresthill" cancels.
_PLACE_NEG = re.compile(r"\b(?:not|no|n't)\s+$")
_STRUCTURE_OBJECT = re.compile(
    r"\b(structure fire|house fire|building fire|apartment fire|"
    r"residential fire|commercial fire|dwelling fire)\b"
)
_LOC_STREET = re.compile(
    r"\b(\d{2,5})\s+([a-z]+(?:\s+[a-z]+)?)\s+"
    r"(street|st|road|rd|avenue|ave|drive|dr|lane|ln|way|"
    r"blvd|boulevard|court|ct|circle|cir|place|pl)\b"
)
_LOC_HWY = re.compile(r"\b(?:highway|hwy|interstate)\s*(\d{1,3})\b")
_STREET_SUFFIX = {
    "st": "street", "street": "street", "rd": "road", "road": "road",
    "ave": "avenue", "avenue": "avenue", "dr": "drive", "drive": "drive",
    "ln": "lane", "lane": "lane", "way": "way", "blvd": "boulevard",
    "boulevard": "boulevard", "ct": "court", "court": "court",
    "cir": "circle", "circle": "circle", "pl": "place", "place": "place",
}


def categories_public():
    return [
        {"id": c[0], "label": c[1], "detail": c[2], "chip": c[3]}
        for c in CATEGORIES
    ]


# Whisper sometimes appends the hotword list to a real transmission.
_HOTWORD_ECHO = re.compile(
    r"\b(?:lincoln miller roseville|smoke showing working fire extrication|"
    r"battalion engine truck)\b.*$",
    re.I,
)


# Words in watch_transcribe.HOTWORDS. Whisper also echoes a partial tail of
# the list ("placer nevada el dorado miller sacramento"); now that the list
# ends in "foresthill", such an echo would raise a false Foresthill alert.
_HOTWORD_WORDS = frozenset(
    "battalion engine truck auburn lincoln roseville placer nevada "
    "el dorado miller sacramento foresthill".split()
)
_ECHO_MIN_WORDS = 3


def strip_prompt_echo(text: str) -> str:
    """Drop a trailing copy of the decoder hint list, if Whisper appended one."""
    text = _HOTWORD_ECHO.sub("", text or "").strip()
    words = text.split()
    run = 0
    for w in reversed(words):
        if re.sub(r"[^a-z]", "", w.lower()) not in _HOTWORD_WORDS:
            break
        run += 1
    if run >= _ECHO_MIN_WORDS:
        text = " ".join(words[:-run])
    return text


def normalize(text: str) -> str:
    text = strip_prompt_echo(text).lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9'\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _mentioned(text: str, pattern: re.Pattern):
    """First match whose preceding words do not negate it."""
    for m in pattern.finditer(text):
        window = text[max(0, m.start() - 48):m.start()]
        if _NEG.search(window):
            continue
        return m.group(0)
    return None


# State routes and interstates that cross the watched area. A bare number
# only counts as a highway when it is one of these.
_AREA_HIGHWAYS = {"20", "49", "50", "65", "70", "80", "99", "174", "193"}
_HWY_ANY = re.compile(
    r"\b(?:highway|hwy|interstate|i|sr|route|state route)[\s-]*(\d{1,3})\b"
)
_HWY_DIR = re.compile(
    r"\b(\d{2,3})\s+(?:east|west|north|south)(?:bound)?\b|"
    r"\b(?:east|west|north|south)bound\s+(\d{2,3})\b"
)
_ROAD_NAME = re.compile(
    r"\b([a-z]+(?:\s+[a-z]+)?)\s+"
    r"(street|st|road|rd|avenue|ave|drive|dr|lane|ln|way|"
    r"blvd|boulevard|court|ct|circle|cir|place|pl)\b"
)
_ROAD_STOP = {"the", "a", "on", "at", "and", "of", "to", "in", "off", "is",
              "west", "east", "north", "south", "old", "new", "your", "that"}


def location_tokens(text: str) -> set:
    """Loose place tokens ("hwy 49", "dry creek") for cross-channel merging."""
    t = normalize(text)
    out = set()
    for m in _HWY_ANY.finditer(t):
        if m.group(1) in _AREA_HIGHWAYS:
            out.add(f"hwy {m.group(1)}")
    for m in _HWY_DIR.finditer(t):
        num = m.group(1) or m.group(2)
        if num in _AREA_HIGHWAYS:
            out.add(f"hwy {num}")
    for m in _ROAD_NAME.finditer(t):
        words = [w for w in m.group(1).split() if w not in _ROAD_STOP]
        if words:
            out.add(" ".join(words))
    for m in _FORESTHILL.finditer(t):
        out.add("foresthill")
    return out


def location_key(text: str):
    t = normalize(text)
    m = _LOC_STREET.search(t)
    if m:
        suffix = _STREET_SUFFIX.get(m.group(3), m.group(3))
        return f"{m.group(1)} {m.group(2)} {suffix}"
    h = _LOC_HWY.search(t)
    if h:
        return f"hwy {h.group(1)}"
    return None


def foresthill_mentioned(text: str):
    """The Foresthill wording in an already-normalized transcript, or None."""
    for m in _FORESTHILL.finditer(text):
        if _PLACE_NEG.search(text[max(0, m.start() - 12):m.start()]):
            continue
        return m.group(0)
    return None


def _hit(category_id: str, evidence: str):
    _id, label, detail, _chip = _BY_ID[category_id]
    return {
        "category": category_id,
        "label": label,
        "detail": detail,
        "evidence": evidence,
    }


def classify(text: str):
    """Return a hit dict, or None when the call is not a major incident.

    A major incident that names Foresthill keeps its own category and
    carries place="foresthill"; routine traffic that names it becomes a
    "foresthill" hit.
    """
    t = normalize(text)
    if not t:
        return None
    place = foresthill_mentioned(t)
    hit = _classify_major(t)
    if hit:
        if place:
            hit["place"] = "foresthill"
        return hit
    if place:
        hit = _hit("foresthill", place)
        hit["place"] = "foresthill"
        return hit
    return None


def _classify_major(t: str):

    if _mentioned(t, _FIREFIGHTER) or _mentioned(t, _MAYDAY_REPEAT):
        return _hit("firefighter_down", "firefighter down")
    if _mentioned(t, _MAYDAY) and _mentioned(t, _FF_WORD):
        return _hit("firefighter_down", "mayday")
    if _mentioned(t, _COLLAPSE):
        return _hit("building_collapse", "collapse")
    if _mentioned(t, _MCI):
        return _hit("mass_casualty", "mass casualty")

    airport = _mentioned(t, _AIRPORT)
    if not airport and _AIRPORT_CTX.search(t):
        airport = _mentioned(t, _AIRPORT_ALERT_N)
    if airport:
        return _hit("airport_alert", airport)

    if _mentioned(t, _SHOOTING) and not _SHOOTING_PAIN.search(t):
        evidence = _mentioned(t, _SHOOTING)
        return _hit("shooting", evidence)

    if _mentioned(t, _TECH):
        return _hit("technical_rescue", _mentioned(t, _TECH))

    mva = _mentioned(t, _MVA_STRONG) or _mentioned(t, _MVA_MAJOR)
    if not mva and _mentioned(t, _HIGH_LEVEL) and _mentioned(t, _CRASH_WORD):
        mva = "high level " + _mentioned(t, _CRASH_WORD)
    if not mva and _mentioned(t, _MVA_CONTEXT) and _mentioned(t, _MVA_EXTRA):
        mva = _mentioned(t, _MVA_EXTRA)
    if mva:
        return _hit("motor_vehicle_accident", mva)

    brush = _mentioned(t, _BRUSH)
    if brush and _mentioned(t, _BRUSH_MAJOR):
        return _hit("brush_grass_fire", brush)

    severity = _mentioned(t, _SEVERITY)
    if not severity:
        return None

    other = _mentioned(t, _OTHER_OBJECT)
    structure = _mentioned(t, _STRUCTURE_OBJECT)
    if other and not structure:
        return _hit("other_fire", severity)
    if brush and not structure:
        return None
    return _hit("structure_fire", severity)


def _epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return time.time()


def _apply_merge(prev: dict, new: dict):
    channels = list(prev.get("channels") or [prev.get("talkgroup_name") or ""])
    name = new.get("talkgroup_name") or ""
    # Tell the caller what happened, so it can notify on a new channel only.
    new["merged_into"] = prev.get("id")
    new["new_channel"] = bool(name) and name not in channels
    if name and name not in channels:
        channels.append(name)
    prev["channels"] = [c for c in channels if c]
    prev["loc_tokens"] = sorted(_tokens_of(prev) | _tokens_of(new))
    prev["updated"] = new["updated"]
    prev["text"] = new["text"]
    if new.get("rel"):
        prev["rel"] = new["rel"]
    if new.get("evidence"):
        prev["evidence"] = new["evidence"]
    prev["calls"] = int(prev.get("calls") or 1) + 1
    if new.get("talkgroup_name"):
        prev["talkgroup_name"] = new["talkgroup_name"]
    if new.get("location") and not prev.get("location"):
        prev["location"] = new["location"]
    if new.get("place") and not prev.get("place"):
        prev["place"] = new["place"]


def _tokens_of(alert: dict) -> set:
    if alert.get("loc_tokens") is not None:
        return set(alert["loc_tokens"])
    return location_tokens(alert.get("text") or "")


def merge_alert(alerts: list, new: dict) -> list:
    """Fold new into an open alert, or append it. Oldest first, capped."""
    alerts = list(alerts)
    new_epoch = _epoch(new["updated"])
    loc = new.get("location")
    for prev in reversed(alerts):
        if prev.get("category") != new.get("category"):
            continue
        gap = new_epoch - _epoch(prev.get("updated") or prev.get("started"))
        if gap < 0:
            gap = 0
        prev_loc = prev.get("location")
        if loc and prev_loc and loc != prev_loc:
            continue
        same_tg = (prev.get("system") == new.get("system")
                   and prev.get("talkgroup") == new.get("talkgroup"))
        # Foresthill is a place watch. Unrelated calls on the same channel
        # stay separate so the list shows how often the name comes up.
        if new.get("category") == "foresthill":
            same_tg = False
        if same_tg and gap <= MERGE_SAME_TG_SEC:
            _apply_merge(prev, new)
            return alerts[-ALERT_CAP:]
        if loc and prev_loc and loc == prev_loc and gap <= MERGE_LOCATION_SEC:
            _apply_merge(prev, new)
            return alerts[-ALERT_CAP:]
        if (not same_tg and new.get("category") != "foresthill"
                and gap <= MERGE_CROSS_CHANNEL_SEC):
            a, b = _tokens_of(prev), _tokens_of(new)
            if not a or not b or a & b:
                _apply_merge(prev, new)
                return alerts[-ALERT_CAP:]
    alerts.append(new)
    return alerts[-ALERT_CAP:]


def _load(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, list):
            data = {"alerts": data}
    else:
        data = {}
    data["categories"] = categories_public()
    data.setdefault("alerts", [])
    return data


def _write_atomic(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def record_alert(hit: dict, *, talkgroup, talkgroup_name, system, when_iso,
                 rel, text, alerts_path=None) -> dict:
    """Merge one classified call into the alerts file.

    Returns the new record. When it was folded into an open alert, the
    record carries merged_into (that alert's id), new_channel, and channels
    (every channel on the merged alert).
    """
    path = Path(alerts_path) if alerts_path else ALERTS_PATH
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) > 500:
        text = text[:497] + "..."
    now = when_iso or datetime.now().isoformat(timespec="seconds")
    new = {
        "id": uuid.uuid4().hex[:12],
        "category": hit["category"],
        "label": hit["label"],
        "detail": hit["detail"],
        "evidence": hit.get("evidence") or "",
        "text": text,
        "talkgroup": talkgroup,
        "talkgroup_name": talkgroup_name,
        "system": system,
        "started": now,
        "updated": now,
        "rel": rel or "",
        "calls": 1,
        "location": location_key(text),
        "loc_tokens": sorted(location_tokens(text)),
        "channels": [talkgroup_name] if talkgroup_name else [],
    }
    if hit.get("place"):
        new["place"] = hit["place"]
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as lock:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            data = _load(path)
            data["alerts"] = merge_alert(data["alerts"], new)
            if new.get("merged_into"):
                for a in data["alerts"]:
                    if a.get("id") == new["merged_into"]:
                        new["channels"] = list(a.get("channels") or [])
                        new["calls"] = a.get("calls") or 1
                        break
            _write_atomic(path, data)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return new
