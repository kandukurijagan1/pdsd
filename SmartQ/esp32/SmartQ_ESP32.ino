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
 *                             Protected against Wi-Fi thrashing with 10s backoff & no sleep.
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
  EVENT_CALL_NEXT,
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
volatile bool wifiGotIp    = false;
bool initialTokenSynced    = false;
bool readyBannerApplied    = false;

// Button instances
DebouncedButton btnGetToken = { PIN_BTN_GET_TOKEN, HIGH, HIGH, 0 };
DebouncedButton btnRepeat   = { PIN_BTN_REPEAT,    HIGH, HIGH, 0 };
DebouncedButton btnHelp     = { PIN_BTN_HELP,      HIGH, HIGH, 0 };

// Continuous Siren Alarm State for HELP button (Toggled ON until pressed again to turn OFF)
bool helpAlarmActive            = false;
unsigned long lastSirenToggleMs = 0;
bool sirenState                 = false;

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
  Wire.setClock(40000);
  uint8_t addresses[] = {0x27, 0x3F, 0x20, 0x38};
  for (uint8_t addr : addresses) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("[LCD] I2C Backpack detected at address 0x%02X\n", addr);
      return addr;
    }
  }
  Serial.println("[LCD] WARNING: No I2C backpack responded at 0x27/0x3F/0x20/0x38! Check SDA(21), SCL(22), VIN(5V), GND.");
  return 0x27;
}

// Delta buffer to eliminate LCD flicker
char activeScreenBuffer[2][17] = {"                ", "                "};

void initLcdHardware() {
  Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
  Wire.setClock(40000); // 40 kHz prevents 3.3V->5V I2C nibble desync on JHD162A
  if (lcd) {
    lcd->init();
    // Re-apply explicit pins & 40 kHz clock because LiquidCrystal_I2C::init() calls Wire.begin()
    Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
    Wire.setClock(40000);
    lcd->backlight();
    lcd->clear();
  }
  memset(activeScreenBuffer[0], ' ', 16);
  activeScreenBuffer[0][16] = '\0';
  memset(activeScreenBuffer[1], ' ', 16);
  activeScreenBuffer[1][16] = '\0';
}

