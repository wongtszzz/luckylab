import streamlit as st
import pandas as pd
import numpy as np
import os
from scipy.stats import norm
from datetime import datetime, timedelta
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import OptionsFeed, DataFeed

# --- 1. CONFIG & STYLING ---
st.set_page_config(page_title="Lucky Quants Lab", page_icon="🧪", layout="wide")

st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    .stMetric { background-color: #f0f2f6; padding: 5px 15px; border-radius: 10px; border: 1px solid #dcdcdc; }
    div[data-testid="stExpander"] { border: 1px solid #e6e9ef; border-radius: 10px; }
    hr {margin: 0.5em 0px;}
    </style>
    """, unsafe_allow_html=True)

h1, h2 = st.columns([2, 1])
h1.markdown("### 🧪 Lucky Quants Lab")
if 'last_refresh' not in st.session_state: st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
h2.markdown(f"<p style='text-align: right; color: gray; font-size: 0.8em; padding-top: 15px;'>Refreshed: {st.session_state.last_refresh}</p>", unsafe_allow_html=True)
st.divider()

try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing.")
    st.stop()

# --- 2. PERMANENT STORAGE ---
DB_FILE = "lucky_ledger.csv"

def save_data(df):
    df.to_csv(DB_FILE, index=False)

def load_data():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except: pass
    return pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Open Price", "Close Price", "Qty", "Total Premium Collected", "Status"])

if 'journal_data' not in st.session_state:
    st.session_state.journal_data = load_data()

# --- 3. TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER (Untouched) ---
with tab1:
    c1, c2 = st.columns([1, 2])
    t_scan = c1.text_input("Ticker", value="TSM").upper()
    safety_target = c2.slider("Safety %", 70, 99, 90)
    if st.button("🔬 Run Analysis"):
        with st.spinner("Analyzing..."):
            try:
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=t_scan, feed=DataFeed.IEX))
                curr_price = price_data[t_scan].ask_price
                expiry = datetime.now() + timedelta(days=(4 - datetime.now().weekday() + 7) % 7 or 7)
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_scan, expiration_date=expiry.date(), feed=OptionsFeed.INDICATIVE))
                results = []
                for sym, data in chain.items():
                    strike_val = float(sym[-8:]) / 1000
                    if "P" in sym and strike_val < curr_price:
                        iv, t_years = 0.30, 7/365
                        d2 = (np.log(curr_price/strike_val) + (0.04 - 0.5*iv**2)*t_years) / (iv*np.sqrt(t_years))
                        prob_otm = norm.cdf(d2) * 100
                        if prob_otm >= safety_target:
                            mid = (data.bid_price + data.ask_price) / 2
                            results.append({"Strike": strike_val, "Safety %": round(prob_otm, 1), "Premium": round(mid, 2), "Est. Income": round(mid * 100, 2)})
                df_res = pd.DataFrame(results).sort_values("Strike", ascending=False)
                st.write(f"**{t_scan} Price:** ${curr_price:.2f}")
                st.dataframe(df_res, use_container_width=True)
            except Exception as e: st.error(f"Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    # UPDATED FONT & FORMATTING LOGIC
    raw_total_usd = pd.to_numeric(st.session_state.journal_data["Total Premium Collected"], errors='coerce').fillna(0).sum()
    total_usd_int = int(round(raw_total_usd))
    total_hkd_int = int(round(raw_total_usd * 7.8))
    
    # Combined string for uniform font size in the metric
    formatted_value = f"{total_usd_int:,} (~HKD {total_hkd_int:,})"
    st.metric(label="**Total Premium Collected** 🤑", value=formatted_value)

    with st.expander("➕ Log New Trade", expanded=True):
        l1, l2, l3, l4 = st.columns(4)
        ticker_log = l1.text_input("Ticker", value="TSM").upper()
        strat = l2.selectbox("Type", ["Short Put", "Short Call"])
        qty = l3.number_input("Qty", min_value=1, value=1)
        exp = l4.date_input("Expiry", value=datetime.now().date())
        
        l5, l6, l7 = st.columns(3)
        strike = l5.number_input("Strike", value=None, step=0.5, format="%g")
        open_p = l6.number_input("Open Price (Sell)", value=None, step=0.01, format="%.2f")
        close_p = l7.number_input("Close Price (Buy Back)", value=0.00, step=0.01, format="%.2f")
        
        if st.button("🚀 Commit Trade", use_container_width=True):
            if strike is None or open_p is None:
                st.warning("Enter Strike and Open Price.")
            else:
                net_gain = ((float(open_p) - float(close_p)) * 100 * qty) - max(1.05, 0.70 * qty)
                today = datetime.now().date()
                if close_p > 0: status = "Closed"
                elif exp < today: status = "Expired (Win)"
                else: status = "Open / Running"

                new_row = {
                    "Ticker": ticker_log, "Type": strat, "Strike": int(strike) if strike % 1 == 0 else strike, 
                    "Expiry": exp.strftime("%Y-%m-%d"), "Open Price": open_p, "Close Price": close_p, 
                    "Qty": int(qty), "Total Premium Collected": round(net_gain, 2), "Status": status
                }
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                save_data(st.session_state.journal_data)
                st.rerun()

    st.write("### History")
    updated_df = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True, key="ledger_editor")
    
    if not updated_df.equals(st.session_state.journal_data):
        st.session_state.journal_data = updated_df
        save_data(updated_df)

    if st.button("🔄 Recalculate Everything"):
        df = st.session_state.journal_data.copy()
        df["Open Price"] = pd.to_numeric(df["Open Price"], errors='coerce').fillna(0)
        df["Close Price"] = pd.to_numeric(df["Close Price"], errors='coerce').fillna(0)
        df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce').fillna(1)
        
        today = datetime.now().date()
        def update_row(r):
            premium = round(((r["Open Price"] - r["Close Price"]) * 100 * r["Qty"]) - max(1.05, 0.70 * r["Qty"]), 2)
            try:
                exp_date = datetime.strptime(str(r["Expiry"]), "%Y-%m-%d").date()
            except: exp_date = today
            if r["Close Price"] > 0: stat = "Closed"
            elif exp_date < today: stat = "Expired (Win)"
            else: stat = "Open / Running"
            return pd.Series([premium, stat])

        df[["Total Premium Collected", "Status"]] = df.apply(update_row, axis=1)
        st.session_state.journal_data = df
        save_data(df)
        st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
        st.rerun()
