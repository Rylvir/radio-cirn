#!/usr/bin/env python3
import os
import re
import sqlite3
import sys
import pandas as pd
from datetime import datetime, timedelta
from faster_whisper import WhisperModel
from supabase import create_client, Client

# ===================== CONFIG =====================
MODEL_SIZE = "medium"          # Use "medium" first on new machine to avoid crashes
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

DB_FILE = "radio_calls.db"
INITIAL_PROMPT = "This is a police radio call. Use 10-codes, unit numbers, street names, license plates spelled phonetically."

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

UPLOAD_TALKGROUPS = {10601, 2001}
UPLOAD_DAYS = 7

# ===================== TALKGROUP NAMES =====================
tg_name_map = {}
CSV_DIR = "/home/scribe/trunk-build"   # Change if your path is different
for csv_file in ["cirn.csv", "beale.csv", "cris.csv"]:
    path = os.path.join(CSV_DIR, csv_file)
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if 'Decimal' in df.columns and 'Alpha Tag' in df.columns:
                for _, row in df.iterrows():
                    try:
                        tg = int(row['Decimal'])
                        name = str(row['Alpha Tag']).strip()
                        if name and name.lower() not in ['nan', '']:
                            tg_name_map[tg] = name
                    except:
                        continue
        except:
            pass

def parse_filename(filename):
    pattern = r"(\d+)-(\d+)_(\d+\.\d+)-call_(\d+)"
    match = re.search(pattern, filename)
    if match:
        tg = int(match.group(1))
        epoch = int(match.group(2))
        freq = float(match.group(3))
        return {
            "filename": filename,
            "talkgroup": tg,
            "talkgroup_name": tg_name_map.get(tg, f"TG {tg}"),
            "start_time": datetime.fromtimestamp(epoch).isoformat(),
            "epoch": epoch,
            "frequency": freq,
        }
    return None

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('''CREATE TABLE IF NOT EXISTS calls (
                    filename TEXT UNIQUE PRIMARY KEY,
                    talkgroup INTEGER,
                    talkgroup_name TEXT,
                    start_time TEXT,
                    epoch INTEGER,
                    frequency REAL,
                    transcription TEXT,
                    audio_url TEXT)''')
    conn.commit()
    return conn

def already_transcribed(conn, filename):
    c = conn.cursor()
    c.execute("SELECT 1 FROM calls WHERE filename=?", (filename,))
    return c.fetchone() is not None

def should_upload_audio(meta):
    if meta["talkgroup"] not in UPLOAD_TALKGROUPS:
        return False
    call_time = datetime.fromisoformat(meta["start_time"].replace("Z", "+00:00"))
    return datetime.now() - call_time < timedelta(days=UPLOAD_DAYS)

def upload_audio_to_supabase(audio_path):
    try:
        filename = os.path.basename(audio_path)
        with open(audio_path, "rb") as f:
            supabase.storage.from_("audio").upload(filename, f, file_options={"content-type": "audio/mpeg"})
        return supabase.storage.from_("audio").get_public_url(filename)
    except Exception as e:
        print(f"⚠️ Upload failed: {e}")
        return None

def insert_call(conn, meta, transcription, audio_url=None):
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO calls 
                 (filename, talkgroup, talkgroup_name, start_time, epoch, frequency, transcription, audio_url)
                 VALUES (?,?,?,?,?,?,?,?)''',
              (meta["filename"], meta["talkgroup"], meta["talkgroup_name"],
               meta["start_time"], meta["epoch"], meta["frequency"], transcription, audio_url))
    conn.commit()
    print("✅ Saved")

    try:
        supabase.table("calls").upsert({
            "filename": meta["filename"], "talkgroup": meta["talkgroup"],
            "talkgroup_name": meta["talkgroup_name"], "start_time": meta["start_time"],
            "epoch": meta["epoch"], "frequency": meta["frequency"],
            "transcription": transcription, "audio_url": audio_url
        }).execute()
    except:
        pass

def transcribe_file(model, filepath):
    segments, _ = model.transcribe(
        filepath, beam_size=5, language="en",
        initial_prompt=INITIAL_PROMPT, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    return " ".join(seg.text for seg in segments).strip()

def main():
    conn = init_db()
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

    audio_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not audio_file or not os.path.isfile(audio_file):
        return

    filename = os.path.basename(audio_file)
    print(f"🎙 Transcribing: {filename}")

    meta = parse_filename(filename)
    if not meta or already_transcribed(conn, filename):
        print("⏭️ Already transcribed")
        return

    text = transcribe_file(model, audio_file)

    audio_url = None
    if should_upload_audio(meta):
        print("☁️ Uploading audio...")
        audio_url = upload_audio_to_supabase(audio_file)
    else:
        print("📁 Skipping audio upload")

    insert_call(conn, meta, text, audio_url)
    print(f"✅ {text[:100]}...")

if __name__ == "__main__":
    main()
