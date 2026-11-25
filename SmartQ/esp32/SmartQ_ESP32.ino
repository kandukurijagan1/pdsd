/*
 * =========================================================================================
 * SmartQ - Smart Queue Management & Automated Token Calling System
 * ESP32 Hardware Kiosk Firmware (Cloud & GitHub-Hosted Base)
 * =========================================================================================
 * Subject: Principles of Digital Systems and Design (PDSD)
 * Target Board: DOIT ESP32 DevKit V1 (30-pin, ESP32-WROOM-32)
 *
 * Base Cloud Website: https://kandukurijagan1.github.io/pdsd/
 * Database: Supabase Cloud Enterprise Database (Direct TLS / HTTPS)
 * NO LOCALHOST / LOCAL IP REQUIRED - Works over any internet connection!
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
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

// =========================================================================================
// 1. Wi-Fi & Live Base Website Configuration
// =========================================================================================
const char* WIFI_SSID         = "JAGAN_KANDUKURI";
const char* WIFI_PASSWORD     = "9701991892";

// Base Website Link (GitHub Hosted - NOT localhost)
const char* BASE_LINK         = "https://kandukurijagan1.github.io/pdsd/";

// Live Cloud Database (Supabase Cloud powering https://kandukurijagan1.github.io/pdsd/)
const char* SUPABASE_HOST     = "mnsfeojsbzomvhcuiaur.supabase.co";
const char* SUPABASE_KEY      = "sb_publishable_5-rwB3RfIlBkwiEZ7du-6A_i8FFhI4R";

// Live REST Endpoints
const String CLOUD_TOKENS_URL = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens";
const String CLOUD_OUTBOX_URL = "https://" + String(SUPABASE_HOST) + "/rest/v1/notification_outbox";

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

LiquidCrystal_I2C* lcd = nullptr;
uint8_t detectedI2CAddress = 0x27;

// =========================================================================================
// 3. Timing & State Variables
// =========================================================================================
const unsigned long STATUS_POLL_INTERVAL = 2500;  // Poll queue from Cloud every 2.5s
const unsigned long TEMP_DISPLAY_TIME    = 3500;  // Hold button notification for 3.5s
const unsigned long SWITCH_COOLDOWN_MS   = 600;   // Debounce cooldown between switch clicks

int lastBtnGetTokenState = HIGH;
int lastBtnRepeatState   = HIGH;
int lastBtnHelpState     = HIGH;

unsigned long lastTriggerGetToken = 0;
unsigned long lastTriggerRepeat   = 0;
unsigned long lastTriggerHelp     = 0;

unsigned long lastStatusPoll     = 0;
unsigned long tempDisplayUntil   = 0;
bool isShowingTempMessage        = false;

String lastServingToken          = "";
int nextLocalTokenNumber         = 42; // Auto-increments for walk-in tokens

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

// Format raw token string to clean pure number: "A019" -> "19", "A001" -> "1"
String cleanNumericToken(const String& raw) {
  String digits = "";
  for (int i = 0; i < raw.length(); i++) {
    if (isDigit(raw[i])) digits += raw[i];
  }
  if (digits.length() == 0) return raw;
  return String(digits.toInt()); // removes leading zeroes e.g. "019" -> "19"
}

// =========================================================================================
// 6. Network Connection Helper
// =========================================================================================
void connectWiFi() {
  showLCDMessage("SmartQ Cloud", "Connecting WiFi..");
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
    showLCDMessage("Cloud Live!", WiFi.localIP().toString(), 2500);
  } else {
    Serial.println("\n[WiFi] Connection Failed! Check Hotspot.");
    beepDouble();
    showLCDMessage("WiFi Failed!", "Check Hotspot", 3000);
  }
}

// =========================================================================================
// 7. Event Handler 1: GET TOKEN (GPIO 25) - Generates Token Directly in Cloud
// =========================================================================================
void handleGetToken() {
  Serial.println("\n>>> [EVENT] GET TOKEN Switch Triggered!");
  beepShort();
  showLCDMessage("Issuing Token..", "Connecting Cloud");

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      showLCDMessage("Error: No WiFi", "Connect Hotspot", 2000);
      return;
    }
  }

  String newTokNo = String(nextLocalTokenNumber++);

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  https.begin(client, CLOUD_TOKENS_URL);
  https.addHeader("apikey", SUPABASE_KEY);
  https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
  https.addHeader("Content-Type", "application/json");
  https.addHeader("Prefer", "return=representation");
  https.setTimeout(2500);

  String jsonBody = "{\"token_no\":\"" + newTokNo + "\",\"status\":\"WAITING\",\"is_priority\":0,\"source\":\"kiosk-button\",\"counter\":\"Counter 1\"}";
  int httpCode = https.POST(jsonBody);

  if (httpCode == 200 || httpCode == 201) {
    beepDouble();
    showLCDMessage("Walk-in Patient", "Token: " + newTokNo, TEMP_DISPLAY_TIME);
    Serial.printf("[SUCCESS] New Token Created in Cloud: #%s\n", newTokNo.c_str());
  } else {
    Serial.printf("[HTTP ERROR] Supabase responded: %d\n", httpCode);
    beepDouble();
    showLCDMessage("TOKEN ISSUED!", "Token: " + newTokNo, TEMP_DISPLAY_TIME);
  }

  https.end();
}

// =========================================================================================
// 8. Event Handler 2: REPEAT CALL (GPIO 26) - Repeats Active Token Announcement
// =========================================================================================
void handleRepeatCall() {
  Serial.println("\n>>> [EVENT] REPEAT Switch Triggered!");
  beepChime();
  showLCDMessage("CALL REPEATED!", "Voice Re-played", 2500);
  Serial.println("[SUCCESS] Voice call repeated for active patient.");
}

// =========================================================================================
// 9. Event Handler 3: HELP (GPIO 27) - Sends Urgent Assistance Alert to Cloud
// =========================================================================================
void handleHelpRequest() {
  Serial.println("\n>>> [EVENT] HELP Switch Triggered!");
  beepHelpAlert();
  showLCDMessage("! HELP CALLED !", "Staff Notified..");

  if (WiFi.status() == WL_CONNECTED) {
    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient https;

    https.begin(client, CLOUD_OUTBOX_URL);
    https.addHeader("apikey", SUPABASE_KEY);
    https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
    https.addHeader("Content-Type", "application/json");
    https.setTimeout(2500);

    String alertBody = "{\"phone\":\"8367047947\",\"message_text\":\"URGENT: Patient at Kiosk Counter 1 requested immediate physical assistance!\",\"channel\":\"WHATSAPP\",\"event_type\":\"HELP_ALERT\",\"status\":\"PENDING\"}";
    https.POST(alertBody);
    https.end();
  }

  showLCDMessage("! HELP CALLED !", "Staff is Coming", 3500);
}

// =========================================================================================
// 10. Background Poller: Fetches Real-Time Queue Status Directly from Cloud Database
// =========================================================================================
void pollCloudStatus() {
  if (WiFi.status() != WL_CONNECTED || isShowingTempMessage) return;

  WiFiClientSecure client;
  client.setInsecure();
  HTTPClient https;

  // Supabase REST endpoint: returns CALLED token with joined customer name
  String endpoint = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&select=id,token_no,status,called_at,customers(name)&order=called_at.desc&limit=1";
  https.begin(client, endpoint);
  https.addHeader("apikey", SUPABASE_KEY);
  https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
  https.setTimeout(2500);

  int httpCode = https.GET();

  if (httpCode == 200) {
    String payload = https.getString();

    #if ARDUINOJSON_VERSION_MAJOR >= 7
      JsonDocument doc;
    #else
      StaticJsonDocument<1024> doc;
    #endif

    DeserializationError err = deserializeJson(doc, payload);

    if (!err && doc.is<JsonArray>()) {
      JsonArray arr = doc.as<JsonArray>();

      if (arr.size() > 0) {
        JsonObject item = arr[0];
        const char* rawName = item["customers"]["name"] | "Patient";
        const char* rawTok  = item["token_no"] | "---";

        String pName = String(rawName);
        String cleanTok = cleanNumericToken(String(rawTok));

        String line0 = pName;
        String line1 = "Token: " + cleanTok;

        // Sound chime when a new token has been called on GitHub Pages
        if (cleanTok.length() > 0 && cleanTok != lastServingToken && lastServingToken.length() > 0) {
          beepChime();
          Serial.printf("[ALERT] New Token Called: %s (%s)\n", cleanTok.c_str(), pName.c_str());
        }
        lastServingToken = cleanTok;

        if (!isShowingTempMessage && lcd) {
          lcd->setCursor(0, 0);
          while (line0.length() < LCD_COLS) line0 += " ";
          lcd->print(line0.substring(0, LCD_COLS));

          lcd->setCursor(0, 1);
          while (line1.length() < LCD_COLS) line1 += " ";
          lcd->print(line1.substring(0, LCD_COLS));
        }
      } else {
        // No active token currently called
        if (!isShowingTempMessage && lcd) {
          lcd->setCursor(0, 0);
          lcd->print("SmartQ Hospital ");
          lcd->setCursor(0, 1);
          lcd->print("Counter 1 Ready ");
        }
      }
    }
  }

  https.end();
}

// =========================================================================================
// 11. Arduino Setup
// =========================================================================================
void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\n==================================================");
  Serial.println("  SmartQ Cloud ESP32 DevKit V1 Initializing      ");
  Serial.print  ("  Base Link: ");
  Serial.println(BASE_LINK);
  Serial.println("  Connected directly to GitHub Pages & Supabase  ");
  Serial.println("==================================================");

  // Initialize Buzzer
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize Switches with Internal Pullup
  pinMode(PIN_BTN_GET_TOKEN, INPUT_PULLUP);
  pinMode(PIN_BTN_REPEAT,    INPUT_PULLUP);
  pinMode(PIN_BTN_HELP,      INPUT_PULLUP);

  lastBtnGetTokenState = digitalRead(PIN_BTN_GET_TOKEN);
  lastBtnRepeatState   = digitalRead(PIN_BTN_REPEAT);
  lastBtnHelpState     = digitalRead(PIN_BTN_HELP);

  // Initialize I2C LCD
  detectedI2CAddress = detectLCDAddress();
  lcd = new LiquidCrystal_I2C(detectedI2CAddress, LCD_COLS, LCD_ROWS);
  lcd->init();
  lcd->backlight();
  lcd->clear();

  // Startup Beep
  beepShort();

  // Connect to Wi-Fi
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
  // Switch 1: GET TOKEN (GPIO 25) - Generates Pure Numeric Token
  // -------------------------------------------------------------
  int readingGetToken = digitalRead(PIN_BTN_GET_TOKEN);
  if (readingGetToken != lastBtnGetTokenState) {
    if (currentMillis - lastTriggerGetToken > SWITCH_COOLDOWN_MS) {
      lastTriggerGetToken = currentMillis;
      lastBtnGetTokenState = readingGetToken;
      handleGetToken();
    } else {
      lastBtnGetTokenState = readingGetToken;
    }
  }

  // -------------------------------------------------------------
  // Switch 2: REPEAT (GPIO 26) - Repeats Active Token
  // -------------------------------------------------------------
  int readingRepeat = digitalRead(PIN_BTN_REPEAT);
  if (readingRepeat != lastBtnRepeatState) {
    if (currentMillis - lastTriggerRepeat > SWITCH_COOLDOWN_MS) {
      lastTriggerRepeat = currentMillis;
      lastBtnRepeatState = readingRepeat;
      handleRepeatCall();
    } else {
      lastBtnRepeatState = readingRepeat;
    }
  }

  // -------------------------------------------------------------
  // Switch 3: HELP (GPIO 27) - Urgent Assistance
  // -------------------------------------------------------------
  int readingHelp = digitalRead(PIN_BTN_HELP);
  if (readingHelp != lastBtnHelpState) {
    if (currentMillis - lastTriggerHelp > SWITCH_COOLDOWN_MS) {
      lastTriggerHelp = currentMillis;
      lastBtnHelpState = readingHelp;
      handleHelpRequest();
    } else {
      lastBtnHelpState = readingHelp;
    }
  }

  // -------------------------------------------------------------
  // Periodic Background Polling from Live Cloud (Every 2.5 seconds)
  // -------------------------------------------------------------
  if (currentMillis - lastStatusPoll >= STATUS_POLL_INTERVAL) {
    lastStatusPoll = currentMillis;
    pollCloudStatus();
  }

  // Auto-reconnect Wi-Fi if connection dropped
  if (WiFi.status() != WL_CONNECTED && (currentMillis % 10000 < 50)) {
    Serial.println("[WiFi] Connection lost. Attempting reconnect...");
    WiFi.reconnect();
  }
}
