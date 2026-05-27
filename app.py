import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="PIRCS Radio", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🟢 Placer Interoperable Radio Communication System (PIRCS)")
st.caption("Searchable Radio Transcriptions")

search_term = st.text_input("🔍 Search", "", placeholder="Type 'forest', 'Auburn', 'Henry', etc...")

@st.cache_data(ttl=30)
def load_data():
    response = supabase.table("calls").select("*").order("start_time", desc=True).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"])
    return df

df = load_data()

if search_term:
    mask = (
        df["transcription"].astype(str).str.contains(search_term, case=False, na=False) |
        df["talkgroup_name"].astype(str).str.contains(search_term, case=False, na=False)
    )
    df = df[mask]

st.write(f"**Showing {len(df)} calls**")

if df.empty:
    st.info("No calls found. Try a different search term.")
else:
    for _, row in df.head(30).iterrows():
        col1, col2 = st.columns([1.2, 4])
        
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
