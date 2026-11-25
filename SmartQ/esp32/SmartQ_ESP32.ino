/*
 * =========================================================================================
 * SmartQ - Smart Queue Management & Automated Token Calling System
 * ESP32 Hardware Kiosk Firmware (Ready to Flash)
 * =========================================================================================
 * Subject: Principles of Digital Systems and Design (PDSD)
 * Target Board: DOIT ESP32 DevKit V1 (30-pin, ESP32-WROOM-32)
 *
 * Physical Breadboard Pinout (Verified & Tested):
 * -----------------------------------------------------------------------------------------
 *  Component Pin           ESP32 Pin          Pin Description / Wiring Guide
 * -----------------------------------------------------------------------------------------
 *  16x2 LCD SDA            GPIO 21 (D21)      Right side, Pin 5 from USB
 *  16x2 LCD SCL            GPIO 22 (D22)      Right side, Pin 2 from USB
 *  16x2 LCD VCC            VIN (5V)           Left side, Pin 15 (Bottom-most left pin)
 *  16x2 LCD GND            GND                Right side, Pin 14 (Next to 3V3)
 *  
 *  GET TOKEN Switch        GPIO 25 (D25)      Left side, Pin 8 from USB (Other pin -> GND)
 *  REPEAT Switch           GPIO 26 (D26)      Left side, Pin 9 from USB (Other pin -> GND)
 *  HELP Switch             GPIO 27 (D27)      Left side, Pin 10 from USB (Other pin -> GND)
 *  
 *  Active Buzzer (+)       GPIO 18 (D18)      Right side, Pin 7 from USB
 *  Active Buzzer (-)       GND                Right side, Pin 14 (Common Ground)
 * =========================================================================================
 * Required Arduino IDE Libraries:
 *  1. LiquidCrystal_I2C by Frank de Brabander (Install via Library Manager)
 *  2. ArduinoJson by Benoit Blanchon (Version 6 or 7 supported)
 *  3. WiFi.h & HTTPClient.h (Built into ESP32 board package)
 * =========================================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// =========================================================================================
// 1. Wi-Fi & Laptop Server Configuration
// =========================================================================================
const char* WIFI_SSID     = "JAGAN_KANDUKURI";
const char* WIFI_PASSWORD = "9701991892";

// Your Laptop's LAN IP where Flask app.py is running
// (Pre-configured from your ipconfig: 172.24.25.27)
const char* SERVER_HOST   = "172.24.25.27";
const int   SERVER_PORT   = 5000;

// Base API URL
String serverUrl = "http://" + String(SERVER_HOST) + ":" + String(SERVER_PORT);

// =========================================================================================
// 2. Hardware Pin Definitions
// =========================================================================================
#define PIN_LCD_SDA          21
#define PIN_LCD_SCL          22

#define PIN_BTN_GET_TOKEN    25
#define PIN_BTN_REPEAT       26
#define PIN_BTN_HELP         27

#define PIN_BUZZER           18

// LCD Dimensions
#define LCD_COLS             16
#define LCD_ROWS             2

// LiquidCrystal pointer - dynamically allocated after auto-detecting I2C address
LiquidCrystal_I2C* lcd = nullptr;
uint8_t detectedI2CAddress = 0x27;

// =========================================================================================
// 3. Timing & State Variables
// =========================================================================================
const unsigned long DEBOUNCE_DELAY       = 250;   // ms debounce for switches
const unsigned long STATUS_POLL_INTERVAL = 3000;  // Poll queue status every 3s
const unsigned long TEMP_DISPLAY_TIME    = 4000;  // Hold button messages on LCD for 4s

int lastBtnGetTokenState = HIGH;
int lastBtnRepeatState   = HIGH;
int lastBtnHelpState     = HIGH;

unsigned long lastDebounceGetToken = 0;
unsigned long lastDebounceRepeat   = 0;
unsigned long lastDebounceHelp     = 0;

unsigned long lastStatusPoll     = 0;
unsigned long tempDisplayUntil   = 0;
bool isShowingTempMessage        = false;

String lastServingToken          = "";

// =========================================================================================
// 4. Buzzer Feedback Functions
// =========================================================================================
void beep(int durationMs) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(durationMs);
  digitalWrite(PIN_BUZZER, LOW);
}

void beepShort() {
  beep(80);
}

void beepDouble() {
  beep(90);
  delay(90);
  beep(90);
}

void beepHelpAlert() {
  for (int i = 0; i < 4; i++) {
    beep(130);
    delay(90);
  }
}

void beepChime() {
  beep(60);
  delay(50);
  beep(120);
}

// =========================================================================================
// 5. LCD Helper Functions
// =========================================================================================
void showLCDMessage(const String& line0, const String& line1, unsigned long durationMs = 0) {
  if (!lcd) return;
  lcd->clear();
  lcd->setCursor(0, 0);
  lcd->print(line0.substring(0, LCD_COLS));
  lcd->setCursor(0, 1);
  lcd->print(line1.substring(0, LCD_COLS));

  if (durationMs > 0) {
    tempDisplayUntil = millis() + durationMs;
    isShowingTempMessage = true;
  }
}

// Automatically scans I2C bus to find whether LCD is at 0x27 or 0x3F
uint8_t detectLCDAddress() {
  Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
  uint8_t possibleAddresses[] = {0x27, 0x3F, 0x20, 0x38};

  for (uint8_t addr : possibleAddresses) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("[I2C SCAN] Found 16x2 LCD at address: 0x%02X\n", addr);
      return addr;
    }
  }
  Serial.println("[I2C SCAN] Warning: LCD not detected, defaulting to 0x27");
  return 0x27;
}

// =========================================================================================
// 6. Network Connection Helper
// =========================================================================================
void connectWiFi() {
  showLCDMessage("SmartQ Kiosk", "Connecting WiFi..");
  Serial.print("[WiFi] Connecting to: ");
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
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] ESP32 IP: ");
    Serial.println(WiFi.localIP());

    beepShort();
    showLCDMessage("WiFi Connected!", WiFi.localIP().toString(), 2500);
  } else {
    Serial.println("\n[WiFi] Connection Failed! Check SSID/Password or AP Isolation.");
    beepDouble();
    showLCDMessage("WiFi Failed!", "Check Hotspot", 3000);
  }
}

// =========================================================================================
// 7. Event Handler 1: GET TOKEN (GPIO 25) - Generates Token Instantly
// =========================================================================================
void handleGetToken() {
  Serial.println("\n>>> [EVENT] GET TOKEN Switch Triggered!");
  showLCDMessage("Generating Token", "Please wait...");
  beepShort();

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      showLCDMessage("Error: No WiFi", "Connect Hotspot", 2500);
      return;
    }
  }

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/token";
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(4000);

  // Send direct token generation request
  int httpCode = http.POST("{\"direct\": true}");

  if (httpCode == 200 || httpCode == 201) {
    String payload = http.getString();
    Serial.printf("[HTTP %d] Token Response: %s\n", httpCode, payload.c_str());

    #if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
    #else
      StaticJsonDocument<512> doc;
    #endif

    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      const char* tNo = doc["token_no"] | "1";
      const char* l0  = doc["lcd_line0"] | "Walk-in Patient";
      const char* l1  = doc["lcd_line1"] | "Token: 1";

      beepDouble();
      showLCDMessage(String(l0), String(l1), TEMP_DISPLAY_TIME);
      Serial.printf("[SUCCESS] New Token Issued: #%s\n", tNo);
    } else {
      beepDouble();
      showLCDMessage("TOKEN ISSUED!", "Check Screen", TEMP_DISPLAY_TIME);
    }
  } else {
    Serial.printf("[HTTP ERROR] Failed with code: %d\n", httpCode);
    showLCDMessage("Server Error", "Code: " + String(httpCode), 2500);
  }

  http.end();
}

// =========================================================================================
// 8. Event Handler 2: REPEAT CALL (GPIO 26) - Repeats Active Token Voice
// =========================================================================================
void handleRepeatCall() {
  Serial.println("\n>>> [EVENT] REPEAT Switch Triggered!");
  showLCDMessage("Repeating Call..", "Please listen..");

  if (WiFi.status() != WL_CONNECTED) {
    showLCDMessage("Error: No WiFi", "Cannot repeat", 2000);
    return;
  }

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/repeat";
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000);

  int httpCode = http.POST("{}");

  if (httpCode == 200) {
    beepDouble();
    showLCDMessage("CALL REPEATED!", "Voice Re-played", 2500);
    Serial.println("[SUCCESS] Voice Announcement repeated on server!");
  } else {
    beepShort();
    showLCDMessage("No Active Token", "Counter Idle", 2000);
    Serial.println("[INFO] No active calling token to repeat.");
  }

  http.end();
}

// =========================================================================================
// 9. Event Handler 3: HELP (GPIO 27) - Triggers Urgent Assistance Alert
// =========================================================================================
void handleHelpRequest() {
  Serial.println("\n>>> [EVENT] HELP Switch Triggered!");
  showLCDMessage("! HELP CALLED !", "Staff Notified..");

  // Urgent local audible alert
  beepHelpAlert();

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String endpoint = serverUrl + "/api/device/help";
    http.begin(endpoint);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(3000);

    int httpCode = http.POST("{}");
    Serial.printf("[HTTP %d] Help Alert Sent to Dashboard!\n", httpCode);
    http.end();
  }

  showLCDMessage("! HELP CALLED !", "Staff is Coming", 3500);
}

// =========================================================================================
// 10. Background Poller: Fetches Real-Time Queue Status for 16x2 LCD
// =========================================================================================
void pollServerStatus() {
  if (WiFi.status() != WL_CONNECTED || isShowingTempMessage) return;

  HTTPClient http;
  String endpoint = serverUrl + "/api/device/status";
  http.begin(endpoint);
  http.setTimeout(2500);

  int httpCode = http.GET();

  if (httpCode == 200) {
    String payload = http.getString();

    #if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
    #else
      StaticJsonDocument<512> doc;
    #endif

    DeserializationError err = deserializeJson(doc, payload);

    if (!err) {
      const char* l0 = doc["lcd_line0"] | "SmartQ Counter 1";
      const char* l1 = doc["lcd_line1"] | "Ready";
      String line0 = String(l0);
      String line1 = String(l1);
      const char* serv = doc["serving"] | "";
      String serving = String(serv);

      // Sound chime if a new token was just called by the staff counter
      if (serving.length() > 0 && serving != "None" && serving != lastServingToken && lastServingToken.length() > 0) {
        beepChime();
        Serial.printf("[ALERT] New Token Called: %s\n", serving.c_str());
      }
      lastServingToken = serving;

      // Update LCD display lines
      if (!isShowingTempMessage && lcd) {
        lcd->setCursor(0, 0);
        while (line0.length() < LCD_COLS) line0 += " ";
        lcd->print(line0.substring(0, LCD_COLS));

        lcd->setCursor(0, 1);
        while (line1.length() < LCD_COLS) line1 += " ";
        lcd->print(line1.substring(0, LCD_COLS));
      }
    }
  }

  http.end();
}

// =========================================================================================
// 11. Arduino Setup
// =========================================================================================
void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println("\n==================================================");
  Serial.println("  SmartQ ESP32 DevKit V1 Hardware Initializing   ");
  Serial.println("==================================================");

  // Initialize Buzzer
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize Switches with Internal Pullup
  pinMode(PIN_BTN_GET_TOKEN, INPUT_PULLUP);
  pinMode(PIN_BTN_REPEAT,    INPUT_PULLUP);
  pinMode(PIN_BTN_HELP,      INPUT_PULLUP);

  // Record initial switch states
  lastBtnGetTokenState = digitalRead(PIN_BTN_GET_TOKEN);
  lastBtnRepeatState   = digitalRead(PIN_BTN_REPEAT);
  lastBtnHelpState     = digitalRead(PIN_BTN_HELP);

  // Scan and Initialize I2C LCD
  detectedI2CAddress = detectLCDAddress();
  lcd = new LiquidCrystal_I2C(detectedI2CAddress, LCD_COLS, LCD_ROWS);
  lcd->init();
  lcd->backlight();
  lcd->clear();

  // Power-on confirmation beep
  beepShort();

  // Connect to Local Wi-Fi
  connectWiFi();
}

// =========================================================================================
// 12. Arduino Main Loop
// =========================================================================================
void loop() {
  unsigned long currentMillis = millis();

  // Check if temporary notification display has expired
  if (isShowingTempMessage && currentMillis >= tempDisplayUntil) {
    isShowingTempMessage = false;
    if (lcd) lcd->clear();
  }

  // -------------------------------------------------------------
  // Switch 1: GET TOKEN (GPIO 25)
  // -------------------------------------------------------------
  int readingGetToken = digitalRead(PIN_BTN_GET_TOKEN);
  if ((currentMillis - lastDebounceGetToken) > DEBOUNCE_DELAY) {
    if (readingGetToken != lastBtnGetTokenState) {
      lastDebounceGetToken = currentMillis;
      lastBtnGetTokenState = readingGetToken;
      handleGetToken();
    }
  }

  // -------------------------------------------------------------
  // Switch 2: REPEAT (GPIO 26)
  // -------------------------------------------------------------
  int readingRepeat = digitalRead(PIN_BTN_REPEAT);
  if ((currentMillis - lastDebounceRepeat) > DEBOUNCE_DELAY) {
    if (readingRepeat != lastBtnRepeatState) {
      lastDebounceRepeat = currentMillis;
      lastBtnRepeatState = readingRepeat;
      handleRepeatCall();
    }
  }

  // -------------------------------------------------------------
  // Switch 3: HELP (GPIO 27)
  // -------------------------------------------------------------
  int readingHelp = digitalRead(PIN_BTN_HELP);
  if ((currentMillis - lastDebounceHelp) > DEBOUNCE_DELAY) {
    if (readingHelp != lastBtnHelpState) {
      lastDebounceHelp = currentMillis;
      lastBtnHelpState = readingHelp;
      handleHelpRequest();
    }
  }

  // -------------------------------------------------------------
  // Periodic Background Polling for LCD Screen (Every 3 seconds)
  // -------------------------------------------------------------
  if (currentMillis - lastStatusPoll >= STATUS_POLL_INTERVAL) {
    lastStatusPoll = currentMillis;
    pollServerStatus();
  }

  // Auto-reconnect Wi-Fi if connection dropped
  if (WiFi.status() != WL_CONNECTED && (currentMillis % 10000 < 60)) {
    Serial.println("[WiFi] Connection lost. Attempting reconnect...");
    WiFi.reconnect();
  }
}
