import os
from datetime import datetime
import streamlit as st
from supabase import create_client

# =====================================================
# Configuration
# =====================================================
PAGE_SIZE = 30

st.set_page_config(page_title="PIRCS Radio", layout="wide")

# =====================================================
# Supabase Connection (fail fast with clear message)
# =====================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY environment variables.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================
# UI Header
# =====================================================
st.title("🟢 Placer Interoperable Radio Communication System (PIRCS)")
st.caption("Transcribed Radio Calls — Full Search (powered by Supabase + trigram indexes)")

# =====================================================
# Search Input
# =====================================================
search_term = st.text_input(
    "🔍 Search Transcription or Talkgroup",
    "",
    placeholder="forest, Auburn, Henry, 10-4, dispatch...",
    key="search_input",
)

# =====================================================
# Pagination State Management
# =====================================================
if "offset" not in st.session_state:
    st.session_state.offset = 0
if "last_search" not in st.session_state:
    st.session_state.last_search = ""

# Reset to first page whenever the search term changes
if search_term != st.session_state.last_search:
    st.session_state.offset = 0
    st.session_state.last_search = search_term


def fetch_calls(search_term: str, offset: int, page_size: int = PAGE_SIZE):
    """
    Server-side search using Supabase.
    Uses trigram indexes (idx_calls_transcription_trgm + idx_calls_talkgroup_name_trgm)
    for fast ILIKE searches across the full dataset.
    """
    query = supabase.table("calls").select("*", count="exact")

    if search_term:
        # Escape special characters for ILIKE
        safe = search_term.replace("%", r"\%").replace("_", r"\_")
        query = query.or_(
            f"transcription.ilike.%{safe}%,talkgroup_name.ilike.%{safe}%"
        )

    response = (
        query.order("start_time", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    total = response.count or 0
    rows = response.data or []
    return rows, total


# =====================================================
# Fetch Data (server-side, limited to current page)
# =====================================================
with st.spinner("Searching..." if search_term else "Loading recent calls..."):
    try:
        rows, total = fetch_calls(search_term, st.session_state.offset)
    except Exception as e:
        st.error(f"Error querying Supabase: {e}")
        st.stop()

shown = len(rows)

# =====================================================
# Results Header
# =====================================================
if search_term:
    st.write(f"**Showing {shown} of {total} matching calls**")
else:
    st.write(f"**Showing the most recent {shown} calls** (total in database: {total})")

# =====================================================
# Results Display
# =====================================================
if not rows:
    if search_term:
        st.info("No matches found for your search. Try broadening your terms or clearing the search.")
    else:
        st.info("No recent calls found.")
else:
    for row in rows:
        col1, col2 = st.columns([1.2, 4])

        with col1:
            st.subheader(row.get("talkgroup_name", "Unknown TG"))
            start = row.get("start_time")
            if start:
                try:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    st.caption(dt.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    st.caption(str(start))

        with col2:
            st.write(row.get("transcription", ""))
            audio_url = row.get("audio_url")
            if isinstance(audio_url, str) and audio_url.startswith("http"):
                st.audio(audio_url, format="audio/mp3")
            else:
                st.caption("📁 Audio stored locally only")

        st.divider()

    # =====================================================
    # Pagination - Load More
    # =====================================================
    remaining = total - (st.session_state.offset + shown)
    if shown == PAGE_SIZE and remaining > 0:
        button_text = f"Load more results ({remaining} remaining)"
        if st.button(button_text):
            st.session_state.offset += PAGE_SIZE
            st.rerun()

# =====================================================
# Footer / Reset
# =====================================================
if st.session_state.offset > 0 or search_term:
    if st.button("🔄 Start over / Show recent calls"):
        st.session_state.offset = 0
        st.session_state.last_search = ""
        st.rerun()

st.markdown("---")
st.caption("Search powered by Supabase full-text indexes • 30 results per page")
