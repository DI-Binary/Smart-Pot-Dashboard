import streamlit as st
import json
from datetime import datetime
import pandas as pd
import altair as alt
import paho.mqtt.client as mqtt
from streamlit_autorefresh import st_autorefresh

# ================== KONFIGURASI ==================
BROKER = "broker.hivemq.com"
PORT = 1883

TOPIC_SENSOR = "sic7/stage4/DI-Binary/sensor"
TOPIC_PRED = "sic7/stage4/DI-Binary/prediction"
TOPIC_OUTPUT = "sic7/stage4/DI-Binary/output"

# ================== KONFIG HALAMAN ==================
st.set_page_config(
    page_title="Dashboard Smart Pot",
    layout="wide"
)

# ================== CSS CUSTOM ==================
st.markdown("""
<style>
/* Kurangi jarak atas seluruh halaman */
div.block-container {
    padding-top: 0.8rem;  /* default 2-3rem, ini lebih rapat */
}

/* Kurangi jarak antar metric / header */
h1, h2, h3 {
    margin-top: 0.5rem;
    margin-bottom: 0.3rem;
}
</style>
""", unsafe_allow_html=True)

# ================== BUFFER SHARED ==================
class MQTTBuffer:
    def __init__(self):
        self.sensor = None
        self.prediction = "-"
        self.queue = []
        self.output = {
            "led_color": "OFF",
            "buzzer_on": False
        }

# ================== RESOURCE MQTT ==================
@st.cache_resource
def start_mqtt():
    buffer = MQTTBuffer()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe([(TOPIC_SENSOR, 0), (TOPIC_PRED, 0), (TOPIC_OUTPUT, 0)])
            print("MQTT Tersambung")
        else:
            print("Koneksi MQTT gagal")

    def on_message(client, userdata, msg):
        payload = msg.payload.decode()
        now = datetime.now()

        if msg.topic == TOPIC_SENSOR:
            try:
                data = json.loads(payload)
                buffer.sensor = {
                    "time": now,
                    "temperature": data.get("temp"),
                    "humidity": data.get("hum"),
                    "soil": data.get("soil")
                }
                buffer.queue.append({
                    "time": now,
                    "temperature": data.get("temp"),
                    "humidity": data.get("hum"),
                    "soil": data.get("soil"),
                    "prediction": buffer.prediction
                })
            except Exception as e:
                print("Gagal membaca data sensor:", e)

        elif msg.topic == TOPIC_PRED:
            try:
                buffer.prediction = payload.split(":", 1)[1].strip()
            except:
                pass

        elif msg.topic == TOPIC_OUTPUT:
            try:
                data = json.loads(payload)
                buffer.output["led_color"] = data.get("led_color", "OFF")
                buffer.output["buzzer_on"] = data.get("buzzer_on", False)
            except Exception as e:
                print("Gagal membaca output:", e)


    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    return buffer

buffer = start_mqtt()

# ================== INIT SESSION STATE ==================
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(
        columns=["time", "temperature", "humidity", "soil"]
    )

if "log" not in st.session_state:
    st.session_state.log = pd.DataFrame(
        columns=["time", "temperature", "humidity", "soil", "prediction"]
    )

# ================== SYNC BUFFER KE SESSION STATE ==================
if buffer.sensor is not None:
    st.session_state.history = pd.concat(
        [st.session_state.history, pd.DataFrame([buffer.sensor])],
        ignore_index=True
    ).tail(200)

while buffer.queue:
    entry = buffer.queue.pop(0)
    st.session_state.log = pd.concat(
        [st.session_state.log, pd.DataFrame([entry])],
        ignore_index=True
    )

# ================== AUTO REFRESH ==================
st_autorefresh(interval=1000, key="data_refresh")

# ================== TABS ==================
tab_dashboard, tab_logs, tab_analytics = st.tabs(["Dashboard", "Logs", "Analitik"])

