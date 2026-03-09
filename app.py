import streamlit as st
import requests
import numpy as np
from scipy.stats import norm
import yfinance as yf
from datetime import datetime

# --- CONFIG ---
# PASTE YOUR FINNHUB KEY BETWEEN THE QUOTES BELOW
FINNHUB_KEY = "d6ndtshr01qodk5vcbt0d6ndtshr01qodk5vcbtg"

st.set_page_config(page_title="Weekly Put Picker", layout="centered")
st.title("⚡ Weekly Short Put Dash (Pro)")

# --- Sidebar: Ticker ---
ticker_symbol = st.sidebar.text_input("Enter Ticker", value="SPY").upper()

@st.cache_data(ttl=60) # Live price refreshes every 60 seconds
def get_live_price(symbol):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        r = requests.get(url).json()
        return float(r['c'])
    except:
        return None

# --- Main Logic ---
price = get_live_price(ticker_symbol)

if price and price > 0:
    st.subheader(f"{ticker_symbol} @ ${price:.2f}")
    
    # Calculate the 2 Strikes (OTM)
    # We choose 2% and 4% below current price for the "Weekly" feel
    strike1 = round(price * 0.98, 0)
    strike2 = round(price * 0.96, 0)
    
    st.info("📅 **Nearest Expiration Analysis**")
    
    for K in [strike1, strike2]:
        # Estimation Logic (Since we are using free data)
        # In 2026, for a 30-day put, premium is roughly 1-2% of strike
        # We adjust this based on a standard 30% IV assumption
        iv = 0.25 # Estimated IV
        T = 7/365 # 1 Week
        r = 0.045 # 4.5% Rate
        
        # Black-Scholes Probability of OTM
        d2 = (np.log(price / K) + (r - 0.5 * iv**2) * T) / (iv * np.sqrt(T))
        prob_otm = norm.cdf(d2) * 100
        
        # Estimate Premium (Simplified)
        est_premium = max(0.10, (price - K) * 0.45) 

        with st.container():
            c1, c2, c3 = st.columns(3)
            c1.metric("Strike", f"${K}")
            c2.metric("Est. Premium", f"${est_premium:.2f}")
            c3.metric("Prob. OTM", f"{prob_otm:.1f}%")
            
            # Risk/Reward Bar
            bar_color = "green" if prob_otm > 85 else "blue"
            st.progress(int(prob_otm))
            st.caption(f"Breakeven: ${K - est_premium:.2f} | Capital Required: ${K*100:,.0f}")
            st.divider()

else:
    st.error("⚠️ Invalid Ticker or API Key.")
    st.write("Please check that your Finnhub Key is pasted correctly in the code.")

st.caption("Using Finnhub API for Live Price & Probability Modeling.")
