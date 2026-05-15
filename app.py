import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd

st.set_page_config(page_title="PIRCS Radio", layout="wide")

# ===================== CONFIG =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== TITLE =====================
st.title("🟢 Placer Interoperable Radio Communication System (PIRCS)")
st.caption("Live Radio Transcriptions — CIRN")

# ===================== SEARCH =====================
search_term = st.text_input("🔍 Search Transcription or Talkgroup", "", placeholder="Type a name, unit, or keyword...")

# ===================== LOAD DATA =====================
@st.cache_data(ttl=15)
def load_recent_calls():
    response = supabase.table("calls").select("*").order("start_time", desc=True).limit(100).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"])
    return df

df = load_recent_calls()

# Filter if searching
if search_term:
    mask = (
        df["transcription"].astype(str).str.contains(search_term, case=False, na=False) |
        df["talkgroup_name"].astype(str).str.contains(search_term, case=False, na=False)
    )
    df = df[mask]

st.write(f"**Showing {len(df)} calls**")

# ===================== DISPLAY =====================
if df.empty:
    st.info("No calls found.")
else:
    # Show only the most recent 25 by default
    display_df = df.head(25)
    
    for _, row in display_df.iterrows():
        col1, col2 = st.columns([1, 4])
        
        with col1:
            st.subheader(row["talkgroup_name"])
            st.caption(row["start_time"].strftime("%Y-%m-%d %H:%M:%S"))
        
        with col2:
            st.write(row.get("transcription", ""))
            
            audio_url = row.get("audio_url")
            if isinstance(audio_url, str) and audio_url.startswith("http"):
                st.audio(audio_url, format="audio/mp3")
            else:
                st.caption("📁 Audio stored locally only")
        
        st.divider()
