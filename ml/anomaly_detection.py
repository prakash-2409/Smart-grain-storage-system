"""
Smart Grain Silo - Anomaly Detection
======================================
Uses Isolation Forest to detect abnormal sensor patterns that indicate
early-stage micro-fermentation, smoldering fires, or sensor faults —
even when readings are BELOW the hard-coded alarm thresholds.

Why this matters:
  Your ESP8266 triggers at gas > 90. But what if gas slowly creeps from
  30 → 70 over 2 hours while temp rises and humidity drops? That's a
  classic fermentation signature — invisible to threshold logic but
  obvious to an ML model trained on "normal" baseline patterns.

Usage:
    python anomaly_detection.py                          # Run on latest data
    python anomaly_detection.py --data path/to/data.csv  # Specific CSV
    python anomaly_detection.py --contamination 0.03     # Stricter (3%)
"""

import argparse
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import joblib

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from config import (
    DATA_DIR, MODEL_DIR, PLOT_DIR,
    ISOLATION_FOREST_CONTAMINATION,
    ANOMALY_FEATURES,
    GAS_ALERT, HUMIDITY_ALERT,
)


# ════════════════════════════════════════════════════════════════
#  DATA LOADING
# ════════════════════════════════════════════════════════════════

def load_data(path: str = None) -> pd.DataFrame:
    """Load silo data and engineer features for anomaly detection."""
    if path is None:
        path = os.path.join(DATA_DIR, "silo_data_latest.csv")
    
    if not os.path.exists(path):
        print(f"[!] Data file not found: {path}")
        print("    Run `python fetch_data.py` first.")
        sys.exit(1)
    
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df.dropna(subset=ANOMALY_FEATURES).reset_index(drop=True)
    
    print(f"[+] Loaded {len(df)} rows from {path}")
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create derivative features that help Isolation Forest detect
    slow-developing anomalies that raw values miss.
    """
    df = df.copy()
    
    # Rolling statistics (window = ~10 minutes at 20s intervals = 30 readings)
    window = min(30, len(df) // 4)  # Adaptive window
    if window < 3:
        window = 3
    
    for col in ["temperature", "humidity", "gas_value"]:
        df[f"{col}_rolling_mean"] = df[col].rolling(window, min_periods=1).mean()
        df[f"{col}_rolling_std"] = df[col].rolling(window, min_periods=1).std().fillna(0)
        # Rate of change (derivative)
        df[f"{col}_rate"] = df[col].diff().fillna(0)
    
    # Cross-sensor correlation features
    # High gas + rising temp + dropping humidity = fermentation signature
    df["gas_temp_ratio"] = df["gas_value"] / (df["temperature"] + 1e-6)
    df["temp_hum_diff"] = df["temperature"] - df["humidity"]
    
    df = df.fillna(0)
    print(f"  [+] Engineered {len(df.columns) - 5} additional features")
    return df


# ════════════════════════════════════════════════════════════════
#  ISOLATION FOREST TRAINING
# ════════════════════════════════════════════════════════════════

def train_isolation_forest(df: pd.DataFrame, contamination: float = None):
    """
    Train Isolation Forest on all sensor features.
    
    Returns:
        df: Original DataFrame with 'anomaly' and 'anomaly_score' columns added.
        model: Trained IsolationForest model.
        scaler: Fitted StandardScaler.
    """
    if contamination is None:
        contamination = ISOLATION_FOREST_CONTAMINATION
    
    print(f"\n{'='*60}")
    print(f"  ISOLATION FOREST ANOMALY DETECTION")
    print(f"{'='*60}")
    
    # Select all numeric feature columns (excluding timestamp/motion)
    feature_cols = [c for c in df.columns if c not in ["timestamp", "motion", "anomaly", "anomaly_score"]]
    print(f"  Features: {len(feature_cols)}")
    print(f"  Contamination: {contamination:.1%}")
    
    X = df[feature_cols].values
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    
    print("  Training Isolation Forest...")
    model.fit(X_scaled)
    
    # Predict: -1 = anomaly, 1 = normal
    labels = model.predict(X_scaled)
    scores = model.decision_function(X_scaled)
    
    df = df.copy()
    df["anomaly"] = (labels == -1).astype(int)
    df["anomaly_score"] = scores
    
    n_anomalies = df["anomaly"].sum()
    print(f"  Anomalies detected: {n_anomalies} / {len(df)} ({100 * n_anomalies / len(df):.1f}%)")
    
    # Save model + scaler
    model_path = os.path.join(MODEL_DIR, "isolation_forest.joblib")
    scaler_path = os.path.join(MODEL_DIR, "anomaly_scaler.joblib")
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    print(f"  [+] Model saved: {model_path}")
    
    return df, model, scaler, feature_cols


# ════════════════════════════════════════════════════════════════
#  ANOMALY ANALYSIS & CLASSIFICATION
# ════════════════════════════════════════════════════════════════

def classify_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify detected anomalies into meaningful categories based on
    which sensor values are driving the anomaly.
    """
    anomalies = df[df["anomaly"] == 1].copy()
    
    if len(anomalies) == 0:
        print("\n  ✅ No anomalies detected in the dataset!")
        return anomalies
    
    def categorize(row):
        reasons = []
        if row.get("gas_value", 0) > GAS_ALERT * 0.6:  # 60% of threshold
            reasons.append("ELEVATED_GAS")
        if row.get("gas_value_rate", 0) > 5:
            reasons.append("GAS_SPIKE")
        if row.get("humidity", 0) > HUMIDITY_ALERT * 0.85:
            reasons.append("HIGH_HUMIDITY")
        if row.get("humidity_rate", 0) > 2:
            reasons.append("HUMIDITY_SPIKE")
        if row.get("temperature_rate", 0) > 2:
            reasons.append("TEMP_SPIKE")
        if row.get("gas_value_rolling_std", 0) > 15:
            reasons.append("UNSTABLE_GAS")
        if not reasons:
            reasons.append("MULTI_SENSOR_PATTERN")
        return " + ".join(reasons)
    
    anomalies["category"] = anomalies.apply(categorize, axis=1)
    
    print(f"\n  ANOMALY CLASSIFICATION:")
    print(f"  {'─'*50}")
    for cat, count in anomalies["category"].value_counts().items():
        print(f"    {cat}: {count}")
    
    return anomalies


