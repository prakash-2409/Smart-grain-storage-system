/**
 * Smart Grain Silo IoT Monitor
 * =========================================================
 * An automated, zero-recurring-cost IoT monitoring and
 * active-defense system for agricultural grain silos.
 *
 * Hardware: ESP8266 (NodeMCU)
 *
 * Pin Mapping:
 *  DHT11  → D4  (GPIO2)  - Temperature & Humidity
 *  PIR    → D5  (GPIO14) - Motion Detection
 *  Relay  → D6  (GPIO12) - Controls Exhaust Fan
 *  Buzzer → D7  (GPIO13) - Local Audio Alarm
 *  MQ-2   → A0           - Analog Gas Reading
 *
 * Features:
 *  - ThingSpeak cloud logging every 20 s
 *  - Telegram instant mobile alerts (fire / moisture / intruder)
 *  - Auto relay: fan activates when humidity > 50 %
 *  - Multi-stage buzzer: solid tone = fire, fast beeps = intruder
 *  - Local auto-refreshing web dashboard
 *
 * Required Libraries (install via Arduino IDE Library Manager):
 *  - ESP8266WiFi        (built-in ESP8266 board package)
 *  - ESP8266WebServer   (built-in ESP8266 board package)
 *  - ESP8266HTTPClient  (built-in ESP8266 board package)
 *  - WiFiClientSecure   (built-in ESP8266 board package)
 *  - DHT sensor library by Adafruit
 *  - Adafruit Unified Sensor (dependency for DHT library)
 *
 * Configuration:
 *  Fill in the USER CONFIGURATION section below before flashing.
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <DHT.h>

// ─────────────────────────────────────────────────────────
//  USER CONFIGURATION  – fill these in before flashing
// ─────────────────────────────────────────────────────────
const char* WIFI_SSID       = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD   = "YOUR_WIFI_PASSWORD";

// ThingSpeak
const char* TS_API_KEY      = "YOUR_THINGSPEAK_WRITE_API_KEY";

// Telegram  (get via @BotFather)
const char* TG_BOT_TOKEN    = "YOUR_TELEGRAM_BOT_TOKEN";
const char* TG_CHAT_ID      = "YOUR_TELEGRAM_CHAT_ID";

// Alert thresholds
const int   GAS_THRESHOLD   = 400;   // MQ-2 raw ADC value (0-1023)
const float HUMIDITY_THRESHOLD = 50.0; // % – fan auto-activates above this
const float TEMP_THRESHOLD  = 40.0;  // °C – combined with gas for fire alert
// ─────────────────────────────────────────────────────────

// ── Pin definitions ───────────────────────────────────────
#define DHT_PIN      2   // D4
#define PIR_PIN      14  // D5
#define RELAY_PIN    12  // D6
#define BUZZER_PIN   13  // D7
#define GAS_PIN      A0

// ── DHT sensor type ───────────────────────────────────────
#define DHT_TYPE DHT11
DHT dht(DHT_PIN, DHT_TYPE);

// ── Web server on port 80 ─────────────────────────────────
ESP8266WebServer server(80);

// ── Timing constants (milliseconds) ──────────────────────
const unsigned long CLOUD_INTERVAL   = 20000UL; // ThingSpeak update interval
const unsigned long SENSOR_INTERVAL  = 2000UL;  // Local sensor read interval

// ── State variables ───────────────────────────────────────
float    temperature  = 0.0;
float    humidity     = 0.0;
int      gasLevel     = 0;
bool     motionDetected = false;
bool     fanRunning   = false;
bool     fireAlert    = false;
bool     moistureAlert = false;
bool     intruderAlert = false;

unsigned long lastCloudUpdate = 0;
unsigned long lastSensorRead  = 0;

// ── Non-blocking buzzer state machine ────────────────────
enum BuzzerState { BUZZER_IDLE, BUZZER_ON, BUZZER_OFF };
BuzzerState  buzzerState    = BUZZER_IDLE;
int          buzzerBeepCount = 0;       // beeps remaining for intruder pattern
unsigned long buzzerStateAt = 0;        // millis() when current state started

// ─────────────────────────────────────────────────────────
//  Forward declarations
// ─────────────────────────────────────────────────────────
void readSensors();
void evaluateAlerts();
void controlActuators();
void updateBuzzer();
void sendToThingSpeak();
void sendTelegramAlert(const String& message);
String urlEncode(const String& str);
void handleWebRoot();
String buildDashboardHTML();

// ─────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(100);

  // Pin modes
  pinMode(PIR_PIN,    INPUT);
  pinMode(RELAY_PIN,  OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(RELAY_PIN,  LOW);  // Fan off initially
  digitalWrite(BUZZER_PIN, LOW);  // Buzzer off initially

  dht.begin();

  // ── Connect to WiFi ─────────────────────────────────────
  Serial.print("\nConnecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // ── Register web routes ──────────────────────────────────
  server.on("/", handleWebRoot);
  server.begin();
  Serial.println("Web server started.");
}

// ─────────────────────────────────────────────────────────
//  MAIN LOOP
// ─────────────────────────────────────────────────────────
void loop() {
  server.handleClient();

  unsigned long now = millis();

  // Read sensors every SENSOR_INTERVAL ms
  if (now - lastSensorRead >= SENSOR_INTERVAL) {
    lastSensorRead = now;
    readSensors();
    evaluateAlerts();
    controlActuators();

    // Debug output
    Serial.printf("Temp: %.1f°C | Hum: %.1f%% | Gas: %d | Motion: %s | Fan: %s\n",
                  temperature, humidity, gasLevel,
                  motionDetected ? "YES" : "no",
                  fanRunning     ? "ON"  : "off");
  }

  // Update buzzer state machine every loop iteration (non-blocking)
  updateBuzzer();

  // Push to ThingSpeak every CLOUD_INTERVAL ms
  if (now - lastCloudUpdate >= CLOUD_INTERVAL) {
    lastCloudUpdate = now;
    sendToThingSpeak();
  }
}

// ─────────────────────────────────────────────────────────
//  SENSOR READING
// ─────────────────────────────────────────────────────────
void readSensors() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  // Only update if valid readings received
  if (!isnan(h) && !isnan(t)) {
    humidity    = h;
    temperature = t;
  }

  gasLevel       = analogRead(GAS_PIN);
  motionDetected = (digitalRead(PIR_PIN) == HIGH);
}

// ─────────────────────────────────────────────────────────
//  ALERT EVALUATION
// ─────────────────────────────────────────────────────────
void evaluateAlerts() {
  // Fire alert: high gas level combined with elevated temperature
  bool newFire      = (gasLevel > GAS_THRESHOLD && temperature > TEMP_THRESHOLD);
  bool newMoisture  = (humidity > HUMIDITY_THRESHOLD);
  bool newIntruder  = motionDetected;

  // Send Telegram only on rising edge (new alert state)
  if (newFire && !fireAlert) {
    sendTelegramAlert("🔥 *FIRE ALERT!* High gas level (" + String(gasLevel) +
                      ") and temperature (" + String(temperature, 1) +
                      " °C) detected in the silo!");
  }
  if (newMoisture && !moistureAlert) {
    sendTelegramAlert("💧 *MOISTURE ALERT!* Humidity is " + String(humidity, 1) +
                      "% — fan activated to prevent mold growth.");
  }
  if (newIntruder && !intruderAlert) {
    sendTelegramAlert("🚨 *INTRUDER ALERT!* Motion detected in the silo!");
  }

  fireAlert     = newFire;
  moistureAlert = newMoisture;
  intruderAlert = newIntruder;
}

// ─────────────────────────────────────────────────────────
//  ACTUATOR CONTROL
// ─────────────────────────────────────────────────────────
void controlActuators() {
  // Auto-activate exhaust fan when humidity is too high or fire detected
  fanRunning = (humidity > HUMIDITY_THRESHOLD || fireAlert);
  digitalWrite(RELAY_PIN, fanRunning ? HIGH : LOW);
}

// ─────────────────────────────────────────────────────────
//  BUZZER – non-blocking multi-stage state machine
//   Fire     → continuous solid tone (600 ms ON / 200 ms OFF)
//   Intruder → two fast beeps (100 ms ON / 100 ms OFF × 2, then 400 ms silence)
//   Normal   → silent
//
//  buzzerBeepCount: number of beeps left in the current burst.
//  When -1, the system is in the inter-burst silence gap (BUZZER_OFF state).
// ─────────────────────────────────────────────────────────
void updateBuzzer() {
  unsigned long now = millis();

  if (!fireAlert && !intruderAlert) {
    // No active alert – silence buzzer and reset state machine
    digitalWrite(BUZZER_PIN, LOW);
    buzzerState     = BUZZER_IDLE;
    buzzerBeepCount = 0;
    return;
  }

  if (fireAlert) {
    // Solid-tone pattern: 600 ms ON → 200 ms OFF → repeat
    switch (buzzerState) {
      case BUZZER_IDLE:
        digitalWrite(BUZZER_PIN, HIGH);
        buzzerState   = BUZZER_ON;
        buzzerStateAt = now;
        break;
      case BUZZER_ON:
        if (now - buzzerStateAt >= 600) {
          digitalWrite(BUZZER_PIN, LOW);
          buzzerState   = BUZZER_OFF;
          buzzerStateAt = now;
        }
        break;
      case BUZZER_OFF:
        if (now - buzzerStateAt >= 200) {
          buzzerState = BUZZER_IDLE;
        }
        break;
    }
    return;
  }

  // Intruder: 2 × (100 ms ON / 100 ms OFF) then 400 ms silence, then repeat.
  // Inter-burst silence gap is tracked by buzzerBeepCount == -1 while in BUZZER_OFF.
  switch (buzzerState) {
    case BUZZER_IDLE:
      // Start a new burst
      buzzerBeepCount = 2;
      digitalWrite(BUZZER_PIN, HIGH);
      buzzerState   = BUZZER_ON;
      buzzerStateAt = now;
      break;

    case BUZZER_ON:
      if (now - buzzerStateAt >= 100) {
        digitalWrite(BUZZER_PIN, LOW);
        buzzerState   = BUZZER_OFF;
        buzzerStateAt = now;
      }
      break;

    case BUZZER_OFF:
      if (buzzerBeepCount == -1) {
        // In silence gap – wait 400 ms then restart
        if (now - buzzerStateAt >= 400) {
          buzzerBeepCount = 0;
          buzzerState     = BUZZER_IDLE;
        }
      } else if (now - buzzerStateAt >= 100) {
        // Short OFF between beeps
        buzzerBeepCount--;
        if (buzzerBeepCount > 0) {
          // More beeps in this burst
          digitalWrite(BUZZER_PIN, HIGH);
          buzzerState   = BUZZER_ON;
          buzzerStateAt = now;
        } else {
          // Burst done – start 400 ms silence gap
          buzzerBeepCount = -1;
          buzzerStateAt   = now;
          // Remain in BUZZER_OFF; silence gap check above handles the wait
        }
      }
      break;
  }
}

// ─────────────────────────────────────────────────────────
//  THINGSPEAK CLOUD LOGGING
//   Field mapping:
//    field1 = Temperature (°C)
//    field2 = Humidity (%)
//    field3 = Gas level (raw ADC)
//    field4 = Motion (1 = detected, 0 = none)
// ─────────────────────────────────────────────────────────
void sendToThingSpeak() {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;

  String url = "http://api.thingspeak.com/update?api_key=";
  url += TS_API_KEY;
  url += "&field1=" + String(temperature, 1);
  url += "&field2=" + String(humidity, 1);
  url += "&field3=" + String(gasLevel);
  url += "&field4=" + String(motionDetected ? 1 : 0);

  http.begin(client, url);
  int httpCode = http.GET();
  if (httpCode > 0) {
    Serial.printf("[ThingSpeak] Response: %d\n", httpCode);
  } else {
    Serial.printf("[ThingSpeak] Error: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

// ─────────────────────────────────────────────────────────
//  TELEGRAM ALERT
//
//  Note on TLS: client.setInsecure() skips certificate
//  verification. This is acceptable for a hobby/embedded
//  project on a trusted LAN where the firmware itself is
//  the secret holder. For production deployments, pin the
//  Telegram server fingerprint with client.setFingerprint().
// ─────────────────────────────────────────────────────────

// Percent-encode a string for safe inclusion in a URL query parameter.
String urlEncode(const String& str) {
  String encoded = "";
  for (unsigned int i = 0; i < str.length(); i++) {
    char c = str.charAt(i);
    if (isAlphaNumeric(c) || c == '-' || c == '_' || c == '.' || c == '~') {
      encoded += c;
    } else {
      char buf[4];
      snprintf(buf, sizeof(buf), "%%%02X", (unsigned char)c);
      encoded += buf;
    }
  }
  return encoded;
}

void sendTelegramAlert(const String& message) {
  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClientSecure client;
  client.setInsecure(); // See note above regarding TLS verification
  HTTPClient http;

  String url = "https://api.telegram.org/bot";
  url += TG_BOT_TOKEN;
  url += "/sendMessage?chat_id=";
  url += TG_CHAT_ID;
  url += "&parse_mode=Markdown&text=";
  url += urlEncode(message);

  http.begin(client, url);
  int httpCode = http.GET();
  if (httpCode > 0) {
    Serial.printf("[Telegram] Response: %d\n", httpCode);
  } else {
    Serial.printf("[Telegram] Error: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

// ─────────────────────────────────────────────────────────
//  LOCAL WEB DASHBOARD
// ─────────────────────────────────────────────────────────
void handleWebRoot() {
  server.send(200, "text/html", buildDashboardHTML());
}

String buildDashboardHTML() {
  String alertBanner = "";
  if (fireAlert) {
    alertBanner = "<div class='alert fire'>🔥 FIRE ALERT – Evacuate immediately!</div>";
  } else if (intruderAlert) {
    alertBanner = "<div class='alert intruder'>🚨 INTRUDER DETECTED!</div>";
  } else if (moistureAlert) {
    alertBanner = "<div class='alert moisture'>💧 HIGH HUMIDITY – Fan activated</div>";
  }

  String fanStatus  = fanRunning      ? "<span class='on'>ON</span>"       : "<span class='off'>OFF</span>";
  String motionTxt  = motionDetected  ? "<span class='on'>DETECTED</span>" : "<span class='off'>None</span>";

  String html = "<!DOCTYPE html><html lang='en'><head>"
    "<meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<meta http-equiv='refresh' content='10'>"
    "<title>Smart Grain Silo Monitor</title>"
    "<style>"
      "* { box-sizing: border-box; margin: 0; padding: 0; }"
      "body { font-family: 'Segoe UI', Arial, sans-serif; background: #1a1a2e; color: #eee; }"
      "header { background: #16213e; padding: 20px; text-align: center; border-bottom: 3px solid #e94560; }"
      "header h1 { font-size: 1.6rem; color: #e2b96f; }"
      "header p  { font-size: 0.85rem; color: #aaa; margin-top: 4px; }"
      ".container { max-width: 700px; margin: 24px auto; padding: 0 16px; }"
      ".alert { padding: 14px 20px; border-radius: 8px; font-weight: bold; margin-bottom: 20px; font-size: 1rem; }"
      ".fire     { background: #c0392b; color: #fff; }"
      ".intruder { background: #8e44ad; color: #fff; }"
      ".moisture { background: #2980b9; color: #fff; }"
      ".grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }"
      ".card { background: #16213e; border-radius: 10px; padding: 20px; border-left: 4px solid #e94560; }"
      ".card .label { font-size: 0.75rem; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }"
      ".card .value { font-size: 2rem; font-weight: bold; margin-top: 6px; color: #e2b96f; }"
      ".card .unit  { font-size: 0.9rem; color: #ccc; }"
      ".status-row  { display: flex; justify-content: space-between; margin-top: 16px; background: #16213e; border-radius: 10px; padding: 16px 20px; }"
      ".status-item .label { font-size: 0.75rem; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }"
      ".status-item .val   { font-size: 1.1rem; font-weight: bold; margin-top: 4px; }"
      ".on  { color: #2ecc71; }"
      ".off { color: #7f8c8d; }"
      "footer { text-align: center; padding: 20px; font-size: 0.75rem; color: #555; }"
    "</style>"
    "</head><body>"
    "<header>"
      "<h1>🌾 Smart Grain Silo Monitor</h1>"
      "<p>Auto-refreshes every 10 seconds &nbsp;|&nbsp; Local IP: " + WiFi.localIP().toString() + "</p>"
    "</header>"
    "<div class='container'>";

  html += alertBanner;

  html += "<div class='grid'>"
    "<div class='card'>"
      "<div class='label'>Temperature</div>"
      "<div class='value'>" + String(temperature, 1) + "<span class='unit'> °C</span></div>"
    "</div>"
    "<div class='card'>"
      "<div class='label'>Humidity</div>"
      "<div class='value'>" + String(humidity, 1) + "<span class='unit'> %</span></div>"
    "</div>"
    "<div class='card'>"
      "<div class='label'>Gas Level (MQ-2)</div>"
      "<div class='value'>" + String(gasLevel) + "<span class='unit'> / 1023</span></div>"
    "</div>"
    "<div class='card'>"
      "<div class='label'>Gas Threshold</div>"
      "<div class='value'>" + String(GAS_THRESHOLD) + "<span class='unit'> ADC</span></div>"
    "</div>"
  "</div>"

  "<div class='status-row'>"
    "<div class='status-item'>"
      "<div class='label'>Motion</div>"
      "<div class='val'>" + motionTxt + "</div>"
    "</div>"
    "<div class='status-item'>"
      "<div class='label'>Exhaust Fan</div>"
      "<div class='val'>" + fanStatus + "</div>"
    "</div>"
    "<div class='status-item'>"
      "<div class='label'>Fire Alert</div>"
      "<div class='val'>" + (fireAlert ? "<span class='on'>YES</span>" : "<span class='off'>No</span>") + "</div>"
    "</div>"
    "<div class='status-item'>"
      "<div class='label'>Moisture Alert</div>"
      "<div class='val'>" + (moistureAlert ? "<span class='on'>YES</span>" : "<span class='off'>No</span>") + "</div>"
    "</div>"
  "</div>"

  "</div>"
  "<footer>Smart Grain Silo IoT Monitor &copy; 2025 &nbsp;|&nbsp; Powered by ESP8266</footer>"
  "</body></html>";

  return html;
}
