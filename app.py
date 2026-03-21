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

# Custom CSS for Equal Sized Boxes and Centered Content
st.markdown("""
<style>
    /* Force columns to contain equal-sized metric boxes */
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 0 !important;
        min-width: 0 !important;
    }
    
    [data-testid="stMetric"] {
        background-color: rgba(28, 131, 225, 0.1); 
        padding: 20px; 
        border-radius: 15px; 
        border: 1px solid rgba(128, 128, 128, 0.3);
        height: 150px; /* Fixed height for symmetry */
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        text-align: center;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        line-height: 1.2 !important;
    }

    [data-testid="stMetricLabel"] {
        font-size: 1.1rem !important;
        margin-bottom: 10px !important;
    }

    [data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        justify-content: center !important;
    }

    .footer-right { position: fixed; bottom: 10px; right: 10px; color: gray; font-size: 0.8em; font-weight: bold; z-index: 1000; }
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
    st.error(f"Secrets Error. Check Streamlit Settings.")
    st.stop()

# --- 2. LOGIC & DATA ENGINE ---
FILE_PATH = "lucky_ledger.csv"
COLS = ["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Commission", "Premium", "Status"]

def save_journal(df):
    try:
        csv_content = df[COLS].to_csv(index=False)
        commit_message = f"Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        try:
            contents = repo.get_contents(FILE_PATH)
            repo.update_file(contents.path, commit_message, csv_content, contents.sha)
        except:
            repo.create_file(FILE_PATH, "Init", csv_content)
        st.session_state.last_update = datetime.now().strftime("%Y-%m-%d")
    except Exception as e:
        st.error(f"GitHub Sync Failed: {e}")

def load_journal():
    try:
        contents = repo.get_contents(FILE_PATH)
        decoded_content = base64.b64decode(contents.content).decode('utf-8')
        df = pd.read_csv(io.StringIO(decoded_content))
        for c in COLS:
            if c not in df.columns:
                df[c] = 0.0 if c in ["Open Price", "Close Price", "Premium", "Commission"] else (1 if c == "Qty" else "Unknown")
        df['exp_dt'] = pd.to_datetime(df['Expiry'], errors='coerce')
        df['is_open'] = df['Status'].astype(str).str.contains("Open", case=False, na=False)
        df = df.sort_values(by=['is_open', 'exp_dt'], ascending=[False, False])
        return df[COLS].reset_index(drop=True)
    except:
        return pd.DataFrame(columns=COLS)

if 'journal' not in st.session_state: 
    st.session_state.journal = load_journal()
    st.session_state.last_update = datetime.now().strftime("%Y-%m-%d")

# --- 3. UI TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- OPTIMIZER ---
with tab1:
    st.write("Short Put Probability Analysis")
    c1, c2, c3 = st.columns(3)
    tk = c1.text_input("Ticker", value="TSM").upper()
    sf = c2.slider("Safety %", 70, 99, 90)
    iv_input = c3.slider("IV %", 10, 200, 30) 
    
    if st.button("🔬 Run Analysis", type="primary"):
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
            st.success(f"**{tk}:** ${px:.2f} | **Expiry:** {exp.date()}")
            if res: st.dataframe(pd.DataFrame(res).sort_values("Strike", ascending=False), use_container_width=True)
            else: st.warning("No matches.")
        except Exception as e: st.error(f"Error: {e}")

# --- LEDGER ---
with tab2:
    df_j = st.session_state.journal
    total_prem = df_j["Premium"].sum()
    active_count = len(df_j[df_j["Status"].astype(str).str.contains("Open", na=False)])
    
    m1, m2 = st.columns(2)
    
    # Symmetric Metrics
    m1.metric(label="Total Premium 🤑", 
              value=f"${total_prem:,.2f}", 
              delta=f"≈ HKD {(total_prem*7.8):,.0f}", 
              delta_color="normal")
              
    m2.metric(label="Active Trades 📈", 
              value=str(active_count))

    with st.expander("➕ Log New Trade"):
        l1, l2, l3, l4 = st.columns(4)
        n_tk = l1.text_input("Ticker").upper()
        n_ty = l2.selectbox("Type", ["Short Put", "Short Call"])
        n_qt = l3.number_input("Qty", value=1, min_value=1)
        n_ex = l4.date_input("Expiry", datetime.now().date())
        l5, l6 = st.columns(2)
        n_st = l5.number_input("Strike", value=0.0, format="%.1f")
        n_op = l6.number_input("Open Price", value=0.0, format="%.2f")
        
        if st.button("🚀 Commit Trade", use_container_width=True, type="primary"):
            if n_tk:
                comm = round(n_qt * 1.05, 2)
                net = round((float(n_op) * 100 * n_qt) - comm, 2)
                stat = "Expired (Win)" if n_ex < datetime.now().date() else "Open / Running"
                new_row = pd.DataFrame([{"Ticker": n_tk, "Type": n_ty, "Strike": round(n_st, 1), "Expiry": str(n_ex), "Open Price": round(float(n_op), 2), "Close Price": 0.0, "Qty": n_qt, "Commission": comm, "Premium": net, "Status": stat}])
                st.session_state.journal = pd.concat([df_j, new_row], ignore_index=True)
                save_journal(st.session_state.journal)
                st.rerun()

    st.write("### Trade History")
    def refresh_calculations(current_df):
        for col in ["Strike", "Open Price", "Close Price", "Qty", "Commission"]:
            current_df[col] = pd.to_