# ================== TAB DASHBOARD ==================
with tab_dashboard:
    st.title("🌱 Dashboard Smart Pot")

    prediction_raw = buffer.prediction or ""

    if prediction_raw.startswith("[") and "]" in prediction_raw:
        level_end = prediction_raw.index("]")
        level = prediction_raw[1:level_end]
        key = prediction_raw[level_end+1:].strip()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Suhu (°C)", buffer.sensor["temperature"] if buffer.sensor else "-")
    with c2:
        st.metric("Kelembapan (%)", buffer.sensor["humidity"] if buffer.sensor else "-")
    with c3:
        st.metric("Kelembapan Tanah (%)", buffer.sensor["soil"] if buffer.sensor else "-")
    with c4:
        st.markdown("### Status Tanaman")
        if level == "INFO":
            st.info(prediction_raw)
        elif level == "WARNING":
            st.warning(prediction_raw)
        elif level == "HIGH":
            st.error(prediction_raw)
        elif level == "CRITICAL":
            st.error(prediction_raw)
        elif level == "ERROR":
            st.error(prediction_raw)
        else:
            st.info(prediction_raw)

    st.subheader("Tren Sensor")
    if not st.session_state.history.empty:
        chart_data = st.session_state.history.melt(
            id_vars="time",
            var_name="sensor",
            value_name="value"
        )
        chart = alt.Chart(chart_data).mark_line().encode(
            x="time:T",
            y="value:Q",
            color="sensor:N"
        ).properties(height=350).interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.warning("Menunggu data sensor...")

    # ================== SUGGESTION / ACTION ==================
    prediction_suggestions = {
        "sensor_failure": "Sensor bermasalah! Periksa koneksi sensor.",
        "kondisi_optimal": "Tanaman sehat. Tidak perlu tindakan.",
        "segera_siram": "Tanah mulai kering. Segera siram tanaman!",
        "dehidrasi_panas": "Tanaman kepanasan dan dehidrasi! Pindahkan ke tempat teduh atau segera siram.",
        "bahaya_akar": "Risiko masalah pada akar! Bisa terjadi karena drainase buruk atau terlalu sering disiram.",
        "risiko_jamur": "Risiko jamur! Kelembapan tinggi dapat merusak tanaman. Tingkatkan sirkulasi udara dan hindari terlalu sering menyiram."
    }


    if prediction_raw.startswith("[") and "]" in prediction_raw:
        suggestion_msg = prediction_suggestions.get(key, "Menunggu saran...")

        st.subheader("Saran Tindakan")
        if level == "INFO":
            st.info(suggestion_msg)
        elif level == "WARNING":
            st.warning(suggestion_msg)
        elif level == "HIGH":
            st.error(suggestion_msg)
        elif level == "CRITICAL":
            st.error(suggestion_msg)
        elif level == "ERROR":
            st.error(suggestion_msg)
        else:
            st.info(suggestion_msg)
    else:
        st.info("Menunggu prediksi...")

    c5, c6 = st.columns(2)

    with c5:
        st.subheader("Status LED")
        led_color = buffer.output["led_color"]
        st.markdown(
            f"<div style='padding:15px;border-radius:8px;"
            f"background-color:{led_color.lower() if led_color!='OFF' else '#ddd'};"
            f"color:black;font-weight:bold;text-align:center;'>"
            f"{led_color}</div>",
            unsafe_allow_html=True
        )

    with c6:
        st.subheader("Status Buzzer")
        if buffer.output["buzzer_on"]:
            st.error("ON")
        else:
            st.success("OFF")


# ================== TAB LOGS ==================
with tab_logs:
    st.subheader("Log Sensor + AI (Semua History)")
    st.dataframe(st.session_state.log, use_container_width=True)

# ================== TAB ANALITIK ==================
with tab_analytics:
    st.subheader("Ringkasan Analitik (50 Data Terakhir)")

    if not st.session_state.history.empty:
        last_50 = st.session_state.history.tail(50)
        stats_50 = pd.DataFrame({
            "Rata-rata": last_50[["temperature","humidity","soil"]].mean(),
            "Min": last_50[["temperature","humidity","soil"]].min(),
            "Max": last_50[["temperature","humidity","soil"]].max(),
            "Range": last_50[["temperature","humidity","soil"]].max() - last_50[["temperature","humidity","soil"]].min(),
            "Std": last_50[["temperature","humidity","soil"]].std()
        })
        st.dataframe(stats_50)

    if not st.session_state.log.empty:
        st.markdown("### Distribusi Prediksi")
        pred_count = st.session_state.log['prediction'].value_counts().reset_index()
        pred_count.columns = ["Prediksi", "Jumlah"]

        pie_chart = alt.Chart(pred_count).mark_arc(innerRadius=50).encode(
            theta=alt.Theta(field="Jumlah", type="quantitative"),
            color=alt.Color(field="Prediksi", type="nominal"),
            tooltip=["Prediksi", "Jumlah"]
        )
        st.altair_chart(pie_chart, use_container_width=True)

# ================== FOOTER ==================
st.divider()
st.caption("© Dashboard Smart Pot AI • Sistem Real-Time MQTT")





