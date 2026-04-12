import streamlit as st
import pandas as pd
import altair as alt
import time

st.set_page_config(page_title="Energy Monitor", layout="wide")
st.title("⚡ Energy Dashboard")

conn = st.connection("neon", type="sql")

COST_PER_KWH = 0.15

# --- FETCH DATA ---
df = conn.query("""
SELECT timestamp, voltage, current 
FROM readings 
ORDER BY timestamp ASC
""", ttl="0s")

alerts_df = conn.query("""
SELECT id, description, time_stamp 
FROM alerts 
ORDER BY time_stamp DESC
""", ttl="0s")

if df.empty:
    st.stop()

df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('America/Moncton')

# --- CALCULATIONS ---
df['power'] = df['voltage'] * df['current']

df['dt'] = df['timestamp'].diff().dt.total_seconds().fillna(1)
df['energy_Wh'] = (df['power'] * df['dt']) / 3600

# --- DAILY CALC ---
df['date'] = df['timestamp'].dt.date

today = df['date'].max()
today_df = df[df['date'] == today]

daily_energy = today_df['energy_Wh'].sum()
daily_cost = (daily_energy / 1000) * COST_PER_KWH

lifetime_energy = df['energy_Wh'].sum()
lifetime_cost = (lifetime_energy / 1000) * COST_PER_KWH

# --- DAILY SAVE (OVERWRITE MODE) ---
yesterday = today - pd.Timedelta(days=1)
yesterday_df = df[df['date'] == yesterday]

if not yesterday_df.empty:
    y_energy = yesterday_df['energy_Wh'].sum()
    y_cost = (y_energy / 1000) * COST_PER_KWH

    conn.query(f"""
    INSERT INTO daily_history (date, total_energy_wh, total_cost)
    VALUES ('{yesterday}', {y_energy}, {y_cost})
    ON CONFLICT (date)
    DO UPDATE SET
        total_energy_wh = EXCLUDED.total_energy_wh,
        total_cost = EXCLUDED.total_cost;
    """)

# --- CHART ---
def make_chart(data, y, title):
    return alt.Chart(data).mark_line().encode(
        x='timestamp:T',
        y=alt.Y(y, scale=alt.Scale(zero=False))
    ).properties(height=250, title=title)

def filter_df(data, minutes):
    cutoff = data['timestamp'].max() - pd.Timedelta(minutes=minutes)
    return data[data['timestamp'] >= cutoff]

time_options = {"5m":5, "15m":15, "1h":60, "6h":360, "24h":1440}

# --- GRAPHS ---
g1, g2 = st.columns(2)

with g1:
    st.subheader("Voltage")
    sel = st.radio("", time_options.keys(), horizontal=True, key="v")
    st.altair_chart(make_chart(filter_df(df, time_options[sel]), 'voltage', "Voltage"), use_container_width=True)

with g2:
    st.subheader("Current")
    sel = st.radio("", time_options.keys(), horizontal=True, key="c")
    st.altair_chart(make_chart(filter_df(df, time_options[sel]), 'current', "Current"), use_container_width=True)

g3, g4 = st.columns(2)

with g3:
    st.subheader("Power")
    sel = st.radio("", time_options.keys(), horizontal=True, key="p")
    st.altair_chart(make_chart(filter_df(df, time_options[sel]), 'power', "Power"), use_container_width=True)

with g4:
    st.subheader("Daily Energy")
    today_chart = today_df.copy()
    today_chart['energy_cum'] = today_chart['energy_Wh'].cumsum()
    st.altair_chart(make_chart(today_chart, 'energy_cum', "Energy Today (Wh)"), use_container_width=True)

# --- SUMMARY ---
st.write("---")

c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
    <div style="padding:20px; border-radius:10px; background:#111;">
        <h3>Today's Energy</h3>
        <h1>{daily_energy:.2f} Wh</h1>
    </div>
    """, unsafe_allow_html=True)

with c2:
    mode = st.toggle("Show Lifetime Cost", value=False)
    
    if mode:
        value = lifetime_cost
        label = "Lifetime Cost"
    else:
        value = daily_cost
        label = "Today's Cost"
    
    st.markdown(f"""
    <div style="padding:20px; border-radius:10px; background:#111;">
        <h3>{label}</h3>
        <h1>${value:.2f}</h1>
    </div>
    """, unsafe_allow_html=True)

# --- ALERTS ---
st.write("---")
st.subheader("Alerts")

if alerts_df.empty:
    st.info("No alerts")
else:
    for _, row in alerts_df.iterrows():
        col1, col2 = st.columns([10,1])
        
        with col1:
            st.markdown(f"""
            <div style="padding:10px; margin-bottom:5px; background:#222; border-radius:8px;">
                <b>{row['description']}</b><br>
                <small>{row['time_stamp']}</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            if st.button("X", key=row['id']):
                conn.query(f"DELETE FROM alerts WHERE id = '{row['id']}'")
                st.rerun()

# --- EXPORT ---
st.write("---")
st.subheader("📥 Export Energy Report")

daily_hist = conn.query("SELECT * FROM daily_history ORDER BY date ASC;", ttl="0s")

df_daily = df.groupby('date').agg({'energy_Wh':'sum'}).reset_index()
df_daily['cost'] = (df_daily['energy_Wh']/1000)*COST_PER_KWH

merged = pd.merge(df_daily, daily_hist, on='date', how='outer', suffixes=('_calc','_stored'))

st.download_button(
    "Download CSV",
    merged.to_csv(index=False).encode('utf-8'),
    f"energy_report_{time.strftime('%Y%m%d_%H%M%S')}.csv",
    "text/csv",
    use_container_width=True
)

# --- REFRESH ---
time.sleep(1)
st.rerun()