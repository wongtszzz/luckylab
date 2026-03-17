import streamlit as st
from alpaca.data.historical import OptionHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, StockLatestQuoteRequest
import numpy as np
from scipy.stats import norm
import pandas as pd
from datetime import datetime, timedelta

# --- 1. SETUP & SECRETS ---
try:
    API_KEY = st.secrets["ALPACA_KEY"]
    SECRET_KEY = st.secrets["ALPACA_SECRET"]
except:
    st.error("API Keys missing! Please add ALPACA_KEY and ALPACA_SECRET to Streamlit Secrets.")
    st.stop()

stock_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
opt_client = OptionHistoricalDataClient(API_KEY, SECRET_KEY)

st.set_page_config(page_title="Short Put Command Center", layout="wide")
st.title("🛡️ Short Put Optimizer & Journal")

# --- 2. TABBED INTERFACE ---
tab1, tab2 = st.tabs(["🔍 Live Put Scanner", "📓 My Trade Journal"])

with tab1:
    st.header("Scan for 90%+ Safety Puts")
    ticker_input = st.text_input("Enter Ticker", value="SPY").upper()
    
    if st.button("Run Alpaca Scan"):
        try:
            # Get Live Price
            s_req = StockLatestQuoteRequest(symbol_or_symbols=ticker_input)
            current_price = stock_client.get_stock_latest_quote(s_req)[ticker_input].ask_price
            st.metric(f"{ticker_input} Live Price", f"${current_price:.2f}")

            # Get Nearest Friday Expiry
            today = datetime.now()
            days_to_fri = (4 - today.weekday() + 7) % 7
            if days_to_fri == 0: days_to_fri = 7
            expiry = today + timedelta(days=days_to_fri)
            
            # Request Option Chain
            o_req = OptionChainRequest(underlying_symbol=ticker_input, expiration_date=expiry.date())
            chain = opt_client.get_option_chain(o_req)
            
            # Logic: Filter and Rank
            matches = []
            T = max(days_to_fri, 1) / 365
            r = 0.045 # 4.5% Rate
            
            for strike, data in chain.items():
                if data.type == 'put' and data.strike < current_price:
                    iv = data.implied_volatility or 0.25
                    vol = data.volume or 0
                    
                    # Probability Math (Safety Check)
                    d2 = (np.log(current_price / data.strike) + (r - 0.5 * iv**2) * T) / (iv * np.sqrt(T))
                    prob = norm.cdf(d2) * 100
                    
                    # FILTERS: 90% Safety + Volume > 10
                    if prob >= 90 and vol >= 10:
                        mid_price = (data.bid_price + data.ask_price) / 2
                        # IBKR Margin Estimate (Max of 20% or 10% rule)
                        m_req = max((0.20 * current_price - (current_price - data.strike) + mid_price) * 100, (0.10 * data.strike) * 100)
                        roc = (mid_price * 100 / m_req) * (365 / days_to_fri) * 100
                        
                        matches.append({
                            "Strike": data.strike, "Safety": f"{prob:.1f}%", 
                            "Volume": vol, "Premium": f"${mid_price:.2f}", 
                            "Ann. ROC": roc, "Margin Req": f"${m_req:.0f}"
                        })

            if matches:
                res_df = pd.DataFrame(matches).sort_values("Ann. ROC", ascending=False).head(5)
                st.write(f"### Best 90% Safety Strikes (Exp: {expiry.date()})")
                st.dataframe(res_df, use_container_width=True)
            else:
                st.warning("No strikes found with 90% safety and volume > 10.")
                
        except Exception as e:
            st.error(f"Scan failed: {e}")

with tab2:
    st.header("Manual Trade Journal")
    st.info("Input your trades below to track your performance.")
    
    # Initialize session state for trades
    if 'journal' not in st.session_state:
        st.session_state.journal = pd.DataFrame(columns=[
            "Ticker", "Strike", "Premium", "Qty", "Entry Date", "Status", "Total P/L ($)"
        ])

    # Manual Entry Table
    edited_df = st.data_editor(
        st.session_state.journal, 
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Status": st.column_config.SelectboxColumn(options=["Open", "Closed"]),
            "Entry Date": st.column_config.DateColumn(),
            "Total P/L ($)": st.column_config.NumberColumn(format="$%d")
        }
    )
    st.session_state.journal = edited_df

    # --- JOURNAL ANALYTICS ---
    if not edited_df.empty:
        df = edited_df.copy()
        df['Entry Date'] = pd.to_datetime(df['Entry Date'])
        
        # Calculate Totals
        total_p = df['Total P/L ($)'].sum()
        
        # Weekly/Monthly Logic
        now = datetime.now()
        this_week = df[df['Entry Date'] > (now - timedelta(days=7))]['Total P/L ($)'].sum()
        this_month = df[df['Entry Date'].dt.month == now.month]['Total P/L ($)'].sum()
        
        # Best/Worst
        best_trade = df.loc[df['Total P/L ($)'].idxmax()] if not df.empty else None
        worst_trade = df.loc[df['Total P/L ($)'].idxmin()] if not df.empty else None

        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Overall Profit", f"${total_p:,.2f}")
        m2.metric("Weekly Profit", f"${this_week:,.2f}")
        m3.metric("Monthly Profit", f"${this_month:,.2f}")

        st.divider()
        c1, c2 = st.columns(2)
        if best_trade is not None:
            c1.success(f"🏆 **Best Trade:** {best_trade['Ticker']} ${best_trade['Strike']}P (+${best_trade['Total P/L ($)']})")
        if worst_trade is not None:
            c2.error(f"📉 **Worst Trade:** {worst_trade['Ticker']} ${worst_trade['Strike']}P (${worst_trade['Total P/L ($)']})")
