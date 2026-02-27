#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <DHT.h>
#include <ESP8266HTTPClient.h>  // ---> NEW: For Telegram
#include <WiFiClientSecure.h>   // ---> NEW: For Secure Telegram connection

// ---> WI-FI CREDENTIALS <---
const char* ssid = "Prakash-thinkpad";      
const char* password = "12345678";

// ---> THINGSPEAK DETAILS <---
const char* apiKey = "RM25QSPWM80IK75K"; 
const char* serverName = "api.thingspeak.com";

// ---> TELEGRAM DETAILS <---
String botToken = "8602575235:AAGDqaayoe70_Ju1QBZaEZfeaYlMZfmfzqk";
String chatId = "2142292504"; 
unsigned long lastTelegramMsg = 0; // Cooldown timer

#define DHTPIN D4       
#define DHTTYPE DHT11  
#define PIR_PIN D5      
#define BUZZER_PIN D7  
#define GAS_PIN A0      
#define RELAY_PIN D6    // Exhaust Fan Relay

// ---> HARDWARE CHEAT CODE <---
#define RELAY_ON LOW    // For Active-LOW relays
#define RELAY_OFF HIGH  

DHT dht(DHTPIN, DHTTYPE);
ESP8266WebServer server(80);
WiFiClient client;

unsigned long lastCloudUpload = 0; 

float temp = 0.0;
float hum = 0.0;
int gasValue = 0;
int motion = 0;
String alertStatus = "SAFE";
bool isFanRunning = false; 

// ==========================================
// TELEGRAM SEND FUNCTION
// ==========================================
void sendTelegram(String message) {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure clientSecure;
    clientSecure.setInsecure(); // Connect securely without certificate

    HTTPClient http;
    message.replace(" ", "%20"); // Format spaces for URL
    String url = "https://api.telegram.org/bot" + botToken + "/sendMessage?chat_id=" + chatId + "&text=" + message;
    
    http.begin(clientSecure, url);
    int httpCode = http.GET();
    
    if (httpCode == 200) {
      Serial.println("✅ Telegram Alert Sent Successfully!");
    } else {
      Serial.println("❌ Telegram Error: " + String(httpCode));
    }
    http.end();
  }
}

// ==========================================
// UPGRADED PROFESSIONAL UI DASHBOARD
// ==========================================
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><title>Smart Silo Dashboard</title>";
  html += "<meta charset='UTF-8'>"; 
  html += "<meta name='viewport' content='width=device-width, initial-scale=1'>";
  html += "<meta http-equiv='refresh' content='2'>";
  
  html += "<style>";
  html += "body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #e8f5e9; color: #1b5e20; margin: 0; padding: 20px; text-align: center; }";
  html += "h1 { margin-bottom: 5px; font-size: 2.2em; color: #2e7d32; }";
  html += "p.subtitle { color: #4caf50; font-size: 1.1em; margin-top: 0; margin-bottom: 30px; font-weight: bold; }";
  html += ".grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; max-width: 900px; margin: 0 auto; }";
  html += ".card { background: white; border-radius: 15px; padding: 25px; width: 200px; box-shadow: 0 6px 12px rgba(0,0,0,0.1); border-top: 6px solid #4caf50; transition: transform 0.2s; }";
  html += ".card:hover { transform: translateY(-5px); }";
  html += ".card h3 { margin: 0; font-size: 1.2em; color: #757575; text-transform: uppercase; letter-spacing: 1px; }";
  html += ".card .value { font-size: 2.5em; font-weight: bold; margin: 15px 0 0 0; color: #2e7d32; }";
  html += ".status-banner { margin: 10px auto 30px auto; padding: 20px; border-radius: 10px; max-width: 860px; font-size: 1.8em; font-weight: bold; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }";
  html += ".safe { background-color: #4caf50; color: white; }";
  html += ".danger { background-color: #d32f2f; color: white; animation: blink 1s linear infinite; }";
  html += "@keyframes blink { 50% { opacity: 0.8; } }";
  html += ".motion-card { background: white; border-radius: 15px; padding: 20px; width: 80%; max-width: 640px; margin: 30px auto; box-shadow: 0 6px 12px rgba(0,0,0,0.15); border-top: 6px solid #2196f3; }";
  html += ".motion-card h3 { margin: 0; font-size: 1.4em; color: #555; text-transform: uppercase; letter-spacing: 1px; }";
  html += "</style></head><body>";

  html += "<h1>🌾 Smart Grain Silo</h1>";
  html += "<p class='subtitle'>Real-Time Agricultural Monitoring System</p>";

  // Main Status Banner
  if (alertStatus == "SAFE") {
    html += "<div class='status-banner safe'>✅ SYSTEM STATUS: " + alertStatus + "</div>";
  } else {
    html += "<div class='status-banner danger'>🚨 SYSTEM STATUS: " + alertStatus + "</div>";
  }

  html += "<div class='grid'>";

  html += "<div class='card'><h3>Temperature</h3><div class='value'>" + String(temp, 1) + " &deg;C</div></div>";
  html += "<div class='card'><h3>Humidity</h3><div class='value'>" + String(hum, 1) + " %</div></div>";
  html += "<div class='card' style='border-top-color: #ff9800;'><h3>Gas/Smoke</h3><div class='value' style='color:#f57c00;'>" + String(gasValue) + "</div></div>";
  
  // Exhaust Fan UI Card
  if (isFanRunning) {
    html += "<div class='card' style='border-top-color: #9c27b0;'><h3>Exhaust Fan</h3><div class='value' style='color:#9c27b0; font-size: 1.8em; margin-top:25px;'>⚙️ PURGING AIR</div></div>";
  } else {
    html += "<div class='card' style='border-top-color: #9e9e9e;'><h3>Exhaust Fan</h3><div class='value' style='color:#757575; font-size: 1.8em; margin-top:25px;'>OFF</div></div>";
  }

  html += "</div>"; 

  // Motion Card
  if (motion == HIGH) {
    html += "<div class='motion-card' style='border-top-color: #f44336;'><h3>PIR Motion Sensor</h3><div class='value' style='color:#d32f2f; font-size: 2.2em; font-weight:bold; margin-top:15px;'>🚨 MOVEMENT DETECTED! 🚨</div></div>";
  } else {
    html += "<div class='motion-card'><h3>PIR Motion Sensor</h3><div class='value' style='color:#1976d2; font-size: 2.2em; font-weight:bold; margin-top:15px;'>No Motion</div></div>";
  }

  html += "</body></html>";
  server.send(200, "text/html", html);
}

