import streamlit as st

st.set_page_config(
    page_title="TradeLens AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.title("📊 TradeLens AI")
    st.markdown("---")
    st.markdown("🏠 Home")
    st.markdown("➕ New Trade")
    st.markdown("📋 Trades")
    st.markdown("📅 Calendar")
    st.markdown("📈 Analytics")
    st.markdown("🎯 Strategy")
    st.markdown("📝 Weekly Review")
    st.markdown("⚙️ Settings")

st.title("TradeLens AI 📊")
st.subheader("AI-Powered Trading Journal & Self-Review Dashboard")
st.markdown("---")

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric(label="Total P&L", value="$0.00")
with col2:
    st.metric(label="Win Rate", value="0%")
with col3:
    st.metric(label="Profit Factor", value="0.00")
with col4:
    st.metric(label="Avg R:R", value="0.00")
with col5:
    st.metric(label="Trades This Week", value="0")

st.markdown("---")
st.info("👋 Welcome to TradeLens AI. Start by adding your first trade or setting up your Strategy Profile.")