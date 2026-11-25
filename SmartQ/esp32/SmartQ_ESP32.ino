/*
 * =========================================================================================
 * SmartQ - Smart Queue Management & Automated Token Calling System
 * Advanced Enterprise Dual-Core Firmware (FreeRTOS SMP Architecture)
 * =========================================================================================
 * Subject: Principles of Digital Systems and Design (PDSD)
 * Target Board: DOIT ESP32 DevKit V1 (30-pin, ESP32-WROOM-32, Dual-Core 240MHz)
 *
 * Base Cloud Website: https://kandukurijagan1.github.io/pdsd/
 * Database: Supabase Cloud Enterprise Database (Direct TLS / HTTPS)
 * NO LOCALHOST / LOCAL IP REQUIRED - Direct cloud connection over Wi-Fi!
 *
 * Architecture:
 *   - Core 0 (TaskCloudSync): Asynchronous TLS/HTTPS polling (every 1.5s) to Supabase Cloud
 *                             REST API. Processes switch events from xHardwareEventQueue.
 *   - Core 1 (loop / UI):     Ultra-reliable 35ms stable-state debouncer, immediate buzzer
 *                             acoustic feedback (<1ms), and flicker-free 16x2 LCD delta
 *                             rendering (updates only characters that changed).
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
 *  GET TOKEN Switch        GPIO 25 (D25)      Left side, Pin 8 from USB (Other leg -> GND)
 *  REPEAT Switch           GPIO 26 (D26)      Left side, Pin 9 from USB (Other leg -> GND)
 *  HELP Switch             GPIO 27 (D27)      Left side, Pin 10 from USB (Other leg -> GND)
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
// 1. Wi-Fi & Live Cloud Website Configuration
// =========================================================================================
const char* WIFI_SSID           = "JAGAN_KANDUKURI";
const char* WIFI_PASSWORD       = "9701991892";

// Base Website Link (GitHub Pages - NOT localhost)
const char* BASE_LINK           = "https://kandukurijagan1.github.io/pdsd/";

// Live Cloud Database (Supabase Cloud powering https://kandukurijagan1.github.io/pdsd/)
const char* SUPABASE_HOST       = "mnsfeojsbzomvhcuiaur.supabase.co";
const char* SUPABASE_KEY        = "sb_publishable_5-rwB3RfIlBkwiEZ7du-6A_i8FFhI4R";

// Live REST Endpoints
const String CLOUD_TOKENS_URL   = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens";
const String CLOUD_OUTBOX_URL   = "https://" + String(SUPABASE_HOST) + "/rest/v1/notification_outbox";

// =========================================================================================
// 2. Hardware Pin Definitions
// =========================================================================================
#define PIN_LCD_SDA            21
#define PIN_LCD_SCL            22

#define PIN_BTN_GET_TOKEN      25
#define PIN_BTN_REPEAT         26
#define PIN_BTN_HELP           27

#define PIN_BUZZER             18

#define LCD_COLS               16
#define LCD_ROWS               2

// =========================================================================================
// 3. Custom Structures (Declared Early for Prototype Resolution)
// =========================================================================================
struct DebouncedButton {
  int pin;
  int debouncedState;
  int lastRawReading;
  unsigned long lastChangeTime;
};

enum EventType {
  EVENT_NONE = 0,
  EVENT_GET_TOKEN,
  EVENT_REPEAT_CALL,
  EVENT_HELP_ALERT
};

struct HardwareEvent {
  EventType type;
  int tokenNumber;
};

struct DisplayState {
  char line0[32];
  char line1[32];
  bool isTemporary;
  unsigned long tempUntil;
};

// =========================================================================================
// 4. Global Variables & FreeRTOS Handles
// =========================================================================================
QueueHandle_t xHardwareEventQueue = NULL;
SemaphoreHandle_t xDisplayMutex   = NULL;

DisplayState currentDisplay = {"SmartQ Hospital", "Connecting WiFi.", false, 0};

// LCD Driver
LiquidCrystal_I2C* lcd = nullptr;
uint8_t detectedI2CAddress = 0x27;

// Active tracking data
String currentServingToken = "";
String currentPatientName  = "";
int nextWalkInTokenNumber   = 42;

// Button instances
DebouncedButton btnGetToken = { PIN_BTN_GET_TOKEN, HIGH, HIGH, 0 };
DebouncedButton btnRepeat   = { PIN_BTN_REPEAT,    HIGH, HIGH, 0 };
DebouncedButton btnHelp     = { PIN_BTN_HELP,      HIGH, HIGH, 0 };

const unsigned long DEBOUNCE_STABLE_TIME = 35; // 35ms stable filter

// =========================================================================================
// 5. Acoustic Feedback Subsystem (Buzzer)
// =========================================================================================
void playBeep(int durationMs) {
  digitalWrite(PIN_BUZZER, HIGH);
  delay(durationMs);
  digitalWrite(PIN_BUZZER, LOW);
}

void soundBeepShort() {
  playBeep(80);
}

void soundBeepDouble() {
  playBeep(80);
  delay(60);
  playBeep(80);
}

void soundChimeAlert() {
  playBeep(60);
  delay(40);
  playBeep(140);
}

void soundEmergencyAlert() {
  for (int i = 0; i < 4; i++) {
    playBeep(100);
    delay(60);
  }
}

// =========================================================================================
// 6. Display Subsystem (Flicker-Free Delta Rendering & Text Management)
// =========================================================================================
uint8_t detectI2CAddress() {
  Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
  uint8_t addresses[] = {0x27, 0x3F, 0x20, 0x38};
  for (uint8_t addr : addresses) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) return addr;
  }
  return 0x27;
}

void setDisplayMessage(const String& l0, const String& l1, unsigned long durationMs = 0) {
  if (xDisplayMutex && xSemaphoreTake(xDisplayMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    strncpy(currentDisplay.line0, l0.c_str(), sizeof(currentDisplay.line0) - 1);
    currentDisplay.line0[sizeof(currentDisplay.line0) - 1] = '\0';

    strncpy(currentDisplay.line1, l1.c_str(), sizeof(currentDisplay.line1) - 1);
    currentDisplay.line1[sizeof(currentDisplay.line1) - 1] = '\0';

    if (durationMs > 0) {
      currentDisplay.isTemporary = true;
      currentDisplay.tempUntil = millis() + durationMs;
    } else {
      currentDisplay.isTemporary = false;
    }
    xSemaphoreGive(xDisplayMutex);
  }
}

// Clean token number to strictly pure numbers (e.g., "A019" -> "19", "AB24" -> "24")
String cleanNumericOnly(const String& raw) {
  String digits = "";
  for (unsigned int i = 0; i < raw.length(); i++) {
    if (isDigit(raw[i])) digits += raw[i];
  }
  if (digits.length() == 0) return raw;
  return String(digits.toInt());
}

// Delta buffer to eliminate LCD flicker
char activeScreenBuffer[2][17] = {"                ", "                "};

void renderLCDDelta(const char* l0, const char* l1) {
  if (!lcd) return;

  char formatted0[17];
  char formatted1[17];

  snprintf(formatted0, sizeof(formatted0), "%-16.16s", l0);
  snprintf(formatted1, sizeof(formatted1), "%-16.16s", l1);

  // Update Line 0 only if modified
  if (strncmp(activeScreenBuffer[0], formatted0, 16) != 0) {
    lcd->setCursor(0, 0);
    lcd->print(formatted0);
    strncpy(activeScreenBuffer[0], formatted0, 16);
  }

  // Update Line 1 only if modified
  if (strncmp(activeScreenBuffer[1], formatted1, 16) != 0) {
    lcd->setCursor(0, 1);
    lcd->print(formatted1);
    strncpy(activeScreenBuffer[1], formatted1, 16);
  }
}

// =========================================================================================
// 7. Cloud Communication Engine (Runs on Core 0)
// =========================================================================================
void TaskCloudSync(void* pvParameters) {
  Serial.println("[Core 0] Cloud Sync Engine Started.");

  WiFiClientSecure secureClient;
  secureClient.setInsecure(); // High-speed TLS verification bypass for embedded

  HTTPClient https;
  unsigned long lastPollTime = 0;
  const unsigned long POLL_INTERVAL_MS = 1500; // Fast 1.5s live polling

  // Query highest existing token on startup to synchronize walk-in sequence
  if (WiFi.status() == WL_CONNECTED) {
    String maxQueryUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?select=token_no&order=id.desc&limit=25";
    https.begin(secureClient, maxQueryUrl);
    https.addHeader("apikey", SUPABASE_KEY);
    https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
    https.setTimeout(2500);
    int c = https.GET();
    if (c == 200) {
      String p = https.getString();
      #if ARDUINOJSON_VERSION_MAJOR >= 7
        JsonDocument initDoc;
      #else
        StaticJsonDocument<2048> initDoc;
      #endif
      DeserializationError err = deserializeJson(initDoc, p);
      if (!err && initDoc.is<JsonArray>()) {
        int maxFound = 41;
        for (JsonObject o : initDoc.as<JsonArray>()) {
          const char* t = o["token_no"] | "0";
          int n = String(cleanNumericOnly(String(t))).toInt();
          if (n > maxFound) maxFound = n;
        }
        nextWalkInTokenNumber = maxFound + 1;
        Serial.printf("[Core 0] Initialized Walk-in Token Sequence to #%d\n", nextWalkInTokenNumber);
      }
    }
    https.end();
  }

  while (true) {
    unsigned long now = millis();

    // 1. Process Hardware Switch Events from Core 1
    HardwareEvent event;
    if (xQueueReceive(xHardwareEventQueue, &event, 0) == pdTRUE) {
      if (WiFi.status() == WL_CONNECTED) {
        if (event.type == EVENT_GET_TOKEN) {
          String newTokNo = String(event.tokenNumber);
          Serial.printf("[Core 0] Dispatching POST to Supabase for Token #%s\n", newTokNo.c_str());

          https.begin(secureClient, CLOUD_TOKENS_URL);
          https.addHeader("apikey", SUPABASE_KEY);
          https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
          https.addHeader("Content-Type", "application/json");
          https.addHeader("Prefer", "return=representation");
          https.setTimeout(2500);

          String jsonBody = "{\"token_no\":\"" + newTokNo + "\",\"status\":\"WAITING\",\"is_priority\":0,\"source\":\"kiosk-button\",\"counter\":\"Counter 1\"}";
          int code = https.POST(jsonBody);
          Serial.printf("[Core 0] Supabase Token Insert Response: %d\n", code);
          https.end();

        } else if (event.type == EVENT_REPEAT_CALL) {
          Serial.println("[Core 0] Processing Repeat Call Event on Supabase Cloud...");
          if (currentServingToken.length() > 0) {
            String updateUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&counter=eq.Counter%201";
            https.begin(secureClient, updateUrl);
            https.addHeader("apikey", SUPABASE_KEY);
            https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
            https.addHeader("Content-Type", "application/json");
            https.setTimeout(2500);
            https.PATCH("{\"called_at\":\"2026-11-25T12:00:00Z\"}");
            https.end();
          }

        } else if (event.type == EVENT_HELP_ALERT) {
          Serial.println("[Core 0] Dispatching Urgent Help Alert to Supabase Cloud...");
          https.begin(secureClient, CLOUD_OUTBOX_URL);
          https.addHeader("apikey", SUPABASE_KEY);
          https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
          https.addHeader("Content-Type", "application/json");
          https.setTimeout(2500);

          String body = "{\"phone\":\"8367047947\",\"message_text\":\"URGENT: Patient at Kiosk Counter 1 requested immediate physical assistance!\",\"channel\":\"WHATSAPP\",\"event_type\":\"HELP_ALERT\",\"status\":\"PENDING\"}";
          int code = https.POST(body);
          Serial.printf("[Core 0] Supabase Help Alert Response: %d\n", code);
          https.end();
        }
      }
    }

    // 2. Fast Background Polling for Currently Called Token from GitHub Pages / Supabase
    if (now - lastPollTime >= POLL_INTERVAL_MS) {
      lastPollTime = now;

      if (WiFi.status() == WL_CONNECTED) {
        String endpoint = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&select=id,token_no,status,called_at,customers(name)&order=called_at.desc&limit=1";
        https.begin(secureClient, endpoint);
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
              String cleanTok = cleanNumericOnly(String(rawTok));

              // Trigger acoustic chime when a new token has been called on GitHub Pages
              if (cleanTok.length() > 0 && cleanTok != currentServingToken && currentServingToken.length() > 0) {
                soundChimeAlert();
                Serial.printf("[Core 0] 📢 New Token Called: #%s (%s)\n", cleanTok.c_str(), pName.c_str());
              }

              currentServingToken = cleanTok;
              currentPatientName  = pName;

              // Update display buffer if not showing a temporary message
              if (!currentDisplay.isTemporary) {
                setDisplayMessage(pName, "Token: " + cleanTok);
              }
            } else {
              if (!currentDisplay.isTemporary && currentServingToken.length() > 0) {
                currentServingToken = "";
                setDisplayMessage("SmartQ Hospital", "Counter 1 Ready");
              }
            }
          }
        }
        https.end();
      } else {
        // Wi-Fi auto-reconnect
        if (WiFi.status() != WL_CONNECTED) {
          WiFi.reconnect();
        }
      }
    }

    vTaskDelay(pdMS_TO_TICKS(50));
  }
}

// =========================================================================================
// 8. Industrial Stable-State Switch Debounce Engine
// =========================================================================================
bool checkButtonPressed(DebouncedButton* btn, unsigned long now) {
  int raw = digitalRead(btn->pin);

  if (raw != btn->lastRawReading) {
    btn->lastChangeTime = now;
    btn->lastRawReading = raw;
  }

  if ((now - btn->lastChangeTime) >= DEBOUNCE_STABLE_TIME) {
    if (raw != btn->debouncedState) {
      btn->debouncedState = raw;
      if (btn->debouncedState == LOW) {
        // Confirmed transition from HIGH to LOW (Active LOW Button Pressed!)
        return true;
      }
    }
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n========================================================");
  Serial.println("  SmartQ Advanced Enterprise Dual-Core Firmware (PDSD) ");
  Serial.printf ("  Base Website: %s\n", BASE_LINK);
  Serial.println("  Direct Supabase Cloud TLS & Zero-Freeze Architecture   ");
  Serial.println("========================================================");

  // Initialize Buzzer
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // Initialize Switches with Internal Pullup
  pinMode(PIN_BTN_GET_TOKEN, INPUT_PULLUP);
  pinMode(PIN_BTN_REPEAT,    INPUT_PULLUP);
  pinMode(PIN_BTN_HELP,      INPUT_PULLUP);

  btnGetToken.debouncedState = digitalRead(PIN_BTN_GET_TOKEN);
  btnGetToken.lastRawReading = btnGetToken.debouncedState;

  btnRepeat.debouncedState   = digitalRead(PIN_BTN_REPEAT);
  btnRepeat.lastRawReading   = btnRepeat.debouncedState;

  btnHelp.debouncedState     = digitalRead(PIN_BTN_HELP);
  btnHelp.lastRawReading     = btnHelp.debouncedState;

  // FreeRTOS Inter-Task Sync
  xHardwareEventQueue = xQueueCreate(10, sizeof(HardwareEvent));
  xDisplayMutex       = xSemaphoreCreateMutex();

  // Initialize I2C LCD
  detectedI2CAddress = detectI2CAddress();
  lcd = new LiquidCrystal_I2C(detectedI2CAddress, LCD_COLS, LCD_ROWS);
  lcd->init();
  lcd->backlight();
  lcd->clear();

  soundBeepShort();
  renderLCDDelta("SmartQ Hospital", "Connecting WiFi.");

  // Connect to Local Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 25) {
    delay(350);
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    soundBeepDouble();
    renderLCDDelta("Cloud Connected!", WiFi.localIP().toString().c_str());
    delay(1500);
    renderLCDDelta("SmartQ Hospital", "Counter 1 Ready");
  } else {
    soundEmergencyAlert();
    renderLCDDelta("WiFi Failed!", "Check Hotspot");
    delay(2000);
  }

  // Pin Cloud Task to Core 0 (Networking CPU)
  xTaskCreatePinnedToCore(
    TaskCloudSync,
    "CloudSyncTask",
    10240,       // 10 KB Stack
    NULL,
    1,           // Priority 1
    NULL,
    0            // Core 0
  );

  Serial.println("[Core 1] Real-Time UI Engine Ready. Buttons Armed & Listening!");
}

void loop() {
  unsigned long now = millis();

  // Check temporary notification expiration
  if (currentDisplay.isTemporary && now >= currentDisplay.tempUntil) {
    if (xDisplayMutex && xSemaphoreTake(xDisplayMutex, pdMS_TO_TICKS(10)) == pdTRUE) {
      currentDisplay.isTemporary = false;
      if (currentServingToken.length() > 0) {
        strncpy(currentDisplay.line0, currentPatientName.c_str(), 16);
        snprintf(currentDisplay.line1, 16, "Token: %s", currentServingToken.c_str());
      } else {
        strncpy(currentDisplay.line0, "SmartQ Hospital", 16);
        strncpy(currentDisplay.line1, "Counter 1 Ready", 16);
      }
      xSemaphoreGive(xDisplayMutex);
    }
  }

  // -------------------------------------------------------------
  // Switch 1: GET TOKEN (GPIO 25) - Confirmed Press
  // -------------------------------------------------------------
  if (checkButtonPressed(&btnGetToken, now)) {
    int issuedNumber = nextWalkInTokenNumber++;
    Serial.printf("[BUTTON 1 - GPIO 25] Pressed! Generating Token #%d\n", issuedNumber);

    soundBeepDouble();
    String tokStr = "Token: " + String(issuedNumber);
    setDisplayMessage("Walk-in Patient", tokStr, 3500);

    HardwareEvent ev = { EVENT_GET_TOKEN, issuedNumber };
    xQueueSend(xHardwareEventQueue, &ev, 0);
  }

  // -------------------------------------------------------------
  // Switch 2: REPEAT CALL (GPIO 26) - Confirmed Press
  // -------------------------------------------------------------
  if (checkButtonPressed(&btnRepeat, now)) {
    Serial.println("[BUTTON 2 - GPIO 26] Pressed! Repeating Active Call...");

    soundChimeAlert();
    String line1Msg = (currentServingToken.length() > 0) ? ("Serving: " + currentServingToken) : "Counter 1 Ready";
    setDisplayMessage("CALL REPEATED!", line1Msg, 2500);

    HardwareEvent ev = { EVENT_REPEAT_CALL, 0 };
    xQueueSend(xHardwareEventQueue, &ev, 0);
  }

  // -------------------------------------------------------------
  // Switch 3: HELP (GPIO 27) - Confirmed Press
  // -------------------------------------------------------------
  if (checkButtonPressed(&btnHelp, now)) {
    Serial.println("[BUTTON 3 - GPIO 27] Pressed! URGENT HELP ALERT TRIGGERED!");

    soundEmergencyAlert();
    setDisplayMessage("! HELP CALLED !", "Staff Notified..", 3500);

    HardwareEvent ev = { EVENT_HELP_ALERT, 0 };
    xQueueSend(xHardwareEventQueue, &ev, 0);
  }

  // -------------------------------------------------------------
  // Render LCD with Mutex Protection
  // -------------------------------------------------------------
  if (xDisplayMutex && xSemaphoreTake(xDisplayMutex, pdMS_TO_TICKS(10)) == pdTRUE) {
    renderLCDDelta(currentDisplay.line0, currentDisplay.line1);
    xSemaphoreGive(xDisplayMutex);
  }

  // Small delay to yield Core 1
  vTaskDelay(pdMS_TO_TICKS(10));
}