// ==========================================
// STANDARD SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(115200);
  
  pinMode(PIR_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT); 
  
  // Force fan OFF immediately on startup using our cheat code
  digitalWrite(RELAY_PIN, RELAY_OFF); 
  
  dht.begin();

  Serial.println("\n--- Starting Smart Grain Monitor ---");
  Serial.print("Connecting to WiFi");
  
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print("."); 
  }
  
  Serial.println("\nWiFi Connected!");
  Serial.print("IP Address for your Webpage: ");
  Serial.println(WiFi.localIP()); 

  server.on("/", handleRoot);
  server.begin();
}

void loop() {
  server.handleClient();
  
  gasValue = analogRead(GAS_PIN);
  motion = digitalRead(PIR_PIN);
  
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) temp = t;
  if (!isnan(h)) hum = h;

  // ---> AUTOMATED EXHAUST FAN LOGIC <---
  if (hum > 50.0 || gasValue > 90) {
    digitalWrite(RELAY_PIN, RELAY_ON); // Turn Fan ON
    isFanRunning = true;
  } else {
    digitalWrite(RELAY_PIN, RELAY_OFF);  // Turn Fan OFF safely
    isFanRunning = false;
  }

  // ---> MULTI-STAGE ALARM LOGIC (WITH TELEGRAM) <---
  if (gasValue > 90 || hum > 60.0) {
    alertStatus = "SPOILAGE ALERT!";
    digitalWrite(BUZZER_PIN, HIGH); // Solid beep for fire
    
    if (millis() - lastTelegramMsg > 60000) { // 60s cooldown
      sendTelegram("🚨 CRITICAL ALERT: High Gas/Smoke detected in Grain Silo!");
      lastTelegramMsg = millis();
    }
  }
  else if (hum > 60.0) {
    alertStatus = "HIGH HUMIDITY ALERT!";
    digitalWrite(BUZZER_PIN, HIGH); 
    delay(300);
    digitalWrite(BUZZER_PIN, LOW);  // Slow warning beep
    delay(300);
    
    if (millis() - lastTelegramMsg > 60000) { // 60s cooldown
      sendTelegram("💧 CLIMATE ALERT: Moisture > 50%. Exhaust Fan activated to purge air.");
      lastTelegramMsg = millis();
    }
  }
  else if (motion == HIGH) {
    alertStatus = "INTRUDER DETECTED!";
    digitalWrite(BUZZER_PIN, HIGH);
    delay(150);
    digitalWrite(BUZZER_PIN, LOW);  // Fast beep for intruder
    delay(150);
    
    if (millis() - lastTelegramMsg > 60000) { // 60s cooldown
      sendTelegram("⚠️ SECURITY ALERT: Motion detected at Grain Silo hatch!");
      lastTelegramMsg = millis();
    }
  }
  else {
    alertStatus = "SAFE";
    digitalWrite(BUZZER_PIN, LOW);
  }
  
  // ---> THINGSPEAK CLOUD UPLOAD (Every 20 Seconds) <---
  if (millis() - lastCloudUpload > 20000) {
    if (WiFi.status() == WL_CONNECTED) {
      if (client.connect(serverName, 80)) {
        String postStr = apiKey;
        postStr += "&field1=" + String(temp);
        postStr += "&field2=" + String(hum);
        postStr += "&field3=" + String(gasValue);
        postStr += "&field4=" + String(motion); 
        postStr += "\r\n\r\n";

        client.print("POST /update HTTP/1.1\n");
        client.print("Host: api.thingspeak.com\n");
        client.print("Connection: close\n");
        client.print("X-THINGSPEAKAPIKEY: " + String(apiKey) + "\n");            
        client.print("Content-Type: application/x-www-form-urlencoded\n");
        client.print("Content-Length: " + String(postStr.length()) + "\n\n");
        client.print(postStr);
        
        Serial.println("Data sent to ThingSpeak!");
        lastCloudUpload = millis();
      }
      client.stop();
    }
  }

  delay(100);
}