# SmartQ – Smart Queue Management & Automated Token Calling System Using ESP32

**Subject:** Principles of Digital Systems and Design (PDSD)  
**Project Type:** Hardware + Software Prototype  
**Languages:** English and Telugu  
**Controller:** ESP32 DevKit V1 (ESP32-WROOM-32)  
**Backend:** Python 3 (Flask) | **Database:** SQLite 3  
**Frontend:** HTML5, CSS3, JavaScript (Web Speech API)  

---

## 1. Project Overview & Architecture

SmartQ is an inclusive queue management and automated token calling prototype designed for service centers, clinics, banks, and college administrative offices. It bridges physical hardware (ESP32 kiosk with LCD, buttons, and buzzer) and a modern web management application hosted on a local laptop.

### Key Capabilities:
- **Inclusive Token Generation:**
  1. **Physical Kiosk (Voice-Guided Assistant):** Specially engineered for illiterate, uneducated, or elderly patients. Pressing the `GET TOKEN` button prompts the patient by voice (*"Please tell your name"* / *"దయచేసి మీ పేరు చెప్పండి"*). The system listens to their voice, captures their name, asks for their 10-digit mobile number by voice, validates the digits, and generates their token automatically with spoken and LCD confirmation!
  2. **QR Code / Mobile Web:** Contactless registration on [`register.html`](file:///c:/Users/ADMIN/Documents/pdsd/SmartQ/templates/register.html) with mandatory Patient Name and 10-digit Mobile Number. Includes **🎤 Tap-to-Speak** voice input buttons directly inside the form fields so smartphone users don't need to type!
  3. **Staff-Assisted:** Counter staff can create tokens directly through the dashboard with priority flags.
- **Bilingual Voice Announcements:** Spoken token announcements in **English** and **Telugu** via browser speech synthesis (`window.speechSynthesis`), with fallback phonetic support and doorbell chimes.
- **WhatsApp Connectivity (Dual-Mode):**
  1. **Automated Cloud Dispatch:** Integrated with Twilio WhatsApp Cloud API to automatically send booking slips and turn reminders to patients' phone numbers.
  2. **1-Click WhatsApp Click-to-Chat (`wa.me`):** Allows staff and patients to immediately open pre-filled, formatted WhatsApp tickets and call reminders without requiring Twilio API credits.
  3. **Outbox Audit Table:** All WhatsApp messages are logged in SQLite (`notification_outbox`) with delivery status.
- **Priority-First Queue Management:** Configurable queue ordering policy (`Priority-First FIFO` for senior citizens and accessibility needs, or `Standard FIFO`).
- **Real-Time Device Feedback:** ESP32 polls the Flask server to show live counter status (`Now Serving: A001`), handles repeat announcements, and supports a dedicated **HELP / Assistance Alert** button with visual and audio alerts on the staff dashboard.
- **Printable Tickets:** Thermal-receipt styled printable token slip with QR code for live mobile status tracking.

---

## 2. Hardware Circuit Connections (ESP32 DevKit V1)

| Component | ESP32 Pin | Connection Notes |
| :--- | :--- | :--- |
| **16×2 LCD SDA** | **GPIO 21** | I2C Data line (Use 3.3V/5V level shifter if pullups are 5V) |
| **16×2 LCD SCL** | **GPIO 22** | I2C Clock line |
| **LCD VCC & GND** | **VIN (5V) & GND** | Connect to ESP32 VIN and common Ground |
| **GET TOKEN Button** | **GPIO 25 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **REPEAT Button** | **GPIO 26 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **HELP Button** | **GPIO 27 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **Active Buzzer (+)**| **GPIO 18** | Driven by GPIO 18 (or via NPN transistor driver) |
| **Active Buzzer (-)**| **Common GND** | Ground connection |

> **Safety Warning:** ESP32 GPIOs operate at 3.3V logic. Verify whether your I2C LCD backpack pulls SDA/SCL lines to 5V; if so, cut the 5V trace or use a bidirectional I2C logic level shifter.

---

## 3. Software Structure

```
SmartQ/
├── app.py                   # Flask server, SQLite models, REST API & device endpoints
├── requirements.txt         # Python dependencies (Flask, CORS, qrcode, Pillow, etc.)
├── .env                     # Configuration (Host, Port, Counter Name, Priority Mode)
├── smartq.db                # SQLite database (auto-created on startup)
├── start_server.bat         # One-click Windows startup script
├── test_smartq.py           # Automated test suite (9 test cases for all 5 modules)
├── templates/
│   ├── index.html           # Staff counter dashboard (Queue actions & voice call)
│   ├── register.html        # Customer mobile registration (English & Telugu)
│   └── ticket.html          # Printable thermal-style token ticket slip
├── static/
│   ├── style.css            # Responsive UI styles and print media rules
│   └── app.js               # Web Speech API engine, queue polling, sound effects
└── esp32/
    └── SmartQ_ESP32.ino     # Complete ESP32 Arduino C++ firmware
```

---

## 4. How to Run the Software

### Step 1: Start the Python Backend
Double-click `start_server.bat` inside the `SmartQ` folder, or run via PowerShell:

```powershell
cd c:\Users\ADMIN\Documents\pdsd\SmartQ
.\venv\Scripts\python.exe app.py
```

The console will display:
```
=================================================================
 SmartQ - Smart Queue Management & Automated Token Calling
 Principles of Digital Systems and Design (PDSD) Prototype
=================================================================
 * Staff Dashboard:   http://localhost:5000  or  http://192.168.x.x:5000
 * Customer Register: http://192.168.x.x:5000/register
 * ESP32 Server URL:  http://192.168.x.x:5000
=================================================================
```

### Step 2: Access the Interfaces
- **Staff Dashboard:** Open `http://localhost:5000` in Google Chrome or Microsoft Edge.
- **Customer Mobile Registration:** Scan the on-screen QR code from any phone connected to the same Wi-Fi, or browse to `http://<YOUR_LAN_IP>:5000/register`.
- **Printable Slip:** Automatically opens on token generation, or navigate to `http://localhost:5000/ticket/A001`.

---

## 5. How to Program the ESP32

1. Open **Arduino IDE**.
2. Go to **File -> Open** and select `SmartQ/esp32/SmartQ_ESP32.ino`.
3. Install required libraries via **Tools -> Manage Libraries...**:
   - `LiquidCrystal_I2C` by Frank de Brabander (or Marco Schwartz)
   - `ArduinoJson` by Benoit Blanchon (Version 6 or 7)
4. Update the Wi-Fi and Laptop IP settings at the top of the sketch:
   ```cpp
   const char* WIFI_SSID     = "Your_WiFi_Name";
   const char* WIFI_PASSWORD = "Your_WiFi_Password";
   const char* SERVER_HOST   = "192.168.1.100"; // Your laptop's LAN IP
   const int   SERVER_PORT   = 5000;
   ```
5. Select your board: **Tools -> Board -> ESP32 Arduino -> DOIT ESP32 DEVKIT V1**.
6. Select your COM port under **Tools -> Port**.
7. Click **Upload**.

---

## 6. Verification and Testing (All 9 Unit Tests)

To verify the complete backend, database, queue policies, and endpoints, run the included test suite:

```powershell
cd c:\Users\ADMIN\Documents\pdsd\SmartQ
.\venv\Scripts\python.exe test_smartq.py
```

**Test Results:**
- `test_01_database_tables_created` : Verifies `customers`, `tokens`, `settings`, `events`, `notification_outbox`.
- `test_02_kiosk_physical_token_creation` : Verifies physical button endpoint generates sequential tokens.
- `test_03_customer_qr_registration_bilingual` : Verifies contactless web registration in English & Telugu.
- `test_04_priority_queue_ordering` : Verifies priority tokens are served before standard tokens in FIFO order.
- `test_05_voice_announcements_english_telugu` : Verifies English and Telugu voice synthesis strings.
- `test_06_esp32_device_lcd_status_polling` : Verifies real-time LCD polling status.
- `test_07_esp32_help_alert_workflow` : Verifies emergency HELP button and staff acknowledgment.
- `test_08_complete_and_skip_transitions` : Verifies full token lifecycle (`WAITING` -> `CALLED` -> `COMPLETED`/`SKIPPED`).
- `test_09_qr_code_and_ticket_page` : Verifies dynamic QR code generation and printable ticket slip.

---

## 7. Viva Voce Questions & Answers

**Q1. What is the core problem SmartQ solves?**  
*A.* Manual queue systems cause overcrowding, confusion, and missed turns due to verbal-only calling. Smartphone-only apps exclude people without smartphones or digital literacy. SmartQ bridges physical kiosks, QR registration, and multilingual voice calling to be 100% inclusive.

**Q2. Why is ESP32 chosen instead of Arduino Uno?**  
*A.* ESP32 features integrated 2.4 GHz Wi-Fi and Bluetooth, a dual-core 32-bit Tensilica processor at 240 MHz, ample GPIOs, and sufficient RAM to process HTTP REST requests and JSON payloads without extra shields.

**Q3. How is priority handling implemented?**  
*A.* SmartQ maintains a priority flag (`is_priority`). When `priority_first` mode is active, the database query executes:  
`ORDER BY is_priority DESC, id ASC`  
This guarantees eligible priority customers (senior citizens, persons with disabilities, medical emergencies) are served first, while maintaining strict FIFO order within each category.

**Q4. How do bilingual announcements work?**  
*A.* The web dashboard uses the HTML5 **Web Speech API** (`window.speechSynthesis`). When a token is called, the server supplies announcement text in both English and Telugu. If a native Telugu voice (`te-IN`) is installed in Windows/Chrome, it speaks Telugu Unicode natively; otherwise, it uses phonetic transliteration with an Indian English voice.

**Q5. How does the ESP32 LCD stay synchronized with staff actions?**  
*A.* The ESP32 runs a non-blocking background task using `millis()`. Every 3 seconds, it sends an HTTP GET request to `/api/device/status` to receive the currently serving token number, waiting count, and help alerts.
