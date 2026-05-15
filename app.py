import os
import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import pandas as pd

st.set_page_config(page_title="PIRCS Radio", layout="wide")

# ===================== CONFIG =====================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase credentials are not configured on Render.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== TITLE =====================
st.title("🟢 Placer Interoperable Radio Communication System (PIRCS)")
st.caption("Live & Searchable Radio Transcriptions — CIRN")

# ===================== FILTERS =====================
st.sidebar.header("Filters")

all_time = st.sidebar.checkbox("Show All Time", value=False)

if not all_time:
    today = datetime.now().date()
    start_date = st.sidebar.date_input("Start Date", today - timedelta(days=14))
    end_date = st.sidebar.date_input("End Date", today)
else:
    start_date = end_date = None

search_term = st.sidebar.text_input("Search Transcription or Talkgroup", "")

# ===================== LOAD DATA =====================
@st.cache_data(ttl=30)
def load_data():
    response = supabase.table("calls").select("*").order("start_time", desc=True).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return df

    df["start_time"] = pd.to_datetime(df["start_time"])

    if not all_time and start_date and end_date:
        df = df[(df["start_time"].dt.date >= start_date) & (df["start_time"].dt.date <= end_date)]

    if search_term:
        mask = (
            df["transcription"].astype(str).str.contains(search_term, case=False, na=False) |
            df["talkgroup_name"].astype(str).str.contains(search_term, case=False, na=False)
        )
        df = df[mask]
    return df

df = load_data()

st.write(f"**Showing {len(df)} calls**")

# ===================== DISPLAY =====================
if df.empty:
    st.info("No calls found.")
else:
    for _, row in df.iterrows():
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
