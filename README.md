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

> **<img width="1200" height="1600" alt="image" src="https://github.com/user-attachments/assets/1636b35f-d3a6-47ee-9f52-7299d18629a0" />*
*
> **<img width="1400" height="869" alt="Screenshot 2026-02-27 074138" src="https://github.com/user-attachments/assets/c32b9aa1-2b49-470d-9d2b-56a984d87d20" />*

> 
> **Insert Photo 2 here:** *Screenshot of the Telegram Bot sending an alert message.*
> 
> **Insert Photo 3 here:** *A clear, well-lit photo of your physical hardware and wiring.*

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
git clone [https://github.com/YOUR_USERNAME/Smart-Grain-Silo.git](https://github.com/YOUR_USERNAME/Smart-Grain-Silo.git)
