"""
Smart Grain Silo - Time-Series Forecasting
============================================
Predicts future Temperature and Humidity using:
  1. ARIMA  (classical statistical model - fast, interpretable)
  2. LSTM   (deep learning - captures complex non-linear patterns)

Goal: Forecast when the silo micro-climate will hit mold-growth
conditions up to 48 hours before it happens.

Usage:
    python forecasting.py                          # Run on latest data
    python forecasting.py --data path/to/data.csv  # Run on specific CSV
    python forecasting.py --model arima             # ARIMA only
    python forecasting.py --model lstm              # LSTM only
"""

import argparse
import os
import sys
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from sklearn.preprocessing import MinMaxScaler
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")

from config import (
    DATA_DIR, MODEL_DIR, PLOT_DIR,
    FORECAST_LOOKBACK, FORECAST_HORIZON,
    LSTM_EPOCHS, LSTM_BATCH_SIZE,
    MOLD_GROWTH_TEMP_MIN, MOLD_GROWTH_TEMP_MAX, MOLD_GROWTH_HUM_MIN,
    HUMIDITY_ALERT,
)


# ════════════════════════════════════════════════════════════════
#  DATA LOADING & PREPROCESSING
# ════════════════════════════════════════════════════════════════

def load_data(path: str = None) -> pd.DataFrame:
    """Load and preprocess silo CSV data."""
    if path is None:
        path = os.path.join(DATA_DIR, "silo_data_latest.csv")
    
    if not os.path.exists(path):
        print(f"[!] Data file not found: {path}")
        print("    Run `python fetch_data.py` first to download ThingSpeak data.")
        sys.exit(1)
    
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Interpolate small gaps (sensor misreads)
    for col in ["temperature", "humidity"]:
        df[col] = df[col].interpolate(method="linear", limit=5)
    
    df = df.dropna(subset=["temperature", "humidity"]).reset_index(drop=True)
    print(f"[+] Loaded {len(df)} rows from {path}")
    return df


# ════════════════════════════════════════════════════════════════
#  ARIMA FORECASTING
# ════════════════════════════════════════════════════════════════

def run_arima(df: pd.DataFrame, target_col: str, steps: int = 144):
    """
    Fit ARIMA model and forecast `steps` ahead.
    Default 144 steps = 48 hours at 20-min resampled intervals.
    
    Args:
        df: Input data with 'timestamp' and target column.
        target_col: Column to forecast ('temperature' or 'humidity').
        steps: Number of future steps to predict.
    
    Returns:
        forecast_df: DataFrame with timestamp and predicted values.
    """
    print(f"\n{'='*60}")
    print(f"  ARIMA FORECAST: {target_col.upper()}")
    print(f"{'='*60}")
    
    # Resample to regular 20-minute intervals for ARIMA stability
    ts = df.set_index("timestamp")[target_col].resample("20min").mean().interpolate()
    
    print(f"  Training samples: {len(ts)}")
    print(f"  Forecast horizon: {steps} steps ({steps * 20 / 60:.0f} hours)")
    
    # Fit ARIMA(5,1,2) — good default for environmental time-series
    print("  Fitting ARIMA(5,1,2)...")
    model = ARIMA(ts, order=(5, 1, 2))
    fitted = model.fit()
    
    print(f"  AIC: {fitted.aic:.2f}")
    
    # Forecast
    forecast = fitted.forecast(steps=steps)
    
    # Build forecast DataFrame with future timestamps
    last_ts = ts.index[-1]
    future_idx = pd.date_range(start=last_ts + pd.Timedelta(minutes=20),
                               periods=steps, freq="20min")
    forecast_df = pd.DataFrame({
        "timestamp": future_idx,
        f"{target_col}_predicted": forecast.values,
    })
    
    return ts, forecast_df, fitted


