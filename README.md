# 🌾 Smart Grain Silo IoT Monitor

An automated, zero-recurring-cost IoT monitoring and active-defense system for agricultural grain silos. Built with the ESP8266, this project prevents post-harvest grain loss by monitoring micro-climates, detecting early spoilage/fires, and preventing theft.

---

## 🚀 The Problem We Solve

Farmers lose up to 20% of their harvested grain to fungal growth, fermentation, and rodent infestation. Traditional monitoring systems require expensive GSM modules and monthly SIM card subscriptions. This project uses local Wi-Fi and free cloud APIs to provide industrial-grade monitoring with **zero recurring subscription costs**.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🌍 **Real-Time Cloud Logging** | Logs Temperature, Humidity, Gas, and Motion to ThingSpeak every 20 seconds |
| 📱 **Instant Mobile Alerts** | Pushes free Telegram notifications for Fire, Moisture, and Intruder events |
| ⚙️ **Active Defense** | Automatically activates exhaust fan relay when humidity exceeds 50% |
| 💻 **Local Web Dashboard** | Auto-refreshing dashboard hosted directly on the ESP8266 |
| 🔊 **Multi-Stage Alarms** | Solid buzzer tone = fire danger; fast double-beeps = intruder |

---

## 🛠️ Hardware Requirements

| Component | Description |
|---|---|
| **ESP8266** | NodeMCU development board |
| **DHT11** | Temperature & Humidity sensor |
| **MQ-2** | Gas sensor (smoke, CO₂, fermentation gases) |
| **PIR Sensor** | Passive infrared motion detector |
| **5V Relay Module** | Controls the exhaust fan |
| **DC Exhaust Fan** | Purges moist or contaminated air |
| **Active Buzzer** | Local audio alarm |

### Pin Mapping

| Component | ESP8266 Pin | GPIO | Function |
|---|---|---|---|
| DHT11 | D4 | GPIO 2 | Temperature & Humidity data |
| PIR Sensor | D5 | GPIO 14 | Motion detection |
| Relay (Fan) | D6 | GPIO 12 | Controls exhaust fan |
| Buzzer | D7 | GPIO 13 | Local audio alarm |
| MQ-2 | A0 | ADC | Analog gas level reading |

---

## 💻 Software & Libraries

Compiled using the **Arduino IDE** with the **ESP8266 board package** installed.

### Required Libraries

Install via **Sketch → Include Library → Manage Libraries…**

| Library | Source |
|---|---|
| `ESP8266WiFi` | Built-in (ESP8266 board package) |
| `ESP8266WebServer` | Built-in (ESP8266 board package) |
| `ESP8266HTTPClient` | Built-in (ESP8266 board package) |
| `WiFiClientSecure` | Built-in (ESP8266 board package) |
| `DHT sensor library` | Adafruit (search "DHT sensor library") |
| `Adafruit Unified Sensor` | Adafruit (required dependency) |

---

## ⚙️ Setup & Configuration

### 1. Install the ESP8266 Board Package

In Arduino IDE go to **File → Preferences** and add the following URL to *Additional Boards Manager URLs*:

```
http://arduino.esp8266.com/stable/package_esp8266com_index.json
```

Then open **Tools → Board → Boards Manager**, search for `esp8266`, and install.

### 2. Create a ThingSpeak Channel

1. Sign up at [thingspeak.com](https://thingspeak.com) (free).
2. Create a new channel with four fields:
   - **Field 1** – Temperature (°C)
   - **Field 2** – Humidity (%)
   - **Field 3** – Gas Level (ADC)
   - **Field 4** – Motion (1 = detected, 0 = none)
3. Copy your **Write API Key**.

### 3. Create a Telegram Bot

1. Open Telegram and message **@BotFather** with `/newbot`.
2. Follow the prompts; copy the **Bot Token**.
3. Start a conversation with your new bot and visit:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   to find your **Chat ID**.

### 4. Configure the Sketch

Open `SmartGrainSilo/SmartGrainSilo.ino` and fill in the *USER CONFIGURATION* section:

```cpp
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* TS_API_KEY    = "YOUR_THINGSPEAK_WRITE_API_KEY";

const char* TG_BOT_TOKEN  = "YOUR_TELEGRAM_BOT_TOKEN";
const char* TG_CHAT_ID    = "YOUR_TELEGRAM_CHAT_ID";
```

You can also adjust the default alert thresholds:

```cpp
const int   GAS_THRESHOLD      = 400;   // MQ-2 raw ADC (0–1023)
const float HUMIDITY_THRESHOLD = 50.0;  // % – fan auto-activates above this
const float TEMP_THRESHOLD     = 40.0;  // °C – used with gas for fire alert
```

### 5. Flash the ESP8266

1. Select **Tools → Board → NodeMCU 1.0 (ESP-12E Module)**.
2. Select the correct **Port**.
3. Click **Upload**.
4. Open the **Serial Monitor** at 115200 baud to verify the connection.

---

## 📊 Local Web Dashboard

After flashing, open a browser on the same Wi-Fi network and navigate to the IP address printed in the Serial Monitor (e.g., `http://192.168.1.42`).

The dashboard auto-refreshes every 10 seconds and shows:

- Live temperature, humidity, and gas readings
- Motion status and exhaust fan state
- Colour-coded alert banners (fire / intruder / moisture)

---

## 🚨 Alert Logic

| Condition | Alert Type | Action |
|---|---|---|
| Gas > threshold **AND** Temp > 40 °C | 🔥 Fire | Telegram alert + continuous buzzer tone + fan ON |
| Humidity > 50 % | 💧 Moisture | Telegram alert + fan ON (auto purge) |
| PIR triggered | 🚨 Intruder | Telegram alert + fast double-beeps |

Telegram messages are sent only on the **rising edge** of each alert (once per event, not every sensor cycle) to avoid notification spam.

---

## 📁 Project Structure

```
SmartGrainSilo/
└── SmartGrainSilo.ino   ← Main Arduino sketch (all features in one file)
```

---

## 📄 License

This project is released under the [MIT License](LICENSE).
