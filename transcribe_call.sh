#!/bin/bash
cd /home/scribe/radio-transcriber
source venv/bin/activate

export SUPABASE_URL="https://jygevxqydcvmbjzinidv.supabase.co"
export SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp5Z2V2eHF5ZGN2bWJqemluaWR2Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODM5MjE3NCwiZXhwIjoyMDkzOTY4MTc0fQ.PIM1CeQVnfsWDiKRd_gYZip0HchSc0McJUeDSOT2A2c"

python3 transcribe_radio.py "$1" "$2" >> /home/scribe/radio-transcribe.log 2>&1 &
