import streamlit as st
import numpy as np
from scipy.stats import norm
import yfinance as yf

# --- Page Config ---
st.set_page_config(page_title="Short Put Strategy Lab", layout="wide")

st.title("🛡️ Short Put Strategy & Risk Lab")
st.markdown("Focused on **Probability**, **Capital Efficiency**, and **Risk Mitigation**.")

# --- Sidebar: Market Data ---
st.sidebar.header("1. Market Context")
ticker_symbol = st.sidebar.text_input("Stock Ticker", value="SPY").upper()

@st.cache_data(ttl=300)
def fetch_market_data(symbol):
    try:
        t = yf.Ticker(symbol)
        return t.fast_info['last_price'], t.info.get('longName', symbol)
    except:
        return 100.0, "Manual Entry"

live_price, co_name = fetch_market_data(ticker_symbol)
st.sidebar.subheader(f"{co_name}")

# --- Sidebar: Trade Parameters ---
st.sidebar.header("2. Position Details")
S = st.sidebar.number_input("Current Stock Price ($)", value=float(live_price))
K = st.sidebar.number_input("Strike Price ($)", value=float(live_price * 0.95))
premium = st.sidebar.number_input("Premium per Share ($)", value=1.50)
T_days = st.sidebar.number_input("Days to Expiration", value=30, min_value=1)
iv = st.sidebar.slider("Implied Volatility (IV %)", 10.0, 150.0, 30.0) / 100
r = 0.045 # 4.5% Risk Free Rate

# --- Calculations ---
T = T_days / 365.0
# Standard deviation for the move (Expected Move)
expected_move_std = S * iv * np.sqrt(T)

# Black-Scholes for Probability
d2 = (np.log(S / K) + (r - 0.5 * iv**2) * T) / (iv * np.sqrt(T))
prob_otm = norm.cdf(d2) * 100
breakeven = K - premium

# Margin & Returns
capital_required = K * 100 # Cash Secured Requirement
net_profit = premium * 100
raw_return = (net_profit / (capital_required - net_profit)) * 100
annualized_return = raw_return * (365 / T_days)

# --- UI: Top Level Metrics ---
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prob. of Max Profit", f"{prob_otm:.1f}%")
c2.metric("Breakeven Price", f"${breakeven:.2f}")
c3.metric("Return on Capital", f"{raw_return:.2f}%")
c4.metric("Annualized Return", f"{annualized_return:.1f}%")

# --- UI: Probability & Risk Analysis ---
st.divider()
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("🎯 Probability Analysis")
    st.write("Where is the stock likely to be at expiration?")
    
    # Probability of touching various levels
    p_hit_strike = (1 - norm.cdf(d2)) * 100 # Simple estimate
    p_below_be = (1 - norm.cdf((np.log(S / breakeven) + (r - 0.5 * iv**2) * T) / (iv * np.sqrt(T)))) * 100
    
    st.write(f"• Probability of Stock < Strike (${K}): **{p_hit_strike:.1f}%**")
    st.write(f"• Probability of Loss (Stock < ${breakeven:.2f}): **{p_below_be:.1f}%**")
    st.write(f"• Expected Move (+/-): **${expected_move_std:.2f}**")

with right_col:
    st.subheader("💰 Capital & Margin")
    st.write("How much 'buying power' is at stake?")
    st.write(f"• Cash-Secured Requirement: **${capital_required:,.2f}**")
    st.write(f"• Net Premium Collected: **${net_profit:,.2f}**")
    
    # Danger Warning
    if p_hit_strike > 40:
        st.warning("⚠️ High Risk: Over 40% chance of assignment.")
    elif p_hit_strike < 15:
        st.success("✅ Conservative: High probability of keeping premium.")
    else:
        st.info("ℹ️ Moderate: Standard income-generation setup.")

# --- Price Shock Simulator ---
st.divider()
st.subheader("📉 The 'Crash' Simulator")
st.write("What happens to your account if the stock drops *instantly* tomorrow?")

shocks = [-2, -5, -10, -15, -20]
shock_rows = []
for s in shocks:
    new_price = S * (1 + s/100)
    # Estimate loss if assigned at new price
    loss_at_exp = (breakeven - new_price) * 100 if new_price < breakeven else 0
    shock_rows.append({
        "Price Drop": f"{s}%",
        "New Stock Price": f"${new_price:.2f}",
        "P&L at Expiration": f"-${abs(loss_at_exp):,.2f}" if loss_at_exp < 0 else "Still Profitable"
    })

st.table(shock_rows)

st.caption("Note: P&L at Expiration assumes you hold the position until the end and are assigned at the strike.")
