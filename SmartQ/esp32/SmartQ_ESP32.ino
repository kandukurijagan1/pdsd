/*
 * =========================================================================================
 * SmartQ - Smart Queue Management & Automated Token Calling System
 * ESP32 Hardware Kiosk Firmware
 * =========================================================================================
 * Subject: Principles of Digital Systems and Design (PDSD)
 * Target Board: ESP32 DevKit V1 (ESP32-WROOM-32)
 *
 * Circuit Connections:
 * -----------------------------------------------------------------------------------------
 *  Component              ESP32 Pin          Connection Notes
 * -----------------------------------------------------------------------------------------
 *  16x2 LCD SDA          GPIO 21            Connect to I2C SDA (check pullup voltage)
 *  16x2 LCD SCL          GPIO 22            Connect to I2C SCL (check pullup voltage)
 *  16x2 LCD VCC          VIN (5V) or 3.3V   According to LCD backpack specification
 *  16x2 LCD GND          GND                Common GND
 *  GET TOKEN Button      GPIO 25            Connect one side to GPIO 25, other to GND
 *  REPEAT Button         GPIO 26            Connect one side to GPIO 26, other to GND
 *  HELP Button           GPIO 27            Connect one side to GPIO 27, other to GND
 *  Active Buzzer (+)     GPIO 18            Signal pin (3.3V active buzzer / driver)
 *  Active Buzzer (-)     GND                Common GND
 * =========================================================================================
 * Required Arduino Libraries:
 *  - LiquidCrystal_I2C by Frank de Brabander (or Marco Schwartz)
 *  - WiFi.h (Built-in ESP32 core)
 *  - HTTPClient.h (Built-in ESP32 core)
 *  - ArduinoJson by Benoit Blanchon (Version 6 or 7)
 * =========================================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// =========================================================================================
// Network & Server Configuration (Update these to match your Wi-Fi & Laptop LAN IP)
// =========================================================================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";         // e.g. "College-WiFi" or Phone Hotspot
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";     // Wi-Fi Password

// Laptop IP where Flask is running (run 'ipconfig' on Windows to verify)
const char* SERVER_HOST   = "192.168.1.100";          // Replace with your laptop LAN IP
const int   SERVER_PORT   = 5000;                     // Flask server port

// Base API URL
String serverUrl = "http://" + String(SERVER_HOST) + ":" + String(SERVER_PORT);

// =========================================================================================
// Hardware Pin Definitions
// =========================================================================================
#define PIN_LCD_SDA          21
#define PIN_LCD_SCL          22

#define PIN_BTN_GET_TOKEN    25
#define PIN_BTN_REPEAT       26
#define PIN_BTN_HELP         27

#define PIN_BUZZER           18

// I2C LCD Configuration (Standard addresses: 0x27 or 0x3F)
#define LCD_I2C_ADDR         0x27
#define LCD_COLS             16
#define LCD_ROWS             2

LiquidCrystal_I2C lcd(LCD_I2C_ADDR, LCD_COLS, LCD_ROWS);

// =========================================================================================
// Button Debounce & Timing Parameters
// =========================================================================================
const unsigned long DEBOUNCE_DELAY       = 60;    // milliseconds
const unsigned long STATUS_POLL_INTERVAL = 3000;  // Poll server every 3s
const unsigned long TEMP_DISPLAY_TIME    = 3500;  // Keep message on screen for 3.5s

// Button States
int lastBtnGetTokenState = HIGH;
int lastBtnRepeatState   = HIGH;
int lastBtnHelpState     = HIGH;

unsigned long lastDebounceGetToken = 0;
unsigned long lastDebounceRepeat   = 0;
unsigned long lastDebounceHelp     = 0;

// System Timers
unsigned long lastStatusPoll = 0;
unsigned long tempDisplayUntil = 0;
bool isShowingTempMessage = false;

// Last known queue status
String lastServingToken = "None";
int lastWaitingCount = 0;

// =========================================================================================
// Helper: Buzzer Patterns
// =========================================================================================
void beep(int durationMs) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(durationMs);
  digitalWrite(PIN_BUZZER, LOW);
}

void beepShort() {
  beep(100);
}

void beepDouble() {
  beep(80);
  delay(80);
  beep(80);
}

void beepHelpAlert() {
  for (int i = 0; i < 4; i++) {
    beep(120);
    delay(80);
  }
}

// =========================================================================================
// LCD Display Helpers
// =========================================================================================
void showLCDMessage(const String& line0, const String& line1, unsigned long durationMs = 0) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line0.substring(0, LCD_COLS));
  lcd.setCursor(0, 1);
  lcd.print(line1.substring(0, LCD_COLS));

  if (durationMs > 0) {
    tempDisplayUntil = millis() + durationMs;
    isShowingTempMessage = true;
  }
}

// =========================================================================================
// Network Connection
// =========================================================================================
void connectWiFi() {
  showLCDMessage("SmartQ Kiosk", "Connecting WiFi...");
  Serial.print("Connecting to Wi-Fi SSID: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(400);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi Connected successfully!");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    beepShort();
    showLCDMessage("WiFi Connected!", WiFi.localIP().toString(), 2000);
  } else {
    Serial.println("\nWiFi Connection Failed! Check SSID/Password.");
    beepDouble();
    showLCDMessage("WiFi Failed!", "Check Router", 3000);
  }
}

// =========================================================================================
// API Request 1: Start Voice-Guided Registration (GET TOKEN Button)
// =========================================================================================
void handleGetToken() {
  Serial.println("\n[EVENT] GET TOKEN Button Pressed! Starting Voice Assistant...");
  showLCDMessage("Speak Your Name", "Listening Mic...");
  beepShort();

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      showLCDMessage("Error: No WiFi", "Try again later", 2500);
      return;
    }
  }

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/voice-session/start";
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST("{}");
  if (httpCode == 200 || httpCode == 201) {
    Serial.println("Voice Assistant session activated on kiosk!");
  }
  http.end();
}

// =========================================================================================
// API Request 2: Repeat Announcement (REPEAT Button)
// =========================================================================================
void handleRepeatCall() {
  Serial.println("\n[EVENT] REPEAT Button Pressed!");
  showLCDMessage("Repeating Call..", "Speaking token..");

  if (WiFi.status() != WL_CONNECTED) {
    showLCDMessage("Error: No WiFi", "Cannot repeat", 2000);
    return;
  }

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/repeat";
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST("{}");

  if (httpCode == 200) {
    beepDouble();
    showLCDMessage("Call Repeated!", "Listen speaker", 2500);
  } else {
    beepShort();
    showLCDMessage("No Token Active", "Counter Ready", 2000);
  }

  http.end();
}

// =========================================================================================
// API Request 3: Help / Assistance Alert (HELP Button)
// =========================================================================================
void handleHelpRequest() {
  Serial.println("\n[EVENT] HELP Button Pressed!");
  showLCDMessage("HELP REQUESTED!", "Staff Notified..");

  // Immediate local urgent beep
  beepHelpAlert();

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String endpoint = serverUrl + "/api/device/help";
    http.begin(endpoint);
    http.addHeader("Content-Type", "application/json");

    int httpCode = http.POST("{}");
    Serial.print("Help Alert Sent, HTTP Code: ");
    Serial.println(httpCode);
    http.end();
  }

  showLCDMessage("HELP REQUESTED!", "Please wait here", 3000);
}

// =========================================================================================
// Background Task: Poll Server for Live Serving Token & Queue Status
// =========================================================================================
void pollServerStatus() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/status";
  http.begin(endpoint);
  http.setTimeout(2000);

  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();
    StaticJsonDocument<384> doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error && doc["success"]) {
      String line0 = doc["lcd_line0"].as<String>();
      String line1 = doc["lcd_line1"].as<String>();

      if (!isShowingTempMessage) {
        lcd.setCursor(0, 0);
        while (line0.length() < LCD_COLS) line0 += " ";
        lcd.print(line0.substring(0, LCD_COLS));

        lcd.setCursor(0, 1);
        while (line1.length() < LCD_COLS) line1 += " ";
        lcd.print(line1.substring(0, LCD_COLS));
      }
    }
  }

  http.end();
}

// =========================================================================================
// Arduino Setup
// =========================================================================================
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n--- SmartQ ESP32 DevKit V1 Initializing ---");

  // Initialize Buzzer
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize Push Buttons with internal pullups
  pinMode(PIN_BTN_GET_TOKEN, INPUT_PULLUP);
  pinMode(PIN_BTN_REPEAT,    INPUT_PULLUP);
  pinMode(PIN_BTN_HELP,      INPUT_PULLUP);

  // Initialize I2C and LCD
  Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
  lcd.init();
  lcd.backlight();
  lcd.clear();

  // Test beep
  beepShort();

  // Connect to Wi-Fi
  connectWiFi();
}

// =========================================================================================
// Arduino Main Loop
// =========================================================================================
void loop() {
  unsigned long currentMillis = millis();

  // Check if temporary message display expired
  if (isShowingTempMessage && currentMillis >= tempDisplayUntil) {
    isShowingTempMessage = false;
    lcd.clear();
  }

  // -------------------------------------------------------------
  // Button 1: GET TOKEN (GPIO 25)
  // -------------------------------------------------------------
  int readingGetToken = digitalRead(PIN_BTN_GET_TOKEN);
  if (readingGetToken != lastBtnGetTokenState) {
    lastDebounceGetToken = currentMillis;
  }
  if ((currentMillis - lastDebounceGetToken) > DEBOUNCE_DELAY) {
    if (readingGetToken == LOW && lastBtnGetTokenState == HIGH) {
      handleGetToken();
    }
  }
  lastBtnGetTokenState = readingGetToken;

  // -------------------------------------------------------------
  // Button 2: REPEAT (GPIO 26)
  // -------------------------------------------------------------
  int readingRepeat = digitalRead(PIN_BTN_REPEAT);
  if (readingRepeat != lastBtnRepeatState) {
    lastDebounceRepeat = currentMillis;
  }
  if ((currentMillis - lastDebounceRepeat) > DEBOUNCE_DELAY) {
    if (readingRepeat == LOW && lastBtnRepeatState == HIGH) {
      handleRepeatCall();
    }
  }
  lastBtnRepeatState = readingRepeat;

  // -------------------------------------------------------------
  // Button 3: HELP (GPIO 27)
  // -------------------------------------------------------------
  int readingHelp = digitalRead(PIN_BTN_HELP);
  if (readingHelp != lastBtnHelpState) {
    lastDebounceHelp = currentMillis;
  }
  if ((currentMillis - lastDebounceHelp) > DEBOUNCE_DELAY) {
    if (readingHelp == LOW && lastBtnHelpState == HIGH) {
      handleHelpRequest();
    }
  }
  lastBtnHelpState = readingHelp;

  // -------------------------------------------------------------
  // Periodic Background Polling (Every 3 seconds)
  // -------------------------------------------------------------
  if (currentMillis - lastStatusPoll >= STATUS_POLL_INTERVAL) {
    lastStatusPoll = currentMillis;
    pollServerStatus();
  }

  // Auto-reconnect Wi-Fi if connection lost
  if (WiFi.status() != WL_CONNECTED && (currentMillis % 10000 < 50)) {
    Serial.println("Wi-Fi connection lost. Attempting reconnect...");
    WiFi.reconnect();
  }
}
