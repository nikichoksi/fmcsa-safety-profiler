import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from pathlib import Path

# Use the local database when present; the deployed app reads the exported Parquet
DB_PATH = "database/fmcsa.db"
PARQUET_PATH = "data/safety_scores.parquet"

st.set_page_config(
    page_title="FMCSA Safety Risk Profiler",
    page_icon="",
    layout="wide"
)

st.title("FMCSA Carrier Safety Risk Profiler")
st.markdown("Analyze motor carrier safety performance using official FMCSA data.")

# Load from pre-computed table (FAST)
@st.cache_data
def load_data():
    if Path(DB_PATH).exists():
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM safety_scores", conn)
        conn.close()
    else:
        df = pd.read_parquet(PARQUET_PATH)
    return df

df = load_data()

# Sidebar filters
st.sidebar.header("Filters")

tier_filter = st.sidebar.multiselect(
    "Risk Tier",
    options=sorted(df['risk_tier'].unique()),
    default=sorted(df['risk_tier'].unique())
)

peer_filter = st.sidebar.multiselect(
    "Peer Group",
    options=sorted(df['peer_group'].unique()),
    default=sorted(df['peer_group'].unique())
)

state_filter = st.sidebar.multiselect(
    "State",
    options=sorted(df['phy_state'].dropna().unique()),
    default=[]
)

min_fleet, max_fleet = st.sidebar.slider(
    "Fleet Size (Power Units)",
    min_value=int(df['total_power_units'].min()),
    max_value=int(df['total_power_units'].max()),
    value=(5, 1000)
)

# Apply filters
filtered = df[
    (df['risk_tier'].isin(tier_filter)) &
    (df['peer_group'].isin(peer_filter)) &
    (df['total_power_units'] >= min_fleet) &
    (df['total_power_units'] <= max_fleet)
]

if state_filter:
    filtered = filtered[filtered['phy_state'].isin(state_filter)]

# KPI Row
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Carriers", f"{len(filtered):,}")
col2.metric("Critical Risk", f"{len(filtered[filtered['risk_tier'] == 'Critical']):,}")
col3.metric("Avg OOS Rate", f"{filtered['oos_rate_raw'].mean():.1%}")
col4.metric("Avg Severity", f"{filtered['severity_rate_raw'].mean():.2f}")
col5.metric("Avg Crash Rate", f"{filtered['crash_rate_raw'].mean():.2f}")

st.divider()

# Charts Row
left, right = st.columns(2)

with left:
    st.subheader("Risk Tier Distribution")
    tier_counts = filtered['risk_tier'].value_counts().reindex(['Low', 'Medium', 'High', 'Critical'], fill_value=0)
    fig1 = px.bar(
        x=tier_counts.index,
        y=tier_counts.values,
        color=tier_counts.index,
        color_discrete_map={'Low': '#2ecc71', 'Medium': '#f1c40f', 'High': '#e67e22', 'Critical': '#e74c3c'},
        labels={'x': 'Risk Tier', 'y': 'Number of Carriers'}
    )
    fig1.update_layout(showlegend=False)
    st.plotly_chart(fig1, width='stretch')

with right:
    st.subheader("OOS Rate by Peer Group")
    peer_order = ['Small Fleet', 'Medium Fleet', 'Large Fleet', 'Extra Large Fleet']
    peer_oos = filtered.groupby('peer_group')['oos_rate_raw'].mean().reindex(peer_order).dropna().reset_index()
    fig2 = px.bar(
        peer_oos, x='peer_group', y='oos_rate_raw', color='peer_group',
        labels={'peer_group': 'Peer Group', 'oos_rate_raw': 'Avg OOS Rate'}
    )
    fig2.update_layout(showlegend=False, yaxis_tickformat='.0%')
    st.plotly_chart(fig2, width='stretch')

# Scatter plot
st.subheader("Fleet Size vs. Safety Performance")
fig3 = px.scatter(
    filtered,
    x='total_power_units',
    y='oos_rate_raw',
    color='risk_tier',
    size='inspections',
    hover_data=['legal_name', 'phy_state', 'severity_rate_raw', 'crash_rate_raw'],
    color_discrete_map={'Low': '#2ecc71', 'Medium': '#f1c40f', 'High': '#e67e22', 'Critical': '#e74c3c'},
    log_x=True,
    labels={'total_power_units': 'Power Units (log scale)', 'oos_rate_raw': 'OOS Rate', 'severity_rate_raw': 'Severity Rate',
            'crash_rate_raw': 'Crash Rate', 'risk_tier': 'Risk Tier'}
)
fig3.update_xaxes(tickvals=[1, 10, 100, 1000, 10000, 100000], tickformat=',d', minor_showgrid=False)
fig3.update_yaxes(tickformat='.0%')
st.plotly_chart(fig3, width='stretch')

# Data table
st.subheader("Carrier Details")
display_cols = ['legal_name', 'phy_state', 'peer_group', 'total_power_units',
                'inspections', 'violations', 'oos_rate_raw', 'severity_rate_raw',
                'crash_rate_raw', 'fatalities', 'risk_tier']
# Show observed rates; rank by the shrunk rates used for tiering so carriers
# with only a few inspections don't crowd the top
st.dataframe(
    filtered.sort_values('oos_rate', ascending=False)[display_cols],
    width='stretch',
    hide_index=True
)

# Download button
csv = filtered[display_cols].to_csv(index=False)
st.download_button(
    label="Download Filtered Data as CSV",
    data=csv,
    file_name="fmcsa_safety_scores.csv",
    mime="text/csv"
)