# ════════════════════════════════════════════════════════════════
#  VISUALIZATION
# ════════════════════════════════════════════════════════════════

def plot_anomalies(df: pd.DataFrame, anomalies: pd.DataFrame):
    """Generate comprehensive anomaly detection plots."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 14), sharex=True)
    
    normal = df[df["anomaly"] == 0]
    
    # ── Gas Sensor ──
    ax = axes[0]
    ax.plot(normal["timestamp"], normal["gas_value"],
            color="#2e7d32", linewidth=0.8, alpha=0.7, label="Normal")
    if len(anomalies) > 0:
        ax.scatter(anomalies["timestamp"], anomalies["gas_value"],
                   c="red", s=20, zorder=5, label="Anomaly", alpha=0.8)
    ax.axhline(y=GAS_ALERT, color="#ff9800", linestyle="--", label=f"Alarm Threshold ({GAS_ALERT})")
    ax.axhline(y=GAS_ALERT * 0.6, color="#ffb74d", linestyle=":", alpha=0.5,
               label=f"ML Early Warning ({int(GAS_ALERT * 0.6)})")
    ax.set_ylabel("Gas Value")
    ax.set_title("MQ-2 Gas Sensor — Anomaly Detection", fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # ── Humidity ──
    ax = axes[1]
    ax.plot(normal["timestamp"], normal["humidity"],
            color="#1976d2", linewidth=0.8, alpha=0.7, label="Normal")
    if len(anomalies) > 0:
        ax.scatter(anomalies["timestamp"], anomalies["humidity"],
                   c="red", s=20, zorder=5, label="Anomaly", alpha=0.8)
    ax.axhline(y=HUMIDITY_ALERT, color="#ff9800", linestyle="--",
               label=f"Alarm Threshold ({HUMIDITY_ALERT}%)")
    ax.set_ylabel("Humidity (%)")
    ax.set_title("Humidity — Anomaly Detection", fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # ── Anomaly Score Timeline ──
    ax = axes[2]
    ax.plot(df["timestamp"], df["anomaly_score"],
            color="#5c6bc0", linewidth=0.8, alpha=0.7)
    ax.axhline(y=0, color="#d32f2f", linestyle="--", linewidth=1, label="Decision Boundary")
    ax.fill_between(df["timestamp"], df["anomaly_score"], 0,
                    where=df["anomaly_score"] < 0,
                    color="red", alpha=0.2, label="Anomalous Region")
    ax.set_ylabel("Anomaly Score")
    ax.set_xlabel("Time")
    ax.set_title("Isolation Forest Anomaly Score Over Time", fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
    
    plt.suptitle("Smart Grain Silo — Isolation Forest Anomaly Detection",
                 fontsize=15, fontweight="bold", y=1.01)
    plt.tight_layout()
    
    out_path = os.path.join(PLOT_DIR, "anomaly_detection_results.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  [+] Plot saved: {out_path}")


def plot_feature_importance(df: pd.DataFrame):
    """Plot pairwise scatter to show anomaly separation in feature space."""
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    colors = df["anomaly"].map({0: "#2e7d32", 1: "#d32f2f"})
    
    pairs = [
        ("gas_value", "humidity"),
        ("temperature", "humidity"),
        ("gas_value", "temperature"),
    ]
    
    for ax, (x_col, y_col) in zip(axes, pairs):
        ax.scatter(df[x_col], df[y_col], c=colors, s=8, alpha=0.5)
        ax.set_xlabel(x_col.replace("_", " ").title())
        ax.set_ylabel(y_col.replace("_", " ").title())
        ax.set_title(f"{x_col} vs {y_col}", fontweight="bold")
        ax.grid(True, alpha=0.3)
    
    # Custom legend
    from matplotlib.lines import Line2D
    legend = [Line2D([0], [0], marker='o', color='w', markerfacecolor='#2e7d32', markersize=8, label='Normal'),
              Line2D([0], [0], marker='o', color='w', markerfacecolor='#d32f2f', markersize=8, label='Anomaly')]
    axes[2].legend(handles=legend, loc="upper right")
    
    plt.suptitle("Feature Space — Normal vs Anomalous Readings",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    
    out_path = os.path.join(PLOT_DIR, "anomaly_feature_space.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [+] Plot saved: {out_path}")


# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Smart Silo Anomaly Detection")
    parser.add_argument("--data", type=str, default=None, help="Path to CSV data file")
    parser.add_argument("--contamination", type=float, default=None,
                        help=f"Expected anomaly rate (default: {ISOLATION_FOREST_CONTAMINATION})")
    args = parser.parse_args()
    
    # Load & engineer features
    df = load_data(args.data)
    df = engineer_features(df)
    
    # Train & detect
    df, model, scaler, feature_cols = train_isolation_forest(df, args.contamination)
    
    # Classify anomalies
    anomalies = classify_anomalies(df)
    
    # Visualize
    plot_anomalies(df, anomalies)
    plot_feature_importance(df)
    
    # Save annotated data
    out_csv = os.path.join(DATA_DIR, "silo_data_with_anomalies.csv")
    df.to_csv(out_csv, index=False)
    print(f"  [+] Annotated data saved: {out_csv}")
    
    if len(anomalies) > 0:
        anomaly_csv = os.path.join(DATA_DIR, "detected_anomalies.csv")
        anomalies.to_csv(anomaly_csv, index=False)
        print(f"  [+] Anomaly log saved: {anomaly_csv}")
    
    print(f"\n{'='*60}")
    print("  ANOMALY DETECTION COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