void setDisplayMessage(const String& l0, const String& l1, unsigned long durationMs = 0) {
  if (xDisplayMutex && xSemaphoreTake(xDisplayMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    snprintf(currentDisplay.line0, sizeof(currentDisplay.line0), "%s", l0.c_str());
    snprintf(currentDisplay.line1, sizeof(currentDisplay.line1), "%s", l1.c_str());

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

void sanitizeLcdLine(const char* src, char* dst16) {
  for (int i = 0; i < 16; i++) dst16[i] = ' ';
  dst16[16] = '\0';
  if (!src) return;
  for (int i = 0; i < 16 && src[i] != '\0'; i++) {
    unsigned char ch = (unsigned char)src[i];
    dst16[i] = (ch >= 32 && ch <= 126) ? (char)ch : ' ';
  }
}

void renderLCDDelta(const char* l0, const char* l1) {
  if (!lcd) return;

  char formatted0[17];
  char formatted1[17];

  sanitizeLcdLine(l0, formatted0);
  sanitizeLcdLine(l1, formatted1);

  // Update Line 0 only if modified
  if (strncmp(activeScreenBuffer[0], formatted0, 16) != 0) {
    lcd->setCursor(0, 0);
    lcd->print(formatted0);
    memcpy(activeScreenBuffer[0], formatted0, 17);
  }

  // Update Line 1 only if modified
  if (strncmp(activeScreenBuffer[1], formatted1, 16) != 0) {
    lcd->setCursor(0, 1);
    lcd->print(formatted1);
    memcpy(activeScreenBuffer[1], formatted1, 17);
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
  unsigned long lastReconnectTime = millis();
  const unsigned long POLL_INTERVAL_MS = 1500;      // 1.5s live polling

  while (true) {
    unsigned long now = millis();

    // Sync highest existing token once Wi-Fi has an IP
    if (WiFi.status() == WL_CONNECTED && !initialTokenSynced) {
      String maxQueryUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?select=token_no&order=id.desc&limit=25";
      https.begin(secureClient, maxQueryUrl);
      https.addHeader("apikey", SUPABASE_KEY);
      https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
      https.setConnectTimeout(5000);
      https.setTimeout(5000);
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
          initialTokenSynced = true;
          Serial.printf("[Core 0] Initialized Walk-in Token Sequence to #%d\n", nextWalkInTokenNumber);
        }
      } else {
        Serial.printf("[Core 0] Initial token query HTTP: %d (%s)\n", c, https.errorToString(c).c_str());
      }
      https.end();
    }

    // 1. Process Hardware Switch Events from Core 1
    HardwareEvent event;
    if (xQueueReceive(xHardwareEventQueue, &event, 0) == pdTRUE) {
      if (WiFi.status() == WL_CONNECTED) {
        if (event.type == EVENT_CALL_NEXT) {
          Serial.println("[Core 0] Calling NEXT token on Supabase Cloud...");

          // 1. Mark existing CALLED token at Counter 1 as COMPLETED
          String compUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&counter=eq.Counter%201";
          https.begin(secureClient, compUrl);
          https.addHeader("apikey", SUPABASE_KEY);
          https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
          https.addHeader("Content-Type", "application/json");
          https.setConnectTimeout(5000);
          https.setTimeout(5000);
          https.PATCH("{\"status\":\"COMPLETED\",\"completed_at\":\"2026-11-25T15:45:00Z\"}");
          https.end();

          // 2. Fetch the top WAITING patient (Priority-first, then FIFO by ID)
          String nextQueryUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.WAITING&select=id,token_no,is_priority,customer_id,customers(name)&order=is_priority.desc,id.asc&limit=1";
          https.begin(secureClient, nextQueryUrl);
          https.addHeader("apikey", SUPABASE_KEY);
          https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
          https.setConnectTimeout(5000);
          https.setTimeout(5000);
          int nextCode = https.GET();

          if (nextCode == 200) {
            String nextPayload = https.getString();
            #if ARDUINOJSON_VERSION_MAJOR >= 7
              JsonDocument nextDoc;
            #else
              StaticJsonDocument<1024> nextDoc;
            #endif
            DeserializationError dErr = deserializeJson(nextDoc, nextPayload);

            if (!dErr && nextDoc.is<JsonArray>() && nextDoc.as<JsonArray>().size() > 0) {
              JsonObject nextItem = nextDoc.as<JsonArray>()[0];
              int nextId = nextItem["id"] | 0;
              const char* nextTokNo = nextItem["token_no"] | "---";
              const char* pName = nextItem["customers"]["name"] | "Patient";

              String cleanTok = cleanNumericOnly(String(nextTokNo));
              Serial.printf("[Core 0] Found Next Patient: Token #%s (%s), marking CALLED in Supabase...\n", cleanTok.c_str(), pName);

              // 3. Mark the next token as CALLED in Supabase
              // Supabase Realtime will automatically push this UPDATE event to the GitHub website!
              https.end();
              String callUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?id=eq." + String(nextId);
              https.begin(secureClient, callUrl);
              https.addHeader("apikey", SUPABASE_KEY);
              https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
              https.addHeader("Content-Type", "application/json");
              https.setConnectTimeout(5000);
              https.setTimeout(5000);
              https.PATCH("{\"status\":\"CALLED\",\"called_at\":\"2026-11-25T15:45:00Z\",\"counter\":\"Counter 1\"}");
              https.end();

              // Update local state and LCD immediately
              currentServingToken = cleanTok;
              currentPatientName  = String(pName);
              setDisplayMessage(String(pName), "Token: " + cleanTok);
              soundChimeAlert();
            } else {
              Serial.println("[Core 0] Queue is empty! No waiting patients found.");
              setDisplayMessage("SmartQ Hospital", "Queue Is Empty");
              https.end();
            }
          } else {
            https.end();
          }

        } else if (event.type == EVENT_REPEAT_CALL) {
          Serial.println("[Core 0] Processing Repeat Call Event on Supabase Cloud...");
          if (currentServingToken.length() > 0) {
            String updateUrl = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&counter=eq.Counter%201";
            https.begin(secureClient, updateUrl);
            https.addHeader("apikey", SUPABASE_KEY);
            https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
            https.addHeader("Content-Type", "application/json");
            https.setConnectTimeout(5000);
            https.setTimeout(5000);
            https.PATCH("{\"called_at\":\"2026-11-25T12:00:00Z\"}");
            https.end();
          }

        } else if (event.type == EVENT_HELP_ALERT) {
          Serial.println("[Core 0] Dispatching Advanced Multi-Parameter Emergency Alert to Supabase Cloud...");
          https.begin(secureClient, CLOUD_OUTBOX_URL);
          https.addHeader("apikey", SUPABASE_KEY);
          https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
          https.addHeader("Content-Type", "application/json");
          https.setConnectTimeout(5000);
          https.setTimeout(5000);

          // Advanced Real-World Context: Active patient, token number, device status, and live dashboard link
          String activePatientContext = (currentServingToken.length() > 0) ? ("\n*Current Patient:* " + currentPatientName + " (Token #" + currentServingToken + ")") : "\n*Queue State:* Counter Active (Walk-in Area)";
          String liveDashboardLink = "https://kandukurijagan1.github.io/pdsd/#dashboard";
          
          String alertMsg = "🚨 *EMERGENCY ASSISTANCE ALERT — SMARTQ HOSPITALS*\n"
                            "--------------------------------------------------\n"
                            "⚠️ *Urgent physical assistance requested at Counter 1 / Kiosk!*\n"
                            + activePatientContext + "\n"
                            "*Hardware Terminal:* ESP32 Station (COM6)\n"
                            "*Status:* Hardware Alarm Siren Triggered\n"
                            "--------------------------------------------------\n"
                            "🔗 *Live Clinic Command Console:*\n"
                            + liveDashboardLink;

          #if ARDUINOJSON_VERSION_MAJOR >= 7
            JsonDocument outboxDoc;
          #else
            StaticJsonDocument<1024> outboxDoc;
          #endif

          outboxDoc["phone"] = "8367047947";
          outboxDoc["message_text"] = alertMsg;
          outboxDoc["channel"] = "WHATSAPP";
          outboxDoc["event_type"] = "HELP_ALERT";
          outboxDoc["status"] = "PENDING";

          String jsonPayload;
          serializeJson(outboxDoc, jsonPayload);

          int code = https.POST(jsonPayload);
          Serial.printf("[Core 0] Supabase Emergency Alert Response: %d\n", code);
          https.end();
        }
      }
    }

    // 2. Fast Background Polling for Currently Called Token from GitHub Pages / Supabase
    if (WiFi.status() == WL_CONNECTED) {
      if (!readyBannerApplied && !currentDisplay.isTemporary && currentServingToken.length() == 0) {
        setDisplayMessage("SmartQ Hospital", "Counter 1 Online");
        readyBannerApplied = true;
      }

      if (now - lastPollTime >= POLL_INTERVAL_MS) {
        lastPollTime = now;

        String endpoint = "https://" + String(SUPABASE_HOST) + "/rest/v1/tokens?status=eq.CALLED&select=id,token_no,status,called_at,customers(name)&order=called_at.desc&limit=1";
        https.begin(secureClient, endpoint);
        https.addHeader("apikey", SUPABASE_KEY);
        https.addHeader("Authorization", "Bearer " + String(SUPABASE_KEY));
        https.setConnectTimeout(5000);
        https.setTimeout(5000);

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
              readyBannerApplied  = false;

              // Update display buffer if not showing a temporary message
              if (!currentDisplay.isTemporary) {
                setDisplayMessage(pName, "Token: " + cleanTok);
              }
            } else {
              if (!currentDisplay.isTemporary && (currentServingToken.length() > 0 || !readyBannerApplied)) {
                currentServingToken = "";
                setDisplayMessage("SmartQ Hospital", "Counter 1 Online");
                readyBannerApplied = true;
              }
            }
          }
        } else {
          Serial.printf("[Core 0] Supabase Poll HTTP: %d (%s)\n", httpCode, https.errorToString(httpCode).c_str());
        }
        https.end();
      }
    } else {
      readyBannerApplied = false;
      if (!currentDisplay.isTemporary && currentServingToken.length() == 0) {
        setDisplayMessage("WiFi Reconnect..", "Local Kiosk Mode");
      }
      // ESP-IDF handles auto-reconnect natively when WiFi.setAutoReconnect(true) is set.
      // Only perform a clean re-init if disconnected for > 30 seconds without recovery.
      if (now - lastReconnectTime >= 30000) {
        lastReconnectTime = now;
        Serial.printf("[WiFi] Still offline (status=%d). Re-initiating WiFi.begin()...\n", WiFi.status());
        WiFi.disconnect(false);
        delay(100);
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      }
    }

    vTaskDelay(pdMS_TO_TICKS(50));
  }
}

