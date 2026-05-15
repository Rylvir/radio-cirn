#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime, timedelta
from tqdm import tqdm

print("🚀 Starting Batch Transcription - Best Quality Mode (large-v3)")

# ===================== CONFIG =====================
ROOT_DIR = "/home/scribe/trunk-build/cirn"
DAYS_BACK = 21                    # Safe starting point (you can increase later)
MODEL_SIZE = "large-v3"

# ===================== FIND FILES =====================
print("Scanning for MP3 files...")
files_to_process = []
cutoff = datetime.now() - timedelta(days=DAYS_BACK)

for root, _, files in os.walk(ROOT_DIR):
    for f in files:
        if f.endswith(".mp3"):
            full_path = os.path.join(root, f)
            mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
            if mtime > cutoff:
                files_to_process.append(full_path)

print(f"Found {len(files_to_process)} MP3 files in the last {DAYS_BACK} days.")

# ===================== PROCESS =====================
processed = 0
for filepath in tqdm(files_to_process, desc="Transcribing"):
    filename = os.path.basename(filepath)
    json_path = filepath.replace(".mp3", ".json")

    try:
        result = subprocess.run([
            "python3", "transcribe_radio.py", filepath, json_path
        ], capture_output=True, text=True, timeout=300)

        output = result.stdout + result.stderr

        if "Already transcribed" in output:
            continue

        processed += 1
        if "Uploading audio" in output:
            print(f"☁️ Audio uploaded → {filename}")
        else:
            print(f"✅ Transcribed (no audio) → {filename}")

    except subprocess.TimeoutExpired:
        print(f"⏰ Timeout → {filename}")
    except Exception as e:
        print(f"❌ Error → {filename}")

print(f"\n🎉 Batch finished! Processed {processed} new calls.")
