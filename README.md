# SmartQ – Smart Queue Management & Automated Token Calling System Using ESP32

**Subject:** Principles of Digital Systems and Design (PDSD)  
**Project Type:** Hardware + Software Prototype  
**Languages:** English, Telugu (తెలుగు), and Tamil (தமிழ்)  
**Controller:** ESP32 DevKit V1 (ESP32-WROOM-32)  
**Backend:** Python 3 (Flask) | **Databases:** SQLite 3 (Local) + Supabase PostgreSQL (Cloud)  
**Frontend:** HTML5, CSS3, JavaScript (Web Speech API, Audio Synthesis)  
**WhatsApp Gateway:** Local Automated Microservice (:3005) + Zero-friction Direct Dispatch  

---

## 1. Project Overview & Architecture

SmartQ is an inclusive, accessible queue management and automated token calling prototype engineered for clinics, diagnostic centers, hospitals, banks, and academic administrative offices. It seamlessly interconnects physical hardware (ESP32 kiosk with 16×2 I2C LCD, buttons, buzzer), a local automated WhatsApp messaging engine, a Supabase cloud database, and a rich multilingual staff dashboard.

```
       +-------------------------------------------------------------+
       |                  SmartQ Physical Kiosk                      |
       |     [ESP32 DevKit V1] + [16x2 I2C LCD] + [Voice Kiosk]     |
       +------------------------------+------------------------------+
                                      | HTTP REST / Wi-Fi
                                      v
       +-------------------------------------------------------------+
       |             SmartQ Flask Server & Orchestrator              |
       |  - Multilingual TTS (EN, TE, TA)                            |
       |  - Priority-First FIFO Engine                               |
       |  - 5-Ahead Proactive WhatsApp Alert Broadcast Engine        |
       +--------------+-------------------------------+--------------+
                      |                               |
       +--------------v---------------+ +-------------v---------------+
       |    Local & Cloud Storage     | | WhatsApp Gateway Engine     |
       |  - SQLite 3 (Local DB)       | |  - Microservice (:3005)     |
       |  - Supabase Cloud PostgreSQL | |  - Automated Outbox Service |
       +------------------------------+ +-------------+---------------+
                                                      |
                                                      v
                                        [Patient's WhatsApp Mobile]
                                         - Token Slip & Tracking QR
                                         - 5-Ahead Early Turn Notice
                                         - Digital Medical Prescription
```

### Key Capabilities:
- **Hospital Waiting Hall Public TV Display (`/display`):**
  - High-contrast, airport/hospital-style TV wall monitor interface for waiting halls.
  - Multi-Counter split status (Counter 1: General Medicine, Counter 2: Emergency / Priority, Counter 3: Pharmacy, Counter 4: Diagnostics).
  - Web Audio API dual-tone chime (`Ding-Dong`) synthesized before trilingual spoken announcements.
  - Live waiting ticker with dynamic Estimated Wait Times and large mobile scan-to-track QR code.
- **Inter-Department Counter Routing & Patient Transfer (`/api/queue/transfer`):**
  - Counter staff can 1-click forward consulting patients to Pharmacy (Counter 3) or Diagnostics (Counter 4).
  - Automatically updates patient's queue routing and dispatches an automated WhatsApp transfer receipt.
- **Dynamic AI Estimated Wait Time (EWT) Engine:**
  - Calculates real-time consultation duration moving averages.
  - Informs each waiting patient of their dynamic wait time (e.g. `~6 mins`) on tracking passes, WhatsApp 5-ahead alerts, and TV display.
- **Interactive WhatsApp Bot Inbound Commands:**
  - Patients can text the WhatsApp bot: `STATUS` (live position check), `RX` (prescription details), `CANCEL` (cancellation).
- **Trilingual Inclusivity (English, Telugu, Tamil):**
  - Spoken token announcements and kiosk voice recognition in **English**, **Telugu (తెలుగు)**, and **Tamil (தமிழ்)**.
  - WhatsApp messages, ticket receipts, and registration screens in all 3 languages.
- **Physical Voice Kiosk:**
  - Designed for illiterate, elderly, and rural patients. Prompts patient by voice, recognizes spoken name and 10-digit mobile number, and confirms on LCD.
