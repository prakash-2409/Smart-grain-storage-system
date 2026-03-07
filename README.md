# 🌾 Smart Grain Silo: Zero-Cost IoT Active Defense System

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-ESP8266-blue.svg)
![Cloud](https://img.shields.io/badge/Cloud-ThingSpeak-orange.svg)
![Integration](https://img.shields.io/badge/Alerts-Telegram_Bot-blue)

[Image of IoT system architecture for Smart Agriculture showing edge sensors connecting to cloud dashboards and mobile devices]

An automated, zero-recurring-cost IoT monitoring and active-defense system for agricultural grain silos. Built with the ESP8266, this project prevents post-harvest grain loss by monitoring micro-climates, detecting early spoilage/fires, and preventing theft in real-time.

---

## 🚀 The Problem & Our Solution
**The Problem:** Farmers lose up to 20% of their harvested grain to fungal growth, fermentation, and rodent infestation. Traditional monitoring systems require expensive GSM modules, paid SIM cards, and monthly cellular subscriptions. 

**The Solution:** We engineered a system with **zero recurring subscription costs** for the farmer. By utilizing local Wi-Fi bridges and free cloud APIs (ThingSpeak & Telegram), we built an industrial-grade monitor that doesn't just passively watch the grain—it actively defends it.

---

## ✨ Deep Dive: System Features

### 1. ⚙️ Active Defense Automation
Unlike basic monitors, this system reacts to environmental threats instantly. 
* If the DHT11 sensor detects humidity crossing the **50% mold-growth threshold**, the ESP8266 automatically triggers a relay to activate a **high-power exhaust fan**. 
* This purges the moist air before fungi can grow, and automatically shuts off when the climate stabilizes.

### 2. 📱 Instant Mobile Alerts (Telegram Bot API)
We bypassed expensive GSM modules by natively integrating the **Official Telegram Bot API** via secure HTTPS (`WiFiClientSecure`). 
* The system pushes instant, free notifications directly to the farmer's phone.
* Features a built-in **60-second cooldown timer** to prevent API rate-limiting and notification spam.

### 3. 🌍 Dual-Layer Monitoring (Local & Cloud)
* **The Local Dashboard:** Hosts a beautifully styled, auto-refreshing, responsive HTML/CSS dashboard directly on the ESP8266. The farmer can monitor real-time data on-site without internet access.
* **The Cloud Database:** Seamless integration with **ThingSpeak**. The ESP8266 uses a non-blocking `millis()` timer to push Temperature, Humidity, Gas, and Motion data to the cloud every 20 seconds for historical analysis.

### 4. 🔊 Multi-Stage Local Alarms
Smart buzzer logic produces distinct audio signatures for different threats so workers know exactly what is wrong without looking at a screen:
* **Fire/Gas Spoilage:** Solid, continuous high-pitched tone.
* **Intruder/Rodent Motion:** Rapid, pulsating fast beeps.
* **High Humidity:** Slow, warning beeps.

---

## 📸 Project Showcase

*(Drop your actual project photos here! Just drag and drop your images into GitHub and it will generate the links for you).*

> **<img width="1200" height="1600" alt="image" src="https://gith<img width="1838" height="976" alt="Screenshot 2026-02-27 065230" src="https://github.com/user-attachments/assets/06a21c8e-37c5-4b68-b462-7ac5bc4936d4" />
ub.com/user-attachments/assets/1636b35f-d3a6-47ee-9f52-7299d18629a0" />*
*
> **<img width="1400" height="869" alt="Screenshot 2026-02-27 074138" src="https://github.com/user-attachments/assets/c32b9aa1-2b49-470d-9d2b-56a984d87d20" />*

> 
> **<img width="1807" height="966" alt="Screenshot 2026-02-27 064920" src="https://github.com/user-attachments/assets/1f6c415a-2ece-4aa9-b103-34f378c87768" />*
> 

---

## 🛠️ Hardware Architecture

[Image of hardware circuit diagram using ESP8266 connected to DHT11, PIR sensor, MQ2 gas sensor, and a relay module]

* **Microcontroller:** ESP8266 (NodeMCU)
* **Climate Sensor:** DHT11 (Temperature & Humidity)
* **Gas Sensor:** MQ-2 (Smoke, CO2, Fermentation gases)
* **Security Sensor:** PIR Motion Sensor (Intruders & Rodents)
* **Actuator:** 5V Relay Module (Active-Low) + DC Exhaust Fan
* **Alerts:** Active Buzzer & LED

### Pin Mapping
| Component | ESP8266 Pin | Function |
| :--- | :--- | :--- |
| **DHT11** | `D4` | Temp/Humidity Data |
| **PIR Sensor**| `D5` | Motion Detection |
| **Relay (Fan)**| `D6` | Controls Exhaust Fan |
| **Buzzer** | `D7` | Local Audio Alarm |
| **MQ-2** | `A0` | Analog Gas Reading |

---

## 💻 Installation & Setup

**1. Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/Smart-Grain-Silo.git
```

**2. Flash the ESP8266**
- Open `code/code.ino` in Arduino IDE.
- Update your Wi-Fi credentials (`ssid`, `password`), ThingSpeak API key, and Telegram bot token.
- Install required libraries: `ESP8266WiFi`, `ESP8266WebServer`, `ESP8266HTTPClient`, `WiFiClientSecure`, `DHT`.
- Select **NodeMCU 1.0 (ESP-12E)** board and flash.

**3. Set up the ML Pipeline**
```bash
cd ml
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your ThingSpeak Channel ID and Read API Key
```

**4. Run the ML Pipeline**
```bash
# Step 1: Pull data from ThingSpeak
python fetch_data.py

# Step 2: Run forecasting (ARIMA + LSTM)
python forecasting.py

# Step 3: Run anomaly detection
python anomaly_detection.py

# Step 4: Run fan optimization
python fan_optimization.py
```

---

## 🤖 Machine Learning Pipeline

The `ml/` directory contains a complete Python-based ML pipeline that consumes the time-series data logged to ThingSpeak and performs three types of predictive analysis:

### Pipeline Architecture
```
ThingSpeak Cloud ──→ fetch_data.py ──→ silo_data_latest.csv
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
            forecasting.py         anomaly_detection.py    fan_optimization.py
            (ARIMA + LSTM)         (Isolation Forest)      (PPO Reinforcement Learning)
                    │                       │                       │
                    ▼                       ▼                       ▼
            48hr Mold Risk          Early Fermentation     Optimal Fan ON/OFF
            Prediction              Detection              Thresholds
```

### ML Script 1: `forecasting.py` — Time-Series Forecasting
| Model | Method | Purpose |
| :--- | :--- | :--- |
| **ARIMA(5,1,2)** | Classical statistics | Fast, interpretable 48-hour forecast of temperature & humidity trends |
| **LSTM (64→32)** | Deep learning | Multi-output neural network jointly predicting temperature + humidity |

**Key Output:** Early warning when the silo micro-climate is predicted to enter mold-growth conditions (Humidity > 65%, Temp 20-40°C) up to **48 hours before** it happens.

### ML Script 2: `anomaly_detection.py` — Isolation Forest
Detects **sub-threshold anomalies** that simple `if (gas > 90)` logic misses:
- Slow gas creep (e.g., 30 → 70 over 2 hours = early fermentation)
- Correlated multi-sensor patterns (gas rising + temperature rising + humidity dropping)
- Sensor faults and electrical noise

Uses engineered features: rolling means, standard deviations, rates of change, and cross-sensor ratios.

### ML Script 3: `fan_optimization.py` — Reinforcement Learning
Trains a PPO (Proximal Policy Optimization) agent in a simulated silo environment to learn:
- **When** to turn the fan ON (optimal humidity threshold)
- **When** to turn it OFF (with hysteresis to prevent rapid cycling)
- **How long** to run it (minimize electricity while keeping humidity safe)

The agent's learned policy is extracted as simple threshold rules that can be coded back into the ESP8266.

---

## 📁 Project Structure
```
Smart-grain-storage-system/
├── code/
│   └── code.ino              # ESP8266 firmware (C++)
├── ml/
│   ├── .env.example           # Template for API secrets
│   ├── config.py              # Central configuration
│   ├── requirements.txt       # Python dependencies
│   ├── fetch_data.py          # ThingSpeak → CSV data puller
│   ├── forecasting.py         # ARIMA + LSTM time-series forecasting
│   ├── anomaly_detection.py   # Isolation Forest anomaly detection
│   ├── fan_optimization.py    # PPO reinforcement learning for fan control
│   ├── data/                  # Downloaded CSVs & processed data
│   ├── models/                # Saved ML models (.keras, .joblib, .zip)
│   └── plots/                 # Generated visualizations
├── README.md
└── LICENSE
```

---

## 🔧 Automation Logic Summary

| Trigger | Fan | Buzzer | Telegram | Dashboard |
| :--- | :--- | :--- | :--- | :--- |
| **Gas > 90** | ON | Solid continuous | CRITICAL Alert | SPOILAGE ALERT |
| **Humidity > 60%** | ON | Slow pulse (300ms) | CLIMATE Alert | HIGH HUMIDITY |
| **Humidity > 50%** | ON | — | — | PURGING AIR |
| **Motion = HIGH** | — | Fast pulse (150ms) | SECURITY Alert | INTRUDER DETECTED |
| **All Normal** | OFF | OFF | — | SAFE |

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
