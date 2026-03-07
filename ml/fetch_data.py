"""
Smart Grain Silo - ThingSpeak Data Fetcher
===========================================
Pulls all historical time-series data from your ThingSpeak channel
and saves it as a clean CSV for downstream ML pipelines.

Usage:
    python fetch_data.py                     # Fetch all data
    python fetch_data.py --results 1000      # Fetch last 1000 points
    python fetch_data.py --days 7            # Fetch last 7 days
"""

import argparse
import sys
import os
import requests
import pandas as pd
from datetime import datetime, timedelta

from config import (
    THINGSPEAK_CHANNEL_ID,
    THINGSPEAK_READ_API_KEY,
    THINGSPEAK_BASE_URL,
    FIELD_MAP,
    DATA_DIR,
)


def fetch_thingspeak(results: int = 8000, days: int = None) -> pd.DataFrame:
    """
    Fetch data from ThingSpeak channel feeds API.
    
    Args:
        results: Max number of data points to retrieve (ThingSpeak max: 8000).
        days:    If set, only fetch data from the last N days.
    
    Returns:
        pd.DataFrame with columns: timestamp, temperature, humidity, gas_value, motion
    """
    url = f"{THINGSPEAK_BASE_URL}/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"
    
    params = {
        "api_key": THINGSPEAK_READ_API_KEY,
        "results": min(results, 8000),  # ThingSpeak hard limit
    }
    
    if days is not None:
        start = datetime.utcnow() - timedelta(days=days)
        params["start"] = start.strftime("%Y-%m-%d%%20%H:%M:%S")
    
    print(f"[*] Fetching data from ThingSpeak channel {THINGSPEAK_CHANNEL_ID}...")
    print(f"    URL: {url}")
    print(f"    Params: results={params['results']}" + (f", days={days}" if days else ""))
    
    response = requests.get(url, params=params, timeout=30)
    
    if response.status_code != 200:
        print(f"[!] HTTP Error {response.status_code}: {response.text}")
        sys.exit(1)
    
    data = response.json()
    feeds = data.get("feeds", [])
    
    if not feeds:
        print("[!] No data returned from ThingSpeak. Check your Channel ID and API Key.")
        sys.exit(1)
    
    print(f"[+] Received {len(feeds)} data points.")
    
    # Build DataFrame
    rows = []
    for entry in feeds:
        row = {"timestamp": entry.get("created_at")}
        for field_key, col_name in FIELD_MAP.items():
            raw = entry.get(field_key)
            row[col_name] = float(raw) if raw is not None else None
        rows.append(row)
    
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Convert motion to int (0/1)
    if "motion" in df.columns:
        df["motion"] = df["motion"].fillna(0).astype(int)
    
    return df


def print_summary(df: pd.DataFrame):
    """Pretty-print a summary of the fetched data."""
    print("\n" + "=" * 60)
    print("  DATA SUMMARY")
    print("=" * 60)
    print(f"  Time range : {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"  Total rows : {len(df)}")
    print(f"  Columns    : {list(df.columns)}")
    print("-" * 60)
    print(df.describe().round(2).to_string())
    print("-" * 60)
    
    # Count missing values
    missing = df.isnull().sum()
    if missing.any():
        print("  Missing values:")
        for col, count in missing.items():
            if count > 0:
                print(f"    {col}: {count} ({100*count/len(df):.1f}%)")
    else:
        print("  No missing values!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fetch Smart Grain Silo data from ThingSpeak")
    parser.add_argument("--results", type=int, default=8000, help="Number of data points (max 8000)")
    parser.add_argument("--days", type=int, default=None, help="Only fetch last N days")
    parser.add_argument("--output", type=str, default=None, help="Custom output CSV filename")
    args = parser.parse_args()
    
    df = fetch_thingspeak(results=args.results, days=args.days)
    print_summary(df)
    
    # Save to CSV
    if args.output:
        out_path = args.output
    else:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(DATA_DIR, f"silo_data_{timestamp_str}.csv")
    
    df.to_csv(out_path, index=False)
    print(f"\n[+] Data saved to: {out_path}")
    
    # Also save a 'latest' symlink-style copy for other scripts to easily find
    latest_path = os.path.join(DATA_DIR, "silo_data_latest.csv")
    df.to_csv(latest_path, index=False)
    print(f"[+] Latest copy saved to: {latest_path}")
    
    return df


if __name__ == "__main__":
    main()