- **Automated WhatsApp Notification Suite (Port 3005):**
  - **100% Background Automation:** Dispatches messages through the connected local WhatsApp microservice without opening annoying manual browser tabs.
  - **Instant Booking Confirmation:** Delivered upon token generation with live tracking link.
  - **5-Ahead Proactive Broadcast:** When Counter calls or completes a token (e.g. serving #A016), background engine automatically broadcasts alerts to the next 5 consecutive waiting tokens (tokens A018, A019, A024, A020, A021) with their exact queue distance (*"1 ahead - NEXT IN LINE!"*, *"2 ahead"*...) and estimated wait times.
  - **Turn Calling Alert:** Urgent notification with counter designation when called.
  - **Digital Prescription Delivery:** Sends consultation summary and prescription directly to WhatsApp upon service completion.
- **Live Mobile QR Tracking & Sealed Prescriptions (`/track/<token_no>`):**
  - Dynamic 3-node Roadmap: `[SERVING: #A016] ➔ [AHEAD: 3 Patients] ➔ [YOU: #A020]` auto-refreshing in real-time.
  - Automatically locks when consultation is completed, transforming into an official printable **Digital Medical Prescription**.
- **Dual Database Persistence (SQLite + Supabase Cloud):**
  - Real-time bidirectional mirror with Supabase Cloud PostgreSQL for remote dashboards, management reports, and disaster recovery.
- **ESP32 DevKit V1 Hardware Integration:**
  - Non-blocking LCD status polling, repeat call requests, and emergency HELP assistance button.

---

## 2. Hardware Circuit Connections (ESP32 DevKit V1)

| Component | ESP32 Pin | Connection Notes |
| :--- | :--- | :--- |
| **16×2 LCD SDA** | **GPIO 21** | I2C Data line |
| **16×2 LCD SCL** | **GPIO 22** | I2C Clock line |
| **LCD VCC & GND** | **VIN (5V) & GND** | Connect to ESP32 VIN and common Ground |
| **GET TOKEN Button** | **GPIO 25 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **REPEAT Button** | **GPIO 26 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **HELP Button** | **GPIO 27 & GND** | Configured with internal `INPUT_PULLUP`. Pressed = LOW |
| **Active Buzzer (+)**| **GPIO 18** | Driven by GPIO 18 (or via NPN transistor driver) |
| **Active Buzzer (-)**| **Common GND** | Ground connection |

---

## 3. Repository Structure

```
pdsd/
├── README.md                  # Comprehensive project documentation
├── start_smartq.bat           # Root launcher for the entire solution
├── .gitignore                 # Standard Python, secrets, and session ignore rules
└── SmartQ/
    ├── app.py                 # Core Flask server, REST APIs & ESP32 device endpoints
    ├── whatsapp_service.py    # Multilingual WhatsApp message templates (EN, TE, TA)
    ├── whatsapp_web_engine.py # Microservice integration & automated outbox processor
    ├── supabase_service.py    # Supabase Cloud PostgreSQL synchronizer
    ├── supabase_schema.sql    # Cloud relational schema & RLS policies
    ├── seed_sample_data.py    # 28-record realistic clinic patient generator (EN/TE/TA)
    ├── test_smartq.py         # Full automated test suite (15 test cases)
    ├── requirements.txt       # Dependencies (Flask, supabase, requests, qrcode, Pillow)
    ├── .env.example           # Environment template
    ├── smartq.db              # SQLite 3 local database
    ├── esp32/
    │   └── SmartQ_ESP32.ino   # Complete ESP32 Arduino C++ firmware
    ├── templates/
    │   ├── index.html         # Staff counter dashboard (Queue actions & voice call)
    │   ├── register.html      # Multilingual patient mobile web registration
    │   ├── kiosk.html         # Virtual hardware kiosk with voice & LCD
    │   ├── login.html         # WhatsApp scan-to-login & OTP verification
    │   ├── track.html         # Live QR queue roadmap & digital prescription slip
    │   └── ticket.html        # Printable thermal-style token ticket slip
    └── static/
        ├── style.css          # Responsive dark-mode clinical UI styling
        └── app.js             # Web Speech API engine, multilingual TTS, audio effects
```

---

## 4. How to Run the Software

### Step 1: Install Dependencies
```powershell
cd SmartQ
pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy `.env.example` to `.env` and configure your settings:
```powershell
cp .env.example .env
```

### Step 3: Populate Realistic Demo Data
```powershell
python seed_sample_data.py
```
*Generates 28 realistic clinic patient records (15 completed with prescriptions, 1 called at Counter 1, 1 skipped, 11 waiting) in English, Telugu, and Tamil, synced to both SQLite and Supabase Cloud.*

### Step 4: Run the Server
```powershell
python app.py
```

The server will start on:
* **Staff Dashboard:** `http://localhost:5000` (or `http://<LAN_IP>:5000`)
* **Patient Web Registration:** `http://<LAN_IP>:5000/register`
* **Voice Kiosk (Method 1):** `http://<LAN_IP>:5000/kiosk`
* **WhatsApp Login Pass:** `http://<LAN_IP>:5000/login`

---

## 5. Verification and Testing (All 15 Unit Tests)

To verify all 15 modules across database schemas, priority algorithms, multilingual speech, 5-ahead WhatsApp broadcast, and Supabase cloud sync:

```powershell
python test_smartq.py
```

**Test Coverage:**
1. `test_01_database_tables_created` - Database schema & tables verified.
2. `test_02_kiosk_physical_token_creation` - Kiosk button token creation.
3. `test_03_customer_qr_registration_bilingual` - Web registration with English/Telugu/Tamil.
4. `test_04_priority_queue_ordering` - Priority-First FIFO ordering.
5. `test_05_voice_announcements_english_telugu` - Multilingual speech synthesis strings.
6. `test_06_esp32_device_lcd_status_polling` - Real-time ESP32 LCD status endpoint.
7. `test_07_esp32_help_alert_workflow` - Emergency HELP button and staff ACK.
8. `test_08_complete_and_skip_transitions` - Token lifecycle transitions.
9. `test_09_voice_kiosk_interactive_flow` - Voice kiosk conversational registration.
10. `test_10_whatsapp_outbox_and_direct_links` - Automated WhatsApp dispatch & links.
11. `test_11_speech_transcription_and_digit_parsing` - Voice-to-text and phone number parsing.
12. `test_12_proactive_5_ahead_alert_and_completed_prescription_qr` - 5-ahead broadcast & prescription QR lock.
13. `test_13_whatsapp_login_otp_and_handshake_session` - WhatsApp OTP & QR login.
14. `test_14_supabase_connection_and_sync` - Supabase Cloud connection and sync APIs.
15. `test_15_whatsapp_web_engine` - WhatsApp Web sender status, queuing, and alerts.

---

## 6. Viva Voce Key Points & Questions

**Q1. What core engineering problem does SmartQ solve?**  
*A.* Traditional physical queues cause crowding, anxiety, and confusion. Pure mobile apps exclude people without smartphones or literacy. SmartQ bridges physical hardware (ESP32 voice kiosk), multilingual audio announcements, and automated WhatsApp background dispatch so that anyone can participate effortlessly.

**Q2. How is priority handling implemented?**  
*A.* When `priority_first` mode is active, the queue query uses:  
`ORDER BY is_priority DESC, id ASC`  
This guarantees senior citizens, pregnant women, and medical emergencies are served first while preserving strict FIFO order within each tier.

**Q3. How does the 5-ahead proactive WhatsApp alert work?**  
*A.* Upon calling or completing a token, the backend calculates the next 5 eligible tokens in line. It immediately queues and delivers proactive WhatsApp messages to those 5 patients with their queue distance (*"You are 2 ahead in line"*) and estimated wait time, preventing missed appointments.

**Q4. How does the ESP32 communicate with the Flask backend?**  
*A.* The ESP32 connects over local Wi-Fi and issues lightweight HTTP REST GET/POST requests (`/api/device/status`, `/api/device/help`, `/api/device/repeat`). Responses are parsed using `ArduinoJson` in non-blocking loops.

---

## 13. Live Real-Time Product Architecture (Cloud + Local WhatsApp)

SmartQ operates as an end-to-end production prototype combining a globally accessible cloud web app with a zero-cost local WhatsApp microservice:

```
+--------------------------------------------------------------------+
|  1. Public Mobile Web (GitHub Pages)                               |
|     https://kandukurijagan1.github.io/pdsd/                        |
|     - Trilingual Registration Form (English, Telugu, Tamil)        |
|     - Live Mobile QR Queue Tracking & Digital Prescription Pass    |
+---------------------------------+----------------------------------+
                                  |
                                  | 1. Direct REST Insert
                                  v
+--------------------------------------------------------------------+
|  2. Supabase Cloud Database                                        |
|     - Tables: customers, tokens, notification_outbox               |
|     - Status: 'PENDING' WhatsApp Notification Queued               |
+---------------------------------+----------------------------------+
                                  |
                                  | 2. Sub-second Polling/Sync
                                  v
+--------------------------------------------------------------------+
|  3. Local Hospital Machine (SmartQ Realtime Bridge)                |
|     - Python Bridge Daemon (realtime_bridge.py / app.py)           |
|     - Detects 'PENDING' cloud outbox notifications                 |
|     - Syncs online tokens into local SQLite smartq.db              |
+---------------------------------+----------------------------------+
                                  |
                                  | 3. Local HTTP POST (:3005)
                                  v
+--------------------------------------------------------------------+
|  4. Local WhatsApp Microservice (:3005)                            |
|     - Puppeteer Stealth WhatsApp Gateway                           |
|     - Authenticated Sender Session: K.K (+91 8367047947)           |
|     - Instant background message dispatch (zero browser popups)    |
+---------------------------------+----------------------------------+
                                  |
                                  | 4. WhatsApp Cloud Protocol
                                  v
+--------------------------------------------------------------------+
|  5. Patient's WhatsApp Phone                                       |
|     - Instant confirmation ticket with trilingual text             |
|     - Direct live tracking link: track.html?token=...              |
|     - 5-ahead, 4-ahead, 3-ahead proactive queue warnings           |
|     - Digital prescription & medicine instructions upon completion  |
+--------------------------------------------------------------------+
```
