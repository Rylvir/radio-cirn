import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd

st.set_page_config(page_title="PIRCS Radio", layout="wide")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Supabase credentials not configured.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🟢 Placer Interoperable Radio Communication System (PIRCS)")
st.caption("Live Radio Transcriptions — Full Database Search")

search_term = st.text_input("🔍 Search Transcription or Talkgroup", "", 
                           placeholder="Type 'forest', 'Auburn', 'Henry', '10-4', etc...")

@st.cache_data(ttl=30)
def load_data(search_term=""):
    # No limit — searches the whole database
    query = supabase.table("calls").select("*").order("start_time", desc=True)
    
    if search_term:
        # Supabase full-text style search
        response = query.or_(
            f"transcription.ilike.%{search_term}%,talkgroup_name.ilike.%{search_term}%"
        ).execute()
    else:
        response = query.limit(100).execute()   # Show last 100 when no search
        
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["start_time"] = pd.to_datetime(df["start_time"])
    return df

df = load_data(search_term)

st.write(f"**Showing {len(df)} matching calls**")

if df.empty:
    st.info("No matching calls found. Try a different search term.")
else:
    for _, row in df.head(30).iterrows():   # Show up to 30 results
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
