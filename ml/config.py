"""
Smart Grain Silo - ML Configuration
Central config for all ML scripts. Reads secrets from .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── ThingSpeak API ──────────────────────────────────────────────
THINGSPEAK_CHANNEL_ID = os.getenv("THINGSPEAK_CHANNEL_ID", "YOUR_CHANNEL_ID")
THINGSPEAK_READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY", "YOUR_READ_API_KEY")
THINGSPEAK_BASE_URL = "https://api.thingspeak.com"

# ── Field Mapping (must match your ESP8266 code) ───────────────
FIELD_MAP = {
    "field1": "temperature",
    "field2": "humidity",
    "field3": "gas_value",
    "field4": "motion",
}

# ── Thresholds (must match your ESP8266 code) ──────────────────
HUMIDITY_FAN_ON = 50.0       # Fan activates above this
HUMIDITY_ALERT = 60.0        # Telegram alert threshold
GAS_ALERT = 90               # Gas alarm threshold
MOLD_GROWTH_TEMP_MIN = 20.0  # Mold risk zone (°C)
MOLD_GROWTH_TEMP_MAX = 40.0
MOLD_GROWTH_HUM_MIN = 65.0   # Mold risk zone (%)

# ── Data Paths ──────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
PLOT_DIR = os.path.join(os.path.dirname(__file__), "plots")

# Create dirs if they don't exist
for d in [DATA_DIR, MODEL_DIR, PLOT_DIR]:
    os.makedirs(d, exist_ok=True)

# ── LSTM Forecasting Params ─────────────────────────────────────
FORECAST_LOOKBACK = 72       # Use last 72 readings (~24 min at 20s interval)
FORECAST_HORIZON = 8640      # Predict next 8640 readings (~48 hours ahead)
LSTM_EPOCHS = 50
LSTM_BATCH_SIZE = 32

# ── Anomaly Detection Params ────────────────────────────────────
ISOLATION_FOREST_CONTAMINATION = 0.05  # Expected 5% anomaly rate
ANOMALY_FEATURES = ["gas_value", "temperature", "humidity"]

# ── Fan Optimization (RL) Params ────────────────────────────────
RL_TOTAL_TIMESTEPS = 50_000
RL_HUMIDITY_TARGET = 45.0    # Target humidity after fan purge
