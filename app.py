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

# Custom CSS for a "prettier" look
st.markdown("""
    <style>
    .stMetric { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border: 1px solid #dcdcdc; }
    div[data-testid="stExpander"] { border: 1px solid #e6e9ef; border-radius: 10px; }
    .stButton>button { border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

st.markdown("### 🧪 Lucky Quants Lab")
st.divider()

try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing in Secrets.")
    st.stop()

# --- 2. PERMANENT STORAGE (AUTO-SAVE) ---
DB_FILE = "lucky_ledger.csv"

def save_data(df):
    df.to_csv(DB_FILE, index=False)

def load_data():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except:
            pass
    return pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Total Premium Collected"])

if 'journal_data' not in st.session_state:
    st.session_state.journal_data = load_data()

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --- 3. TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER (Untouched) ---
with tab1:
    st.subheader("Naked Put Scanner")
    c1, c2, c3 = st.columns(3)
    t_scan = c1.text_input("Ticker to Scan", value="TSM").upper()
    safety_target = c2.slider("Min Safety % (OTM)", 70, 99, 90)
    
    if st.button("🔬 Run Lab Analysis"):
        with st.spinner(f"Analyzing {t_scan}..."):
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
                            results.append({
                                "Strike": strike_val, 
                                "Safety %": round(prob_otm, 1), 
                                "Premium (Per Share)": round(mid, 2), 
                                "Est. Income": round(mid * 100, 2)
                            })
                
                df_res = pd.DataFrame(results).sort_values("Strike", ascending=False)
                st.write(f"**Current {t_scan} Price:** ${curr_price:.2f}")
                st.dataframe(df_res, use_container_width=True)
            except Exception as e:
                st.error(f"Scanner Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    # --- METRICS SECTION ---
    raw_total_usd = pd.to_numeric(st.session_state.journal_data["Total Premium Collected"], errors='coerce').fillna(0).sum()
    total_usd_int = int(round(raw_total_usd))
    total_hkd_int = int(round(raw_total_usd * 7.8))
    
    st.metric(label="**Total Premium Collected** 🤑", value=f"${total_usd_int:,} (${total_hkd_int:,} HKD)")
    st.divider()

    # --- INPUT SECTION ---
    with st.expander("➕ Log New Trade", expanded=True):
        l1, l2, l3, l4 = st.columns(4)
        ticker_log = l1.text_input("Ticker", value="TSM", key="log_ticker").upper()
        strat = l2.selectbox("Type", ["Short Put", "Short Call"])
        qty = l3.number_input("Qty", min_value=1, value=1)
        exp = l4.date_input("Expiry", value=datetime.now().date())
        
        l5, l6 = st.columns(2)
        strike = l5.number_input("Strike Price", value=None, step=0.5, format="%g", placeholder="Strike (e.g. 345)")
        price_per_share = l6.number_input("Price per Share", value=None, step=0.01, format="%.2f", placeholder="Fill Price (e.g. 0.59)")
        
        if st.button("🚀 Commit & Calculate", use_container_width=True):
            if strike is None or price_per_share is None:
                st.warning("Please fill in both Strike and Price.")
            else:
                cash_premium = round(float(price_per_share) * 100, 2)
                comm = max(1.05, 0.70 * qty)
                net_total = (cash_premium * qty) - comm
                
                display_strike = int(strike) if strike % 1 == 0 else strike
                
                new_row = {
                    "Ticker": ticker_log, "Type": strat, "Strike": display_strike, 
                    "Expiry": exp.strftime("%Y-%m-%d"),
                    "Premium": cash_premium, "Qty": int(qty),
                    "Total Premium Collected": round(net_total, 2)
                }
                st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                save_data(st.session_state.journal_data)
                st.rerun()

    # --- TABLE SECTION ---
    st.write("### History")
    
    # Red Delete Button (Aligned Left)
    if st.button("🗑️ Delete Last Entry", type="secondary", help="Removes the most recent trade"):
        if not st.session_state.journal_data.empty:
            st.session_state.journal_data = st.session_state.journal_data.drop(st.session_state.journal_data.index[-1])
            save_data(st.session_state.journal_data)
            st.rerun()

    updated_df = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True, key="ledger_editor")
    
    if not updated_df.equals(st.session_state.journal_data):
        st.session_state.journal_data = updated_df
        save_data(updated_df)

    # --- FOOTER ---
    st.divider()
    c_btn, c_time = st.columns([1, 1])
    with c_btn:
        if st.button("🔄 Refresh & Recalculate"):
            df = st.session_state.journal_data.copy()
            df["Premium"] = pd.to_numeric(df["Premium"], errors='coerce').fillna(0)
            df["Qty"] = pd.to_numeric(df["Qty"], errors='coerce').fillna(1)
            df["Total Premium Collected"] = df.apply(
                lambda row: round((row["Premium"] * row["Qty"]) - max(1.05, 0.70 * row["Qty"]), 2), 
                axis=1
            )
            st.session_state.journal_data = df
            save_data(df)
            st.session_state.last_refresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.rerun()
    
    with c_time:
        st.markdown(f"<p style='text-align: right; color: gray;'>Last Refreshed: {st.session_state.last_refresh}</p>", unsafe_allow_html=True)
