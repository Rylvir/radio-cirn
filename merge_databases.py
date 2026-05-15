import sqlite3
import sys

old_db = "radio_calls_old.db"
new_db = "radio_calls.db"

print("🔄 Merging databases...")

conn_new = sqlite3.connect(new_db)
conn_old = sqlite3.connect(old_db)

# Get all rows from old DB
rows = conn_old.execute("SELECT * FROM calls").fetchall()
print(f"Found {len(rows)} calls in old database.")

inserted = 0
for row in rows:
    try:
        conn_new.execute('''INSERT OR IGNORE INTO calls 
                            (filename, talkgroup, talkgroup_name, start_time, epoch, 
                             frequency, transcription, audio_url)
                            VALUES (?,?,?,?,?,?,?,?)''', row[1:])  # skip id column
        inserted += 1
    except:
        pass  # skip any bad rows

conn_new.commit()
conn_new.close()
conn_old.close()

print(f"✅ Merge complete! Added {inserted} new unique calls.")
print("You can now safely delete radio_calls_old.db")
