import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
import numpy as np
from scipy.stats import norm
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & BRANDING ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")

st.html("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e1e4e8; }
    h1 { color: #1e3a8a; font-family: 'Helvetica Neue', sans-serif; }
    [data-testid="stExpander"] { background-color: #ffffff; border-radius: 10px; }
    </style>
""")

st.title("🧪 Lucky Lab: Options Quant")

# --- 2. AUTHENTICATION ---
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except Exception as e:
    st.error("⚠️ Lucky Lab Keys Missing. Add ALPACA_KEY and ALPACA_SECRET to Streamlit Secrets.")
    st.stop()

# --- 3. CREATE TABS ---
tab1, tab2 = st.tabs(["🔍 Strategy Optimizer", "📓 Lucky Ledger"])

# --- TAB 1: STRATEGY OPTIMIZER ---
with tab1:
    st.subheader("Naked Put Scanner")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    ticker = col_a.text_input("Ticker Symbol", value="SPY").upper()
    safety_threshold = col_b.slider("Minimum Safety %", 70, 99, 90)
    min_vol = col_c.number_input("Min Volume", value=0)

    if st.button("🔬 Run Lab Analysis"):
        with st.spinner(f"Analyzing {ticker}..."):
            try:
                price_req = StockLatestQuoteRequest(symbol_or_symbols=ticker, feed=DataFeed.IEX)
                price_data = stock_client.get_stock_latest_quote(price_req)
                current_price = price_data[ticker].ask_price
                st.metric(f"{ticker} Live Ask", f"${current_price:.2f}")

                today = datetime.now()
                days_to_fri = (4 - today.weekday() + 7) % 7 or 7
                expiry = today + timedelta(days=days_to_fri)
                
                chain_req = OptionChainRequest(underlying_symbol=ticker, expiration_date=expiry.date())
                chain = opt_client.get_option_chain(chain_req)
                
                results = []
                for symbol, data in chain.items():
                    if "P" in symbol and data.strike < current_price:
                        iv = data.implied_volatility or 0.18
                        t_years = max(days_to_fri, 1) / 365
                        d2 = (np.log(current_price/data.strike) + (0.042 - 0.5*iv**2)*t_years) / (iv*np.sqrt(t_years))
                        prob_otm = norm.cdf(d2) * 100
                        
                        if prob_otm >= safety_threshold and (data.volume or 0) >= min_vol:
                            mid_price = (data.bid_price + data.ask_price) / 2
                            m_req = max((0.20*current_price - (current_price-data.strike) + mid_price)*100, (0.10*data.strike)*100)
                            ann_roc = (mid_price*100/m_req) * (365/days_to_fri) * 100
                            results.append({
                                "Strike": data.strike, "Safety %": round(prob_otm, 1),
                                "Premium": f"${mid_price:.2f}", "Ann. ROC %": round(ann_roc, 1),
                                "Volume": data.volume, "Margin Req": int(m_req)
                            })
                if results:
                    st.dataframe(pd.DataFrame(results).sort_values("Ann. ROC %", ascending=False), use_container_width=True)
                else:
                    st.warning("No matches found. Try lower safety or volume.")
            except Exception as e:
                st.error(f"Lab Error: {e}")

# --- TAB 2: LUCKY LEDGER ---
with tab2:
    st.subheader("📓 The Lucky Ledger")

    # Initialize dataframe structure
    if 'journal_data' not in st.session_state:
        st.session_state.journal_data = pd.DataFrame(columns=["Date", "Ticker", "Strike", "Premium", "Qty", "Total Credit"])

    # 1. TOP METRICS (Visible even if data is 0)
    m1, m2 = st.columns(2)
    if not st.session_state.journal_data.empty:
        df_metrics = st.session_state.journal_data.copy()
        df_metrics['Date'] = pd.to_datetime(df_metrics['Date'])
        overall_p = df_metrics["Total Credit"].astype(float).sum()
        seven_days_ago = datetime.now() - timedelta(days=7)
        weekly_p = df_metrics[df_metrics['Date'] >= seven_days_ago]["Total Credit"].astype(float).sum()
    else:
        overall_p = 0.0
        weekly_p = 0.0

    m1.metric("Overall Profit", f"${overall_p:,.2f}")
    m2.metric("Last 7 Days Profit", f"${weekly_p:,.2f}")
    st.divider()

    # 2. ENTRY FORM
    with st.expander("➕ Log New Trade", expanded=True):
        c1, c2, c3 = st.columns(3)
        new_ticker = c1.text_input("Ticker", value="SPY", key="j_ticker").upper()
        weeks_out = c2.selectbox("Weeks to Expiry", options=[1, 2, 3, 4, 5])
        qty = c3.number_input("Qty", min_value=1, value=1)
        
        if st.button("🔍 Fetch & Stage Trade"):
            try:
                target_expiry = datetime.now() + timedelta(days=(4 - datetime.now().weekday() + (7 * weeks_out)) % (7 * weeks_out) or (7 * weeks_out))
                price_data = stock_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=new_ticker, feed=DataFeed.IEX))
                curr_p = price_data[new_ticker].ask_price
                chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=new_ticker, expiration_date=target_expiry.date()))
                
                staged_found = False
                for symbol, data in chain.items():
                    if "P" in symbol and data.strike < (curr_p * 0.95):
                        p_val = (data.bid_price + data.ask_price) / 2
                        if p_val == 0: p_val = getattr(data, 'last_price', 0.05)
                        
                        st.session_state.staged = {
                            "Date": datetime.now().strftime("%Y-%m-%d"), 
                            "Ticker": new_ticker,
                            "Strike": data.strike, 
                            "Premium": float(p_val), 
                            "Qty": int(qty),
                            "Total Credit": round(float(p_val) * qty * 100, 2)
                        }
                        st.info(f"Staged: {new_ticker} ${data.strike}P | Total: ${st.session_state.staged['Total Credit']}")
                        staged_found = True
                        break
                if not staged_found:
                    st.warning("No safe puts found for this date.")
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    # Commit button logic
    if 'staged' in st.session_state:
        if st.button("📥 Commit Trade to Ledger"):
            st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([st.session_state.staged])], ignore_index=True)
            del st.session_state.staged
            st.rerun()

    # 3. THE DATA TABLE
    st.write("### Your Trade History")
    edited_df = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)
    st.session_state.journal_data = edited_df
