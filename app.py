import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pandas as pd

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="Lucky Lab", page_icon="🧪", layout="wide")
try:
    API_KEY, SECRET_KEY = st.secrets["ALPACA_KEY"], st.secrets["ALPACA_SECRET"]
    stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
except:
    st.error("Alpaca Keys Missing."); st.stop()

# --- 2. LEDGER SETUP ---
if 'journal_data' not in st.session_state:
    st.session_state.journal_data = pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"])

# --- 3. UI ---
st.title("🧪 Lucky Lab: Options Quant")
profits = pd.to_numeric(st.session_state.journal_data["Total Profit"], errors='coerce').fillna(0)
st.metric("Net Profit", f"${profits.sum():,.2f}")

with st.expander("➕ Log New Trade", expanded=True):
    c1, c2, c3 = st.columns(3)
    t_input = c1.text_input("Ticker", value="TSM").upper()
    strat = c2.selectbox("Strategy", ["Short Put", "Short Call"])
    qty = c3.number_input("Qty", min_value=1, value=1)

    c4, c5 = st.columns(2)
    exp_date = c4.date_input("Expiry Date", value=datetime.now().date())
    
    # STRIKE: 1 decimal, 0.1 step, starts empty
    strike = c5.number_input("Strike Price", value=None, step=0.1, format="%.1f", placeholder="Enter Strike (e.g. 345.0)")
    
    if st.button("🚀 Fetch & Commit"):
        if strike is None:
            st.error("Please enter a strike price.")
        else:
            try:
                # OSI Symbol Logic
                flag = "P" if strat == "Short Put" else "C"
                strike_code = f"{int(round(strike * 1000)):08d}"
                exp_code = exp_date.strftime('%y%m%d')
                sym = f"{t_input}{exp_code}{flag}{strike_code}"
                
                mid_price = 0.0
                is_past = exp_date < datetime.now().date()

                if is_past:
                    # HISTORICAL LOOKUP for past dates
                    end_dt = datetime.combine(exp_date, datetime.max.time())
                    start_dt = end_dt - timedelta(days=5)
                    req = OptionBarsRequest(symbol_or_symbols=sym, timeframe=TimeFrame.Day, start=start_dt, end=end_dt)
                    res = opt_client.get_option_bars(req)
                    if sym in res.data and len(res.data[sym]) > 0:
                        mid_price = res.data[sym][-1].close
                else:
                    # LIVE CHAIN for future dates
                    chain = opt_client.get_option_chain(OptionChainRequest(underlying_symbol=t_input, expiration_date=exp_date))
                    if sym in chain:
                        mid_price = (chain[sym].bid_price + chain[sym].ask_price) / 2

                if mid_price > 0:
                    # Calculation
                    final_comm = max(1.05, 0.70 * qty)
                    cash_premium = round(mid_price * 100, 2)
                    net_profit = (cash_premium * qty) - final_comm
                    
                    new_row = {
                        "Ticker": t_input, "Type": strat, "Strike": round(strike, 1), 
                        "Expiry": exp_date.strftime("%Y-%m-%d"),
                        "Premium": cash_premium, "Qty": int(qty),
                        "Commission": round(final_comm, 2), "Total Profit": round(net_profit, 2)
                    }
                    st.session_state.journal_data = pd.concat([st.session_state.journal_data, pd.DataFrame([new_row])], ignore_index=True)
                    st.rerun()
                else:
                    st.error(f"No pricing data found for {sym} on {exp_date}. It may have expired worthless or be invalid.")
            except Exception as e:
                st.error(f"Alpaca Error: {e}")

# --- 4. TABLE ---
st.session_state.journal_data = st.data_editor(st.session_state.journal_data, num_rows="dynamic", use_container_width=True)
if st.button("🗑️ Reset Ledger"):
    st.session_state.journal_data = pd.DataFrame(columns=["Ticker", "Type", "Strike", "Expiry", "Premium", "Qty", "Commission", "Total Profit"])
    st.rerun()
