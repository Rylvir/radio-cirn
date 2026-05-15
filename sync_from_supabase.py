import sqlite3
from supabase import create_client

SUPABASE_URL = "https://jygevxqydcvmbjzinidv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp5Z2V2eHF5ZGN2bWJqemluaWR2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODM5MjE3NCwiZXhwIjoyMDkzOTY4MTc0fQ.PIM1CeQVnfsWDiKRd_gYZip0HchSc0McJUeDSOT2A2c"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
conn = sqlite3.connect("radio_calls.db")

print("Downloading all calls from Supabase...")
data = supabase.table("calls").select("*").execute().data

print(f"Found {len(data)} calls in Supabase.")

inserted = 0
for row in data:
    try:
        conn.execute('''INSERT OR IGNORE INTO calls 
                        (filename, talkgroup, talkgroup_name, start_time, epoch, 
                         frequency, transcription, audio_url)
                        VALUES (?,?,?,?,?,?,?,?)''',
                     (row.get('filename'), row.get('talkgroup'), row.get('talkgroup_name'),
                      row.get('start_time'), row.get('epoch'), row.get('frequency'),
                      row.get('transcription'), row.get('audio_url')))
        inserted += 1
    except Exception as e:
        pass

conn.commit()
conn.close()
print(f"✅ Sync complete! Added/updated {inserted} calls.")