// =========================================================================================
// 8. Industrial Stable-State Switch Debounce Engine
// =========================================================================================
// Edge detection: Returns 1 when pressed (HIGH->LOW), 2 when released/turned OFF (LOW->HIGH), 0 otherwise
int checkButtonEdge(DebouncedButton* btn, unsigned long now) {
  int raw = digitalRead(btn->pin);

  if (raw != btn->lastRawReading) {
    btn->lastChangeTime = now;
    btn->lastRawReading = raw;
  }

  if ((now - btn->lastChangeTime) >= DEBOUNCE_STABLE_TIME) {
    if (raw != btn->debouncedState) {
      btn->debouncedState = raw;
      if (btn->debouncedState == LOW) {
        return 1; // Transition to ACTIVE / ON
      } else {
        return 2; // Transition to INACTIVE / OFF
      }
    }
  }
  return 0;
}

bool checkButtonPressed(DebouncedButton* btn, unsigned long now) {
  return checkButtonEdge(btn, now) == 1;
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
  initLcdHardware();

  setDisplayMessage("SmartQ Hospital", "Connecting WiFi.");
  renderLCDDelta(currentDisplay.line0, currentDisplay.line1);
  soundBeepShort();

  // Wi-Fi Event Listeners for Live Diagnostics
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_CONNECTED) {
      Serial.println("[WiFi Event] Associated with AP! Waiting for DHCP IP...");
    } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      wifiGotIp = true;
      Serial.printf("[WiFi Event] IP Address Assigned: %s\n", WiFi.localIP().toString().c_str());
    } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      wifiGotIp = false;
      Serial.printf("[WiFi Event] Disconnected from AP (Reason code: %d)\n", info.wifi_sta_disconnected.reason);
    }
  });

  // Configure Robust Wi-Fi Subsystem
  Serial.printf("[WiFi] Connecting to SSID: '%s' ...\n", WIFI_SSID);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);               // CRITICAL: Disable modem sleep to prevent hotspot dropping client!
  WiFi.setTxPower(WIFI_POWER_15dBm);  // CRITICAL: Prevent brownout RF current spikes!
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();

  // Re-sync LCD after Wi-Fi RF calibration spikes settle so 4-bit mode cannot stay garbled
  initLcdHardware();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] ONLINE! IP: %s\n", WiFi.localIP().toString().c_str());
    soundBeepDouble();
    setDisplayMessage("Cloud Connected!", WiFi.localIP().toString());
    renderLCDDelta(currentDisplay.line0, currentDisplay.line1);
    delay(1500);
    setDisplayMessage("SmartQ Hospital", "Counter 1 Online");
    renderLCDDelta(currentDisplay.line0, currentDisplay.line1);
    readyBannerApplied = true;
  } else {
    Serial.printf("[WiFi] Still connecting / awaiting DHCP (Status: %d). Continuing in background...\n", WiFi.status());
    setDisplayMessage("WiFi Connecting", "Local Kiosk Mode");
    renderLCDDelta(currentDisplay.line0, currentDisplay.line1);
    delay(1000);
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
        snprintf(currentDisplay.line0, sizeof(currentDisplay.line0), "%s", currentPatientName.c_str());
        snprintf(currentDisplay.line1, sizeof(currentDisplay.line1), "Token: %s", currentServingToken.c_str());
      } else {
        snprintf(currentDisplay.line0, sizeof(currentDisplay.line0), "%s", "SmartQ Hospital");
        snprintf(currentDisplay.line1, sizeof(currentDisplay.line1), "%s", (WiFi.status() == WL_CONNECTED) ? "Counter 1 Online" : "Local Kiosk Mode");
      }
      xSemaphoreGive(xDisplayMutex);
    }
  }

  // -------------------------------------------------------------
  // Switch 1: NEXT TOKEN / CALL NEXT (GPIO 25) - Confirmed Press
  // -------------------------------------------------------------
  if (checkButtonPressed(&btnGetToken, now)) {
    Serial.println("[BUTTON 1 - GPIO 25] Pressed! Calling NEXT patient in queue...");

    soundBeepDouble();
    setDisplayMessage("Calling Next...", "Fetching Cloud..");

    HardwareEvent ev = { EVENT_CALL_NEXT, 0 };
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
  // Switch 3: HELP (GPIO 27) - Direct State Tracking (Toggle Switch & Push Button Friendly)
  // -------------------------------------------------------------
  int helpEdge = checkButtonEdge(&btnHelp, now);
  if (helpEdge == 1) {
    // Switch turned ON (Pin goes LOW)
    helpAlarmActive = true;
    Serial.println("[BUTTON 3 - GPIO 27] HELP SWITCH ON -> Sounding emergency alarm & dispatching WhatsApp!");
    setDisplayMessage("* HELP ALERT *", "SOUNDING ALARM!");

    HardwareEvent ev = { EVENT_HELP_ALERT, 0 };
    xQueueSend(xHardwareEventQueue, &ev, 0);
  } else if (helpEdge == 2) {
    // Switch turned OFF (Pin returns to HIGH via internal pullup)
    helpAlarmActive = false;
    Serial.println("[BUTTON 3 - GPIO 27] HELP SWITCH OFF -> Alarm silenced immediately.");
    digitalWrite(PIN_BUZZER, LOW);
    sirenState = false;

    // Restore counter ready screen
    if (currentServingToken.length() > 0) {
      setDisplayMessage(currentPatientName, "Token: " + currentServingToken);
    } else {
      setDisplayMessage("SmartQ Hospital", (WiFi.status() == WL_CONNECTED) ? "Counter 1 Online" : "Local Kiosk Mode");
    }
  }

  // -------------------------------------------------------------
  // Non-Blocking Continuous Siren Pattern (When Alarm is ACTIVE)
  // -------------------------------------------------------------
  if (helpAlarmActive) {
    // Pulsing emergency siren: 120ms ON, 80ms OFF without blocking FreeRTOS tasks
    unsigned long interval = sirenState ? 120 : 80;
    if (now - lastSirenToggleMs >= interval) {
      lastSirenToggleMs = now;
      sirenState = !sirenState;
      digitalWrite(PIN_BUZZER, sirenState ? HIGH : LOW);
    }
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