def plot_arima(ts, forecast_df, target_col: str):
    """Plot ARIMA historical + forecast with mold danger zone."""
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Plot last 3 days of history
    recent = ts[-216:]  # ~3 days at 20min intervals
    ax.plot(recent.index, recent.values, color="#2e7d32", linewidth=1.5,
            label=f"Historical {target_col.title()}", alpha=0.9)
    
    pred_col = f"{target_col}_predicted"
    ax.plot(forecast_df["timestamp"], forecast_df[pred_col],
            color="#d32f2f", linewidth=2, linestyle="--",
            label=f"ARIMA Forecast (48hr)")
    
    # Danger zone shading
    if target_col == "humidity":
        ax.axhline(y=HUMIDITY_ALERT, color="#ff9800", linestyle=":", linewidth=1.5,
                    label=f"Alert Threshold ({HUMIDITY_ALERT}%)")
        ax.axhline(y=MOLD_GROWTH_HUM_MIN, color="#f44336", linestyle=":", linewidth=1.5,
                    label=f"Mold Risk Zone ({MOLD_GROWTH_HUM_MIN}%)")
        ax.fill_between(forecast_df["timestamp"],
                        MOLD_GROWTH_HUM_MIN, 100,
                        alpha=0.1, color="red", label="Mold Danger Zone")
    elif target_col == "temperature":
        ax.axhspan(MOLD_GROWTH_TEMP_MIN, MOLD_GROWTH_TEMP_MAX,
                    alpha=0.08, color="red", label=f"Mold Temp Range ({MOLD_GROWTH_TEMP_MIN}-{MOLD_GROWTH_TEMP_MAX}°C)")
    
    ax.set_title(f"Smart Grain Silo — ARIMA {target_col.title()} Forecast",
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Time")
    ax.set_ylabel(f"{target_col.title()} ({'%' if target_col == 'humidity' else '°C'})")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    plt.tight_layout()
    
    out_path = os.path.join(PLOT_DIR, f"arima_{target_col}_forecast.png")
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  [+] Plot saved: {out_path}")


# ════════════════════════════════════════════════════════════════
#  LSTM FORECASTING
# ════════════════════════════════════════════════════════════════

def build_lstm_sequences(data: np.ndarray, lookback: int):
    """Create sliding window sequences for LSTM training."""
    X, y = [], []
    for i in range(lookback, len(data)):
        X.append(data[i - lookback : i, :])
        y.append(data[i, :])
    return np.array(X), np.array(y)


def run_lstm(df: pd.DataFrame, lookback: int = None):
    """
    Train a multi-output LSTM to jointly forecast Temperature & Humidity.
    
    Returns:
        model: Trained Keras model
        predictions: Array of predictions on the test set
        scaler: Fitted MinMaxScaler (for inverse transforms)
    """
    # Lazy import so ARIMA-only runs don't need TensorFlow
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
    
    if lookback is None:
        lookback = FORECAST_LOOKBACK
    
    print(f"\n{'='*60}")
    print(f"  LSTM MULTI-OUTPUT FORECAST")
    print(f"{'='*60}")
    
    # Prepare features: temperature + humidity
    features = df[["temperature", "humidity"]].values
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(features)
    
    X, y = build_lstm_sequences(scaled, lookback)
    print(f"  Sequences: {X.shape[0]}, Lookback: {lookback}, Features: {X.shape[2]}")
    
    # Train/test split (80/20, no shuffle for time-series)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    print(f"  Train: {len(X_train)} | Test: {len(X_test)}")

    # Build Model
    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(lookback, 2)),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation="relu"),
        Dense(2),  # Output: [temperature, humidity]
    ])
    
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    model.summary()
    
    early_stop = EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True)
    
    print("\n  Training...")
    history = model.fit(
        X_train, y_train,
        epochs=LSTM_EPOCHS,
        batch_size=LSTM_BATCH_SIZE,
        validation_data=(X_test, y_test),
        callbacks=[early_stop],
        verbose=1,
    )
    
    # Predict on test set
    predictions_scaled = model.predict(X_test)
    predictions = scaler.inverse_transform(predictions_scaled)
    actuals = scaler.inverse_transform(y_test)
    
    # Metrics
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    for i, col in enumerate(["Temperature", "Humidity"]):
        mae = mean_absolute_error(actuals[:, i], predictions[:, i])
        rmse = np.sqrt(mean_squared_error(actuals[:, i], predictions[:, i]))
        print(f"  {col} — MAE: {mae:.2f}, RMSE: {rmse:.2f}")
    
    # Save model
    model_path = os.path.join(MODEL_DIR, "lstm_forecaster.keras")
    model.save(model_path)
    print(f"  [+] Model saved: {model_path}")
    
    return model, predictions, actuals, scaler, history, df["timestamp"].iloc[split + lookback:].values


