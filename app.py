import streamlit as st
import pandas as pd
import numpy as np
import io
import base64
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import OptionsFeed, DataFeed
from github import Github

# --- 1. CONFIG & API ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background-color: rgba(28, 131, 225, 0.05); 
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 15px;
        height: 140px; 
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
        margin-bottom: 15px;
    }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 800 !important; }
    [data-testid="stMetricDelta"] { font-size: 1rem !important; color: #888888 !important; justify-content: center !important; }
    [data-testid="stMetricDelta"] > svg { display: none; }
    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; z-index: 1000; }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🧪 Lucky Quants Lab")
st.divider()

# API Connections
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(GITHUB_REPO)
except Exception as e:
    st.error(f"Secrets Error. Check Streamlit Settings. {e}")
    st.stop()

# --- 2. LOGIC & DATA ENGINE ---
FILE_PATH = "lucky_ledger.csv"
COLS = ["Date", "Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def sort_ledger(df):
    """Custom Multi-Level Sort: 1. Date (Newest first) -> 2. Status (Open -> Win -> Loss)"""
    if df.empty: return df
    df['temp_date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    def rank_status(s):
        s = str(s)
        if "Open" in s: return 1
        if "Win" in s: return 2
        if "Loss" in s: return 3
        return 4
        
    df['status_rank'] = df['Status'].apply(rank_status)
    df = df.sort_values(by=['temp_date', 'status_rank'], ascending=[False, True])
    df['Date'] = df['temp_date'].dt.strftime('%Y-%m-%d')
    return df.drop(columns=['temp_date', 'status_rank']).reset_index(drop=True)

def save_journal(df):
    try:
        df_sorted = sort_ledger(df)
        csv_content = df_sorted[COLS].to_csv(index=False)
        commit_message = f"Ledger Auto-Sync: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            contents = repo.get_contents(FILE_PATH)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha)
        except:
            repo.create_file(FILE_PATH, "Initial commit", csv_content)
        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        st.error(f"GitHub Sync Failed: {e}")

def load_journal():
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_content))
        
        # Data Migration: Fill missing columns
        for c in COLS:
            if c not in df.columns:
                if c == "Date": df[c] = datetime.now().strftime("%Y-%m-%d")
                else: df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        return sort_ledger(df[COLS])
    except Exception as e:
        if "404" in str(e): return pd.DataFrame(columns=COLS)
        else:
            st.error(f"⚠️ Emergency Stop: Could not connect to GitHub. Error: {e}")
            st.stop()

# PRO FIX: Schema Validation! Forces a reload if your browser memory has the old columns.
if 'journal' not in st.session_state or set(st.session_state.journal.columns) != set(COLS): 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- OPTIMIZER ---
with tab1:
    st.write("Calculates short put probabilities using Black-Scholes.")
    c1, c2, c3 = st.columns(3)
    tk = c1.text_input("Ticker", value="TSM").upper()
    sf = c2.slider("Safety %", 70, 99, 90)
    iv_input = c3.slider("IV %", 10, 200, 30) 
    
    if st.button("🔬 Run Analysis", type="primary"):
        with st.spinner("Fetching data..."):
            try:
                px = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=tk, feed=DataFeed.IEX))[tk].ask_price
                exp = datetime.now() + timedelta(days=(4-datetime.now().weekday()+7)%7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=tk, expiration_date=exp.date(), feed=OptionsFeed.INDICATIVE))
                res = []
                iv_decimal = iv_input / 100.0
                for s, d in chain.items():
                    stk_val = float(s[-8:])/1000
                    if "P" in s and stk_val < px:
                        d2 = (np.log(px/stk_val) + (0.04 - 0.5 * iv_decimal**2)*(7/365)) / (iv_decimal * np.sqrt(7/365))
                        prob = norm.cdf(d2) * 100
                        if prob >= sf:
                            mid = (d.bid_price + d.ask_price) / 2
                            res.append({"Strike": stk_val, "Safety %": round(prob, 1), "Premium": round(mid, 2), "Est. Income": round(mid*100, 2)})
                st.success(f"**{tk} Price:** ${px:.2f} | **Expiry:** {exp.date()}")
                if res: st.dataframe(pd.DataFrame(res).sort_values("Strike", ascending=False), use_container_width=True)
                else: st.warning("No matches.")
            except Exception as e: st.error(f"Error: {e