def plot_lstm(predictions, actuals, timestamps, history):
    """Plot LSTM predictions vs actuals + training loss curve."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    # ── Temperature Predictions ──
    ax = axes[0, 0]
    ax.plot(timestamps, actuals[:, 0], color="#2e7d32", linewidth=1, label="Actual", alpha=0.8)
    ax.plot(timestamps, predictions[:, 0], color="#d32f2f", linewidth=1, label="LSTM Predicted", alpha=0.8)
    ax.set_title("Temperature: Actual vs Predicted", fontweight="bold")
    ax.set_ylabel("°C")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ── Humidity Predictions ──
    ax = axes[0, 1]
    ax.plot(timestamps, actuals[:, 1], color="#1976d2", linewidth=1, label="Actual", alpha=0.8)
    ax.plot(timestamps, predictions[:, 1], color="#d32f2f", linewidth=1, label="LSTM Predicted", alpha=0.8)
    ax.axhline(y=MOLD_GROWTH_HUM_MIN, color="#ff9800", linestyle=":", label=f"Mold Risk ({MOLD_GROWTH_HUM_MIN}%)")
    ax.set_title("Humidity: Actual vs Predicted", fontweight="bold")
    ax.set_ylabel("%")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ── Training Loss ──
    ax = axes[1, 0]
    ax.plot(history.history["loss"], label="Train Loss")
    ax.plot(history.history["val_loss"], label="Val Loss")
    ax.set_title("LSTM Training Loss", fontweight="bold")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE")
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # ── Mold Risk Heatmap ──
    ax = axes[1, 1]
    mold_risk = ((predictions[:, 0] >= MOLD_GROWTH_TEMP_MIN) & 
                 (predictions[:, 0] <= MOLD_GROWTH_TEMP_MAX) &
                 (predictions[:, 1] >= MOLD_GROWTH_HUM_MIN)).astype(int)
    risk_pct = mold_risk.sum() / len(mold_risk) * 100
    
    ax.scatter(predictions[:, 0], predictions[:, 1],
               c=mold_risk, cmap="RdYlGn_r", alpha=0.5, s=10)
    ax.axhline(y=MOLD_GROWTH_HUM_MIN, color="red", linestyle="--", alpha=0.5)
    ax.axvline(x=MOLD_GROWTH_TEMP_MIN, color="red", linestyle="--", alpha=0.5)
    ax.axvline(x=MOLD_GROWTH_TEMP_MAX, color="red", linestyle="--", alpha=0.5)
    ax.set_title(f"Mold Risk Scatter ({risk_pct:.1f}% in danger zone)", fontweight="bold")
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("Humidity (%)")
    ax.grid(True, alpha=0.3)
    
    plt.suptitle("Smart Grain Silo — LSTM Forecasting Results",
                 fontsize=15, fontweight="bold", y=1.01)
    plt.tight_layout()
    
    out_path = os.path.join(PLOT_DIR, "lstm_forecast_results.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [+] Plot saved: {out_path}")


# ════════════════════════════════════════════════════════════════
#  MOLD RISK EARLY WARNING
# ════════════════════════════════════════════════════════════════

def check_mold_risk(forecast_df: pd.DataFrame, target_col: str):
    """Analyze ARIMA forecast for upcoming mold-risk windows."""
    pred_col = f"{target_col}_predicted"
    
    if target_col == "humidity":
        danger = forecast_df[forecast_df[pred_col] >= MOLD_GROWTH_HUM_MIN]
        if len(danger) > 0:
            first_danger = danger.iloc[0]["timestamp"]
            hours_until = (first_danger - forecast_df.iloc[0]["timestamp"]).total_seconds() / 3600
            print(f"\n  ⚠️  MOLD RISK WARNING: Humidity predicted to exceed {MOLD_GROWTH_HUM_MIN}%")
            print(f"      First breach at: {first_danger}")
            print(f"      Time until risk: {hours_until:.1f} hours")
            print(f"      Duration in danger zone: {len(danger) * 20 / 60:.1f} hours")
            return True
        else:
            print(f"\n  ✅ No humidity-based mold risk in the next 48 hours.")
            return False
    
    return False


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Smart Silo Time-Series Forecasting")
    parser.add_argument("--data", type=str, default=None, help="Path to CSV data file")
    parser.add_argument("--model", type=str, default="both", choices=["arima", "lstm", "both"],
                        help="Which model to run")
    args = parser.parse_args()
    
    df = load_data(args.data)
    
    if args.model in ("arima", "both"):
        # Run ARIMA for both temperature and humidity
        for col in ["temperature", "humidity"]:
            ts, forecast_df, fitted = run_arima(df, col, steps=144)
            plot_arima(ts, forecast_df, col)
            check_mold_risk(forecast_df, col)
            
            # Save forecast CSV
            out_csv = os.path.join(DATA_DIR, f"arima_forecast_{col}.csv")
            forecast_df.to_csv(out_csv, index=False)
            print(f"  [+] Forecast saved: {out_csv}")
    
    if args.model in ("lstm", "both"):
        model, predictions, actuals, scaler, history, timestamps = run_lstm(df)
        plot_lstm(predictions, actuals, timestamps, history)
    
    print(f"\n{'='*60}")
    print("  ALL FORECASTING COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
