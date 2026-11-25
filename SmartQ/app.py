"""
SmartQ - Smart Queue Management and Automated Token Calling System
Backend Server (Flask + SQLite)
Subject: Principles of Digital Systems and Design (PDSD)
"""

import os
import io
import re
import socket
import sqlite3
import base64
import wave
import urllib.parse
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, abort
from flask_cors import CORS
import qrcode
from dotenv import load_dotenv

try:
    import speech_recognition as sr
except ImportError:
    sr = None

from whatsapp_service import (
    send_whatsapp_notification,
    format_token_created_message,
    format_token_called_message,
    format_token_upcoming_message,
    format_token_completed_message,
    build_whatsapp_direct_link,
    generate_and_send_whatsapp_otp,
    verify_whatsapp_login_otp,
    create_qr_whatsapp_login_session,
    check_qr_whatsapp_login_session,
    ACTIVE_QR_SESSIONS
)

from supabase_service import (
    check_supabase_connection,
    sync_customer_to_supabase,
    sync_token_to_supabase,
    sync_event_to_supabase,
    sync_outbox_to_supabase,
    sync_full_database_to_supabase
)

# Load environment configuration
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'smartq-secret-key-pdsd-2026')
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, os.getenv('DATABASE_PATH', 'smartq.db'))
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', 5000))
COUNTER_NAME = os.getenv('COUNTER_NAME', 'Counter 1')
ORGANIZATION_NAME = os.getenv('ORGANIZATION_NAME', 'SmartQ Service Center')
BASE_WEBSITE_URL = os.getenv('BASE_WEBSITE_URL', 'https://kandukurijagan1.github.io/pdsd').rstrip('/')

# ---------------------------------------------------------
# Database Utilities
# ---------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initialize database tables according to PDSD SmartQ specification."""
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Customers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT,
                email TEXT,
                preferred_language TEXT DEFAULT 'en',
                priority_reason TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # 2. Tokens Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_no TEXT NOT NULL,
                customer_id INTEGER,
                status TEXT NOT NULL DEFAULT 'WAITING',
                is_priority INTEGER DEFAULT 0,
                source TEXT NOT NULL,
                counter TEXT DEFAULT 'Counter 1',
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                called_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            )
        """)

        # 3. Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 4. Events Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER,
                event_type TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                message TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # 5. Notification Outbox (Reserved for WhatsApp/SMS extension)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_id INTEGER,
                channel TEXT,
                event_type TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        """)

        # Default Settings
        defaults = {
            'next_token_seq': '1',
            'token_prefix': 'A',
            'counter_name': COUNTER_NAME,
            'organization_name': ORGANIZATION_NAME,
            'priority_mode': os.getenv('PRIORITY_MODE', 'priority_first'),
            'help_alert_active': '0',
            'help_alert_time': '',
            'help_alert_source': '',
            'voice_session_state': 'IDLE',
            'voice_session_patient_name': '',
            'voice_session_token_no': '',
            'voice_session_updated': ''
        }

        for k, v in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        # Schema migrations for Real-Time WhatsApp Alerts, QR Tracking & Digital Prescription
        cursor.execute("PRAGMA table_info(tokens)")
        token_cols = [c[1] for c in cursor.fetchall()]
        if 'alert_5_ahead_sent' not in token_cols:
            cursor.execute("ALTER TABLE tokens ADD COLUMN alert_5_ahead_sent INTEGER DEFAULT 0")
        if 'diagnosis' not in token_cols:
            cursor.execute("ALTER TABLE tokens ADD COLUMN diagnosis TEXT")
        if 'prescription_json' not in token_cols:
            cursor.execute("ALTER TABLE tokens ADD COLUMN prescription_json TEXT")
        if 'doctor_name' not in token_cols:
            cursor.execute("ALTER TABLE tokens ADD COLUMN doctor_name TEXT DEFAULT 'Dr. K. Sharma (Consultant Physician)'")
        if 'doctor_notes' not in token_cols:
            cursor.execute("ALTER TABLE tokens ADD COLUMN doctor_notes TEXT")

        cursor.execute("PRAGMA table_info(notification_outbox)")
        outbox_cols = [c[1] for c in cursor.fetchall()]
        if 'phone' not in outbox_cols:
            cursor.execute("ALTER TABLE notification_outbox ADD COLUMN phone TEXT")
        if 'message_text' not in outbox_cols:
            cursor.execute("ALTER TABLE notification_outbox ADD COLUMN message_text TEXT")

        conn.commit()

def get_setting(key, default=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row['value'] if row else default

def set_setting(key, value):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def get_lan_ip():
    """Detect LAN IP address so ESP32 and phones on the same Wi-Fi can connect."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connecting to a public IP doesn't actually send traffic, but resolves the local interface IP
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# ---------------------------------------------------------
# Token & Queue Operations
# ---------------------------------------------------------

def generate_next_token_number():
    """Thread-safe sequential token generator (e.g. A001, A002)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("SELECT value FROM settings WHERE key = 'next_token_seq'")
        seq_row = cur.fetchone()
        seq = int(seq_row['value']) if seq_row else 1

        cur.execute("SELECT value FROM settings WHERE key = 'token_prefix'")
        pref_row = cur.fetchone()
        prefix = pref_row['value'] if pref_row else 'A'

        token_no = f"{prefix}{seq:03d}"

        # Increment sequence
        cur.execute("UPDATE settings SET value = ? WHERE key = 'next_token_seq'", (str(seq + 1),))
        conn.commit()
        return token_no

def create_token_record(name=None, phone=None, email=None, language='en', is_priority=False, priority_reason=None, source='kiosk'):
    """Create customer (if details provided) and generate token."""
    token_no = generate_next_token_number()
    is_p = 1 if is_priority else 0
    language = language if language in ['en', 'te', 'ta'] else 'en'

    with get_db() as conn:
        cur = conn.cursor()

        # Insert customer record
        customer_id = None
        if name or phone or email or priority_reason:
            cur.execute("""
                INSERT INTO customers (name, phone, email, preferred_language, priority_reason)
                VALUES (?, ?, ?, ?, ?)
            """, (name or 'Walk-in Customer', phone or '', email or '', language, priority_reason or ''))
            customer_id = cur.lastrowid

        # Insert token record
        cur.execute("""
            INSERT INTO tokens (token_no, customer_id, status, is_priority, source, counter)
            VALUES (?, ?, 'WAITING', ?, ?, ?)
        """, (token_no, customer_id, is_p, source, get_setting('counter_name', 'Counter 1')))
        token_id = cur.lastrowid

        # Calculate position in waiting queue
        priority_mode = get_setting('priority_mode', 'priority_first')
        if priority_mode == 'priority_first':
            if is_p:
                cur.execute("SELECT COUNT(*) AS pos FROM tokens WHERE status = 'WAITING' AND is_priority = 1 AND id <= ?", (token_id,))
            else:
                cur.execute("""
                    SELECT (
                        (SELECT COUNT(*) FROM tokens WHERE status = 'WAITING' AND is_priority = 1) +
                        (SELECT COUNT(*) FROM tokens WHERE status = 'WAITING' AND is_priority = 0 AND id <= ?)
                    ) AS pos
                """, (token_id,))
        else:
            cur.execute("SELECT COUNT(*) AS pos FROM tokens WHERE status = 'WAITING' AND id <= ?", (token_id,))
        
        pos_row = cur.fetchone()
        position = pos_row['pos'] if pos_row else 1

        # Dispatch WhatsApp Notification
        whatsapp_link = None
        tracking_url = f"{BASE_WEBSITE_URL}/track.html?token={token_no}"
        if phone:
            org_name = get_setting('organization_name', 'SmartQ Service Center')
            counter_name = get_setting('counter_name', 'Counter 1')
            wa_text = format_token_created_message(
                token_no=token_no,
                patient_name=name or 'Patient',
                position=position,
                counter=counter_name,
                est_wait=position * 3,
                tracking_url=tracking_url,
                org_name=org_name,
                language=language
            )
            send_whatsapp_notification(conn, token_id, phone, wa_text, 'TOKEN_CREATED')
            whatsapp_link = build_whatsapp_direct_link(phone, wa_text)

        # Log event
        msg = f"Token {token_no} created via {source}" + (" (PRIORITY)" if is_p else "")
        cur.execute("""
            INSERT INTO events (token_id, event_type, language, message)
            VALUES (?, 'TOKEN_CREATED', ?, ?)
        """, (token_id, language, msg))

        conn.commit()

        # Cloud Mirror to Supabase
        sync_customer_to_supabase(customer_id, name, phone, lang=language)
        sync_token_to_supabase({
            'id': token_id,
            'token_no': token_no,
            'customer_id': customer_id,
            'status': 'WAITING',
            'is_priority': is_p,
            'source': source,
            'counter': get_setting('counter_name', 'Counter 1')
        })
        sync_event_to_supabase(token_id, 'TOKEN_CREATED', language, msg)

        return {
            'id': token_id,
            'token_no': token_no,
            'position': position,
            'is_priority': bool(is_p),
            'source': source,
            'language': language,
            'phone': phone,
            'whatsapp_link': whatsapp_link
        }

def get_announcement_texts(token_no, counter_name):
    """Generate announcement text for English, Telugu and Tamil."""
    # Split token for speech clarity: e.g. "A 0 0 1" or "A 1"
    token_speech = " ".join(list(token_no))

    english_text = f"Token number {token_speech}, please proceed to {counter_name}."
    telugu_text = f"టోకెన్ సంఖ్య {token_speech}, దయచేసి {counter_name} వద్దకు రండి."
    tamil_text = f"டோக்கன் எண் {token_speech}, தயவுசெய்து {counter_name}-க்கு வரவும்."
    
    return {
        'en': english_text,
        'te': telugu_text,
        'ta': tamil_text
    }

# ---------------------------------------------------------
# Web Page Routes
# ---------------------------------------------------------

@app.route('/')
def index():
    """Staff Dashboard."""
    lan_ip = get_lan_ip()
    return render_template('index.html', lan_ip=lan_ip, port=PORT, counter_name=get_setting('counter_name', 'Counter 1'))

@app.route('/kiosk')
def virtual_kiosk():
    """Virtual ESP32 Kiosk Hardware Simulator."""
    return render_template('kiosk.html')

@app.route('/register')
def register():
    """Customer QR/Mobile Registration."""
    return render_template('register.html')

@app.route('/display')
def public_tv_display():
    """Hospital Waiting Hall Public TV Display (Widescreen Wall Screen)."""
    lan_ip = get_lan_ip()
    return render_template('display.html', lan_ip=lan_ip, port=PORT, org_name=get_setting('organization_name', 'SmartQ Service Center'))

@app.route('/ticket/<token_no>')
def ticket(token_no):
    """Printable Token Ticket with direct QR track link."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.name, c.preferred_language, c.priority_reason
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.token_no = ?
        """, (token_no,))
        row = cur.fetchone()
        if not row:
            abort(404, description="Token not found")
        
        # Calculate waiting ahead
        cur.execute("""
            SELECT COUNT(*) AS ahead FROM tokens 
            WHERE status = 'WAITING' AND id < ?
        """, (row['id'],))
        ahead = cur.fetchone()['ahead']

        return render_template(
            'ticket.html',
            token=dict(row),
            ahead=ahead,
            org_name=get_setting('organization_name', 'SmartQ Service Center'),
            counter=get_setting('counter_name', 'Counter 1')
        )

@app.route('/track/<token_no>')
def track_token_page(token_no):
    """
    Dedicated live mobile tracking portal.
    If WAITING or CALLED: Displays real-time live queue progression.
    If COMPLETED: Deactivates active queue and displays Official Digital Consultation & Prescription Slip!
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.name, c.phone, c.preferred_language, c.priority_reason
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.token_no = ?
        """, (token_no,))
        row = cur.fetchone()
        if not row:
            abort(404, description="Token not found")

        token_data = dict(row)

        ahead = 0
        if token_data['status'] == 'WAITING':
            cur.execute("""
                SELECT COUNT(*) as count FROM tokens 
                WHERE status = 'WAITING' AND id < ?
            """, (token_data['id'],))
            ahead = cur.fetchone()['count']

        cur.execute("""
            SELECT token_no, counter, is_priority 
            FROM tokens 
            WHERE status = 'CALLED' 
            ORDER BY called_at DESC LIMIT 1
        """)
        called_row = cur.fetchone()
        serving_token = dict(called_row) if called_row else None

        import json
        prescription_list = []
        if token_data.get('prescription_json'):
            try:
                prescription_list = json.loads(token_data['prescription_json'])
            except Exception:
                prescription_list = []

        lan_ip = get_lan_ip()
        return render_template(
            'track.html',
            token=token_data,
            ahead=ahead,
            serving=serving_token,
            prescription=prescription_list,
            org_name=get_setting('organization_name', 'SmartQ Service Center'),
            counter=get_setting('counter_name', 'Counter 1'),
            lan_ip=lan_ip,
            port=PORT
        )

@app.route('/api/qr/token/<token_no>')
def api_token_qr(token_no):
    """Generate QR code PNG pointing directly to /track/<token_no>."""
    track_url = f"{BASE_WEBSITE_URL}/track.html?token={token_no}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(track_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/whatsapp')
def whatsapp_hub_page():
    """Local Free WhatsApp Automation Hub."""
    lan_ip = get_lan_ip()
    return render_template('whatsapp.html', lan_ip=lan_ip, port=PORT, org_name=get_setting('organization_name', 'SmartQ Service Center'))

@app.route('/login')
@app.route('/scan-login')
def mobile_login_page():
    """Customer entrance QR scan & quick login page."""
    lan_ip = get_lan_ip()
    return render_template('login.html', lan_ip=lan_ip, port=PORT, org_name=get_setting('organization_name', 'SmartQ Service Center'))

@app.route('/qr-entrance')
def qr_entrance_image():
    """Generate QR code pointing to entrance login & registration."""
    login_url = f"{BASE_WEBSITE_URL}/login.html"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(login_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/qr')
def qr_image():
    """Generate and return QR code PNG pointing to /register on GitHub base website."""
    reg_url = f"{BASE_WEBSITE_URL}/register.html"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(reg_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/qr-info')
def qr_info():
    """Return registration URL and Base64 QR code for dashboard embedding."""
    reg_url = f"{BASE_WEBSITE_URL}/register.html"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=1,
    )
    qr.add_data(reg_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e293b", back_color="#ffffff")
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    b64_qr = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return jsonify({
        'url': reg_url,
        'lan_ip': lan_ip,
        'port': PORT,
        'qr_base64': f"data:image/png;base64,{b64_qr}"
    })

def clean_phone_number(raw_phone):
    """Extract digits and validate 10-digit mobile number."""
    if not raw_phone:
        return ""
    digits = re.sub(r'\D', '', str(raw_phone))
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits

# ---------------------------------------------------------
# WhatsApp Login & Authentication APIs
# ---------------------------------------------------------

@app.route('/api/auth/whatsapp/send-otp', methods=['POST'])
def api_whatsapp_send_otp():
    """Generate and dispatch WhatsApp Login OTP to customer's phone number."""
    data = request.get_json(silent=True) or {}
    raw_phone = data.get('phone', '').strip()
    name = data.get('name', 'Patient').strip()

    phone = clean_phone_number(raw_phone)
    if len(phone) != 10:
        return jsonify({'success': False, 'message': 'Please provide a valid 10-digit mobile number'}), 400

    org_name = get_setting('organization_name', 'SmartQ Service Center')
    with get_db() as conn:
        res = generate_and_send_whatsapp_otp(conn, phone, name=name, org_name=org_name)

    if res['success']:
        return jsonify({
            'success': True,
            'message': f"OTP successfully dispatched via WhatsApp to +91{phone}",
            'phone': phone,
            'otp': res.get('otp'),
            'direct_link': res.get('direct_link')
        }), 200
    else:
        return jsonify({'success': False, 'message': res.get('message', 'Failed to send OTP')}), 400

@app.route('/api/auth/whatsapp/verify-otp', methods=['POST'])
def api_whatsapp_verify_otp():
    """Verify WhatsApp OTP and automatically log in & generate token."""
    data = request.get_json(silent=True) or {}
    raw_phone = data.get('phone', '').strip()
    entered_otp = data.get('otp', '').strip()
    name = data.get('name', '').strip()
    language = data.get('preferred_language', 'en')
    is_priority = bool(data.get('is_priority', False))

    phone = clean_phone_number(raw_phone)
    if len(phone) != 10:
        return jsonify({'success': False, 'message': 'Valid 10-digit phone number is required'}), 400
    if not entered_otp:
        return jsonify({'success': False, 'message': 'Please enter the 6-digit WhatsApp OTP'}), 400

    # Verify OTP
    verification = verify_whatsapp_login_otp(phone, entered_otp)
    if not verification['valid']:
        return jsonify({'success': False, 'message': verification.get('message', 'Invalid OTP')}), 401

    patient_name = name or verification.get('name') or 'WhatsApp Patient'

    # Check if patient already has an active WAITING or CALLED token
    with get_db() as conn:
        active = conn.execute('''
            SELECT * FROM tokens
            WHERE customer_id IN (SELECT id FROM customers WHERE phone = ?)
              AND status IN ('WAITING', 'CALLED')
            ORDER BY id DESC LIMIT 1
        ''', (phone,)).fetchone()
        if active:
            act_dict = dict(active)
            return jsonify({
                'success': True,
                'already_active': True,
                'message': f"Welcome back {patient_name}! You already have an active Token #{act_dict['token_no']}.",
                'token_no': act_dict['token_no'],
                'patient_name': patient_name,
                'phone': phone,
                'redirect_url': f"/track/{act_dict['token_no']}"
            }), 200

    # Create Token record & dispatch automated WhatsApp welcome
    result = create_token_record(
        name=patient_name,
        phone=phone,
        language=language,
        is_priority=is_priority,
        priority_reason='WhatsApp Login Verified',
        source='whatsapp-login'
    )

    return jsonify({
        'success': True,
        'message': 'WhatsApp Login Verified Successfully!',
        'token_no': result['token_no'],
        'position': result['position'],
        'patient_name': patient_name,
        'phone': phone,
        'redirect_url': f"/track/{result['token_no']}",
        'whatsapp_link': result.get('whatsapp_link')
    }), 200

@app.route('/api/auth/whatsapp/qr-session', methods=['POST'])
def api_whatsapp_qr_session():
    """Create a unique session for scan-to-login via WhatsApp handshake."""
    bot_phone = os.getenv('WHATSAPP_BOT_NUMBER', '14155238886').strip()
    session_data = create_qr_whatsapp_login_session(bot_phone)
    session_id = session_data['session_id']
    return jsonify({
        'success': True,
        'session_id': session_id,
        'whatsapp_url': session_data['whatsapp_url'],
        'qr_image_url': f"/api/auth/whatsapp/qr-image/{session_id}"
    })

@app.route('/api/auth/whatsapp/qr-image/<session_id>')
def api_whatsapp_qr_image(session_id):
    """Return QR code PNG that opens WhatsApp with handshake message."""
    bot_phone = os.getenv('WHATSAPP_BOT_NUMBER', '14155238886').strip()
    prefill_text = urllib.parse.quote(f"LOGIN SMARTQ {session_id}")
    wa_url = f"https://wa.me/{bot_phone}?text={prefill_text}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(wa_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#25D366", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/auth/whatsapp/check-session/<session_id>', methods=['GET'])
def api_whatsapp_check_session(session_id):
    """Check if QR login session has completed authentication."""
    res = check_qr_whatsapp_login_session(session_id)
    return jsonify(res)

@app.route('/api/whatsapp/webhook', methods=['POST', 'GET'])
def api_whatsapp_webhook():
    """
    Inbound WhatsApp Webhook (for Twilio, UltraMsg, GreenAPI, Evolution API).
    Receives incoming WhatsApp messages from customers.
    Automatically logs in, generates token, and replies via WhatsApp!
    """
    from_phone = ""
    incoming_text = ""

    # Check for Twilio format (form-encoded)
    if request.form:
        raw_from = request.form.get('From', '')
        from_phone = clean_phone_number(raw_from.replace('whatsapp:', ''))
        incoming_text = request.form.get('Body', '').strip()
    elif request.is_json:
        data = request.get_json(silent=True) or {}
        raw_from = data.get('from', '') or data.get('phone', '')
        from_phone = clean_phone_number(raw_from)
        incoming_text = data.get('message', '') or data.get('text', '')

    if not from_phone:
        return jsonify({'status': 'ignored', 'reason': 'No sender phone'}), 200

    incoming_upper = incoming_text.upper()

    # 1. Check if this is a QR Session handshake: "LOGIN SMARTQ AUTH-XXXX"
    if "LOGIN SMARTQ" in incoming_upper:
        parts = incoming_upper.split()
        for p in parts:
            if p.startswith("AUTH-"):
                session_id = p
                if session_id in ACTIVE_QR_SESSIONS:
                    result = create_token_record(
                        name="WhatsApp Customer",
                        phone=from_phone,
                        source='whatsapp-qr-scan'
                    )
                    ACTIVE_QR_SESSIONS[session_id]['status'] = 'LOGGED_IN'
                    ACTIVE_QR_SESSIONS[session_id]['phone'] = from_phone
                    ACTIVE_QR_SESSIONS[session_id]['token_no'] = result['token_no']
                    return jsonify({'status': 'authenticated', 'session_id': session_id, 'token_no': result['token_no']}), 200

    # 2. Interactive Inbound Bot Commands (STATUS, RX, DELAY, CANCEL)
    with get_db() as conn:
        cur = conn.cursor()

        # Command: STATUS / WHERE / QUEUE
        if any(cmd in incoming_upper for cmd in ('STATUS', 'WHERE', 'QUEUE', 'WAIT')):
            cur.execute("""
                SELECT t.*, c.name, c.preferred_language 
                FROM tokens t
                JOIN customers c ON t.customer_id = c.id
                WHERE c.phone LIKE ? AND t.status IN ('WAITING', 'CALLED')
                ORDER BY t.id DESC LIMIT 1
            """, (f"%{from_phone}%",))
            active_tok = cur.fetchone()
            if active_tok:
                # Calculate waiting ahead
                cur.execute("SELECT COUNT(*) as ahead FROM tokens WHERE status = 'WAITING' AND id < ?", (active_tok['id'],))
                ahead = cur.fetchone()['ahead']
                est = (ahead + 1) * 3
                lan_ip = get_lan_ip()
                reply = (
                    f"🎟️ *SmartQ Live Status Report*\n"
                    f"-------------------------------\n"
                    f"Hello *{active_tok['name']}*,\n"
                    f"Your Token Number: *#{active_tok['token_no']}*\n"
                    f"Status: *{active_tok['status']}*\n"
                    f"Ahead of you: *{ahead} patients*\n"
                    f"Estimated Wait: *~{est} minutes*\n"
                    f"Counter: *{active_tok['counter']}*\n\n"
                    f"🔗 Live QR Tracking: {BASE_WEBSITE_URL}/track.html?token={active_tok['token_no']}"
                )
                send_whatsapp_notification(conn, active_tok['id'], from_phone, reply, 'BOT_STATUS_REPLY')
                return jsonify({'status': 'status_replied', 'token_no': active_tok['token_no'], 'ahead': ahead, 'reply': reply}), 200

        # Command: RX / PRESCRIPTION / MEDICINE
        if any(cmd in incoming_upper for cmd in ('RX', 'PRESCRIPTION', 'MEDICINE', 'MEDS')):
            cur.execute("""
                SELECT t.*, c.name 
                FROM tokens t
                JOIN customers c ON t.customer_id = c.id
                WHERE c.phone LIKE ? AND t.status = 'COMPLETED'
                ORDER BY t.id DESC LIMIT 1
            """, (f"%{from_phone}%",))
            comp_tok = cur.fetchone()
            if comp_tok:
                lan_ip = get_lan_ip()
                reply = (
                    f"💊 *SmartQ Digital Prescription Slip*\n"
                    f"-----------------------------------\n"
                    f"Patient: *{comp_tok['name']}*\n"
                    f"Token: *#{comp_tok['token_no']}*\n"
                    f"Doctor: *{comp_tok['doctor_name']}*\n"
                    f"Diagnosis: *{comp_tok['diagnosis']}*\n\n"
                    f"🔗 View & Print Official Prescription:\n"
                    f"{BASE_WEBSITE_URL}/track.html?token={comp_tok['token_no']}"
                )
                send_whatsapp_notification(conn, comp_tok['id'], from_phone, reply, 'BOT_RX_REPLY')
                return jsonify({'status': 'rx_replied', 'token_no': comp_tok['token_no'], 'reply': reply}), 200

        # Command: CANCEL / QUIT / STOP
        if any(cmd in incoming_upper for cmd in ('CANCEL', 'QUIT', 'STOP')):
            cur.execute("""
                UPDATE tokens SET status = 'SKIPPED', completed_at = datetime('now', 'localtime')
                WHERE id IN (
                    SELECT t.id FROM tokens t
                    JOIN customers c ON t.customer_id = c.id
                    WHERE c.phone LIKE ? AND t.status = 'WAITING'
                    ORDER BY t.id DESC LIMIT 1
                )
            """, (f"%{from_phone}%",))
            conn.commit()
            reply = "❌ Your token has been canceled. Text 'HI' anytime to book a fresh token."
            send_whatsapp_notification(conn, None, from_phone, reply, 'BOT_CANCEL_REPLY')
            return jsonify({'status': 'token_canceled', 'reply': reply}), 200

    # 3. General incoming text (e.g. "Hi", "Token", or Patient's name) -> Auto-register token!
    patient_name = incoming_text if (len(incoming_text) < 30 and incoming_upper not in ('HI', 'HELLO', 'TOKEN', 'START')) else "WhatsApp Patient"

    result = create_token_record(
        name=patient_name,
        phone=from_phone,
        source='whatsapp-bot'
    )

    return jsonify({
        'status': 'token_created',
        'phone': from_phone,
        'token_no': result['token_no'],
        'position': result['position']
    }), 200

# ---------------------------------------------------------
# WhatsApp Web Sender APIs (Direct Account Linking)
# ---------------------------------------------------------

@app.route('/api/whatsapp/web/status', methods=['GET'])
def api_whatsapp_web_status():
    """Get live connection state of the WhatsApp Web sender."""
    from whatsapp_web_engine import whatsapp_web_engine
    return jsonify(whatsapp_web_engine.get_status()), 200

@app.route('/api/whatsapp/web/start', methods=['POST'])
def api_whatsapp_web_start():
    """Start the WhatsApp Web browser session to scan QR code."""
    from whatsapp_web_engine import whatsapp_web_engine
    whatsapp_web_engine.start()
    return jsonify({'success': True, 'message': 'WhatsApp Web worker initiated. Fetching QR code...'}), 200

@app.route('/api/whatsapp/web/qr.png', methods=['GET'])
def api_whatsapp_web_qr():
    """Return live QR code screenshot of WhatsApp Web canvas."""
    import time
    from whatsapp_web_engine import whatsapp_web_engine
    if not whatsapp_web_engine.running:
        whatsapp_web_engine.start()

    qr_bytes = whatsapp_web_engine.get_qr_bytes()
    if not qr_bytes:
        for _ in range(6):
            time.sleep(0.5)
            qr_bytes = whatsapp_web_engine.get_qr_bytes()
            if qr_bytes:
                break

    if qr_bytes:
        return send_file(io.BytesIO(qr_bytes), mimetype='image/png')
    
    # Return placeholder while WhatsApp Web loads
    qr = qrcode.QRCode(version=1, box_size=6, border=1)
    qr.add_data("https://web.whatsapp.com")
    qr.make(fit=True)
    img = qr.make_image(fill_color="#25D366", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/api/whatsapp/web/send-test', methods=['POST'])
def api_whatsapp_web_send_test():
    """Send a quick test message via linked WhatsApp Web."""
    data = request.get_json(silent=True) or {}
    phone = data.get('phone', '').strip()
    msg = data.get('message', 'Hello from SmartQ Queue Management System!').strip()
    
    from whatsapp_web_engine import whatsapp_web_engine
    success = whatsapp_web_engine.send_message(phone, msg)
    return jsonify({'success': success, 'phone': phone, 'message': msg}), 200

MULTILANG_NUMBER_MAP = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'oh': '0', 'double': '',
    # Telugu digits
    'సున్నా': '0', 'ఒకటి': '1', 'రెండు': '2', 'మూడు': '3', 'నాలుగు': '4',
    'ఐదు': '5', 'ఆరు': '6', 'ఏడు': '7', 'ఎనిమిది': '8', 'తొమ్మిది': '9',
    # Tamil digits (Formal & Spoken)
    'பூஜ்ஜியம்': '0', 'பூஜ்யம்': '0',
    'ஒன்று': '1', 'ஒன்னு': '1',
    'இரண்டு': '2', 'ரெண்டு': '2',
    'மூன்று': '3', 'மூணு': '3',
    'நான்கு': '4', 'நாலு': '4',
    'ஐந்து': '5', 'அஞ்சு': '5',
    'ஆறு': '6',
    'ஏழு': '7',
    'எட்டு': '8',
    'ஒன்பது': '9'
}

def parse_spoken_digits(transcript):
    """Convert spoken number words in English, Telugu or Tamil to digit string."""
    if not transcript:
        return ""
    clean = ' ' + transcript.lower() + ' '
    for word, digit in MULTILANG_NUMBER_MAP.items():
        clean = re.sub(rf'(?:\b|\s|^){re.escape(word)}(?:\b|\s|$)', f' {digit} ', clean)
    digits = re.sub(r'\D', '', clean)
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    return digits

# ---------------------------------------------------------
@app.route('/api/speech/transcribe', methods=['POST'])
def api_speech_transcribe():
    """
    Dual-mode backend speech-to-text recognition endpoint using Google Speech API.
    Accepts WAV audio file (multipart/form-data or raw bytes) and returns transcribed text.
    Handles English, Telugu and Tamil accents with automatic cross-language fallback.
    """
    if sr is None:
        return jsonify({'success': False, 'message': 'Speech recognition library not available'}), 503

    audio_bytes = None
    if 'audio' in request.files:
        audio_file = request.files['audio']
        audio_bytes = audio_file.read()
    elif request.data:
        audio_bytes = request.data

    if not audio_bytes or len(audio_bytes) < 100:
        return jsonify({'success': False, 'message': 'No audio data received or audio too short'}), 400

    target_lang = request.args.get('lang', 'te')
    step = request.args.get('step', 'NAME')

    # Map language codes (English, Telugu, Tamil)
    if target_lang == 'ta':
        primary_code = 'ta-IN'
        secondary_code = 'en-IN'
    elif target_lang == 'te':
        primary_code = 'te-IN'
        secondary_code = 'en-IN'
    else:
        primary_code = 'en-IN'
        secondary_code = 'ta-IN'

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        audio_buf = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_buf) as source:
            audio_data = recognizer.record(source)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Invalid audio format: {str(e)}'}), 400

    transcript = ""
    used_lang = primary_code

    # 1. Try primary language
    try:
        transcript = recognizer.recognize_google(audio_data, language=primary_code)
    except (sr.UnknownValueError, sr.RequestError):
        # 2. Try secondary language as fallback
        try:
            transcript = recognizer.recognize_google(audio_data, language=secondary_code)
            used_lang = secondary_code
        except Exception:
            transcript = ""

    transcript = transcript.strip()
    digits = parse_spoken_digits(transcript)

    if not transcript:
        return jsonify({
            'success': False,
            'transcript': '',
            'message': 'No clear speech recognized. Please speak closer to microphone.'
        }), 200

    return jsonify({
        'success': True,
        'transcript': transcript,
        'digits': digits,
        'language': used_lang,
        'step': step
    }), 200

# ---------------------------------------------------------
# Customer & Kiosk API Endpoints
# ---------------------------------------------------------

@app.route('/api/tokens/register', methods=['POST'])
def api_customer_register():
    """Customer registration via Web / QR scan (Name and 10-digit mobile mandatory)."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    raw_phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    language = data.get('preferred_language', 'en')
    is_priority = bool(data.get('is_priority', False))
    priority_reason = data.get('priority_reason', '').strip()

    # Name is mandatory
    if not name:
        return jsonify({'success': False, 'message': 'Patient name is mandatory / దయచేసి పేరు నమోదు చేయండి'}), 400

    # Phone is mandatory and must be 10 digits
    phone = clean_phone_number(raw_phone)
    if len(phone) != 10:
        return jsonify({'success': False, 'message': 'A valid 10-digit mobile number is mandatory / దయచేసి 10 అంకెల మొబైల్ నంబర్ నమోదు చేయండి'}), 400

    result = create_token_record(
        name=name,
        phone=phone,
        email=email,
        language=language,
        is_priority=is_priority,
        priority_reason=priority_reason,
        source='qr'
    )

    return jsonify({
        'success': True,
        'token_no': result['token_no'],
        'patient_name': name,
        'phone': phone,
        'position': result['position'],
        'language': result['language'],
        'ticket_url': f"/ticket/{result['token_no']}",
        'whatsapp_link': result.get('whatsapp_link')
    }), 201

@app.route('/api/tokens/voice-kiosk', methods=['POST'])
def api_voice_kiosk_register():
    """Voice Kiosk Token Generation with mandatory spoken name and mobile number."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    raw_phone = data.get('phone', '').strip()
    language = data.get('preferred_language', 'en')
    is_priority = bool(data.get('is_priority', False))

    if not name:
        return jsonify({'success': False, 'message': 'Patient name was not detected'}), 400

    phone = clean_phone_number(raw_phone)
    if len(phone) != 10:
        return jsonify({'success': False, 'message': 'A valid 10-digit mobile number is required'}), 400

    counter = get_setting('counter_name', 'Counter 1')

    result = create_token_record(
        name=name,
        phone=phone,
        language=language,
        is_priority=is_priority,
        priority_reason='Voice Kiosk Patient',
        source='kiosk-voice'
    )

    # Update voice session in settings for ESP32 LCD
    set_setting('voice_session_state', 'COMPLETED')
    set_setting('voice_session_patient_name', name)
    set_setting('voice_session_token_no', result['token_no'])
    set_setting('voice_session_updated', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # Generate custom spoken announcement for patient
    if language == 'te':
        patient_voice_msg = f"ధన్యవాదాలు {name} గారు! మీ టోకెన్ సంఖ్య {result['token_no']}. దయచేసి వేచి ఉండండి."
    else:
        token_spelled = " ".join(list(result['token_no']))
        patient_voice_msg = f"Thank you, {name}! Your token number is {token_spelled}. Please wait for your turn."

    return jsonify({
        'success': True,
        'token_no': result['token_no'],
        'patient_name': name,
        'phone': phone,
        'position': result['position'],
        'counter': counter,
        'language': language,
        'voice_message': patient_voice_msg,
        'ticket_url': f"/ticket/{result['token_no']}"
    }), 201

@app.route('/api/tokens/<token_no>/status', methods=['GET'])
def api_token_status(token_no):
    """Customer live status tracking API."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.name, c.preferred_language
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.token_no = ?
        """, (token_no,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Token not found'}), 404

        token_data = dict(row)
        
        # If waiting, compute waiting position ahead
        ahead = 0
        if token_data['status'] == 'WAITING':
            cur.execute("""
                SELECT COUNT(*) as count FROM tokens 
                WHERE status = 'WAITING' AND id < ?
            """, (token_data['id'],))
            ahead = cur.fetchone()['count']

        # Get currently called token
        cur.execute("SELECT token_no, counter FROM tokens WHERE status = 'CALLED' ORDER BY called_at DESC LIMIT 1")
        called_row = cur.fetchone()
        current_serving = dict(called_row) if called_row else None

        return jsonify({
            'success': True,
            'token': token_data,
            'people_ahead': ahead,
            'estimated_wait_mins': (ahead + 1) * 3,
            'current_serving': current_serving
        })

# ---------------------------------------------------------
# ESP32 Kiosk Hardware API Endpoints
# ---------------------------------------------------------

@app.route('/api/device/voice-session/start', methods=['POST'])
def api_voice_session_start():
    """Triggered when physical GET TOKEN button on ESP32 is pressed."""
    set_setting('voice_session_state', 'LISTENING_NAME')
    set_setting('voice_session_patient_name', '')
    set_setting('voice_session_token_no', '')
    set_setting('voice_session_updated', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    return jsonify({
        'success': True,
        'state': 'LISTENING_NAME',
        'message': 'Voice registration session started'
    })

@app.route('/api/device/voice-session/update', methods=['POST'])
def api_voice_session_update():
    """Update current stage of the voice assistant session."""
    data = request.get_json(silent=True) or {}
    state = data.get('state', 'IDLE')
    name = data.get('name', '')
    token_no = data.get('token_no', '')

    set_setting('voice_session_state', state)
    if name:
        set_setting('voice_session_patient_name', name)
    if token_no:
        set_setting('voice_session_token_no', token_no)
    set_setting('voice_session_updated', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    return jsonify({'success': True, 'state': state})

@app.route('/api/device/voice-session', methods=['GET'])
def api_get_voice_session():
    """Kiosk UI and ESP32 query active voice session state."""
    return jsonify({
        'success': True,
        'state': get_setting('voice_session_state', 'IDLE'),
        'patient_name': get_setting('voice_session_patient_name', ''),
        'token_no': get_setting('voice_session_token_no', ''),
        'updated_at': get_setting('voice_session_updated', '')
    })

@app.route('/api/device/token', methods=['POST'])
def api_device_token():
    """ESP32 GET TOKEN switch handler (generates instant pure numeric token)."""
    token_no = generate_next_token_number()
    seq_digits = re.sub(r'\D', '', str(token_no))
    numeric_token = str(int(seq_digits)) if seq_digits else str(token_no)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO customers (name, phone, preferred_language, created_at)
            VALUES ('Walk-in Patient', '918367047947', 'en', datetime('now', 'localtime'))
        """)
        cust_id = cur.lastrowid
        cur.execute("""
            INSERT INTO tokens (token_no, customer_id, status, is_priority, source, counter, created_at)
            VALUES (?, ?, 'WAITING', 0, 'kiosk-button', 'Counter 1', datetime('now', 'localtime'))
        """, (numeric_token, cust_id))
        tok_id = cur.lastrowid
        conn.commit()

    # Mirror to Supabase Cloud
    try:
        from supabase_service import get_supabase
        sb = get_supabase()
        if sb:
            cust_res = sb.table('customers').insert({
                'name': 'Walk-in Patient',
                'phone': '8367047947',
                'preferred_language': 'en'
            }).execute()
            new_cust_id = cust_res.data[0]['id'] if (cust_res.data and len(cust_res.data) > 0) else None
            sb.table('tokens').insert({
                'token_no': numeric_token,
                'customer_id': new_cust_id,
                'status': 'WAITING',
                'is_priority': 0,
                'source': 'kiosk-button',
                'counter': 'Counter 1'
            }).execute()
            print(f"[Device Token] ✅ Successfully synced Token #{numeric_token} to Supabase Cloud!")
    except Exception as e:
        print(f"[Device Token] Supabase sync note: {e}")

    # Ensure voice state is IDLE
    set_setting('voice_session_state', 'IDLE')

    return jsonify({
        'success': True,
        'token_no': numeric_token,
        'state': 'ISSUED',
        'message': f'Token {numeric_token} generated successfully from physical kiosk!',
        'lcd_line0': 'Walk-in Patient',
        'lcd_line1': f'Token: {numeric_token}',
        'counter': get_setting('counter_name', 'Counter 1')
    }), 200

@app.route('/api/device/status', methods=['GET'])
def api_device_status():
    """ESP32 LCD polling endpoint for real-time status."""
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT t.token_no, t.counter, t.is_priority, c.name as patient_name
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.status = 'CALLED' 
            ORDER BY t.called_at DESC, t.id DESC LIMIT 1
        """)
        called_row = cur.fetchone()

        cur.execute("SELECT COUNT(*) AS count FROM tokens WHERE status = 'WAITING'")
        waiting_count = cur.fetchone()['count']

        help_active = get_setting('help_alert_active', '0') == '1'
        voice_state = get_setting('voice_session_state', 'IDLE')
        voice_name = get_setting('voice_session_patient_name', '')
        voice_token = get_setting('voice_session_token_no', '')

        clean_tok = ""
        if called_row:
            p_name = called_row['patient_name'] or "Patient"
            raw_tok = str(called_row['token_no'])
            digits = re.sub(r'\D', '', raw_tok)
            clean_tok = str(int(digits)) if digits else raw_tok

        # Determine LCD display lines for ESP32: Name on Line 0, Pure numeric Token on Line 1
        if voice_state == 'LISTENING_NAME':
            lcd_l0 = "Speak Your Name "
            lcd_l1 = "Listening Mic..."
        elif voice_state == 'LISTENING_PHONE':
            disp_name = (voice_name[:10] + "..") if len(voice_name) > 10 else voice_name
            lcd_l0 = f"Name: {disp_name:<10}"
            lcd_l1 = "Speak Mobile No "
        elif voice_state == 'COMPLETED' and voice_token:
            digits = re.sub(r'\D', '', str(voice_token))
            v_tok = str(int(digits)) if digits else str(voice_token)
            disp_name = voice_name[:16] if voice_name else "Registered"
            lcd_l0 = f"{disp_name:<16}"
            lcd_l1 = f"Token: {v_tok}"
        elif called_row:
            p_name = called_row['patient_name'] or "Patient"
            lcd_l0 = p_name[:16]
            lcd_l1 = f"Token: {clean_tok}"
        else:
            lcd_l0 = "SmartQ Counter 1"
            lcd_l1 = f"Ready | Wait: {waiting_count}"

        return jsonify({
            'success': True,
            'serving': clean_tok if called_row else 'None',
            'patient_name': called_row['patient_name'] if called_row else '',
            'is_priority': bool(called_row['is_priority']) if called_row else False,
            'counter': get_setting('counter_name', 'Counter 1'),
            'waiting': waiting_count,
            'help_alert': help_active,
            'voice_state': voice_state,
            'lcd_line0': lcd_l0[:16],
            'lcd_line1': lcd_l1[:16]
        })

@app.route('/api/device/repeat', methods=['POST'])
def api_device_repeat():
    """ESP32 REPEAT button press handler."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.preferred_language, c.name
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.status = 'CALLED'
            ORDER BY t.called_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'No token is currently called'}), 400

        token_data = dict(row)
        lang = token_data['preferred_language'] or 'en'
        counter = get_setting('counter_name', 'Counter 1')
        announcements = get_announcement_texts(token_data['token_no'], counter)

        cur.execute("""
            INSERT INTO events (token_id, event_type, language, message)
            VALUES (?, 'TOKEN_REPEATED', ?, ?)
        """, (token_data['id'], lang, f"Repeated call for {token_data['token_no']} via device"))
        conn.commit()

        digits = re.sub(r'\D', '', str(token_data['token_no']))
        clean_tok = str(int(digits)) if digits else str(token_data['token_no'])
        p_name = token_data.get('name') or 'Patient'

        return jsonify({
            'success': True,
            'token': token_data,
            'token_no': clean_tok,
            'patient_name': p_name,
            'lcd_line0': 'REPEAT CALL',
            'lcd_line1': f"Token: {clean_tok}",
            'announcement': announcements,
            'preferred_language': lang
        })

@app.route('/api/device/help', methods=['POST'])
def api_device_help():
    """ESP32 HELP button press handler."""
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    set_setting('help_alert_active', '1')
    set_setting('help_alert_time', now_str)
    set_setting('help_alert_source', 'kiosk')

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (event_type, message)
            VALUES ('HELP_TRIGGERED', 'Assistance requested at Kiosk button')
        """)
        conn.commit()

    return jsonify({
        'success': True,
        'message': 'Help alert triggered successfully',
        'timestamp': now_str
    })

@app.route('/api/device/help/ack', methods=['POST'])
def api_device_help_ack():
    """Staff acknowledges and clears help alert."""
    set_setting('help_alert_active', '0')
    set_setting('help_alert_time', '')
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO events (event_type, message)
            VALUES ('HELP_ACKNOWLEDGED', 'Staff acknowledged kiosk help alert')
        """)
        conn.commit()

    return jsonify({'success': True, 'message': 'Help alert cleared'})

# ---------------------------------------------------------
# Staff Dashboard Queue Management API
# ---------------------------------------------------------

@app.route('/api/queue', methods=['GET'])
def api_get_queue():
    """Returns complete queue state, stats, waiting list, and current serving token."""
    with get_db() as conn:
        cur = conn.cursor()

        # Current serving token
        cur.execute("""
            SELECT t.*, c.name, c.phone, c.preferred_language, c.priority_reason
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.status = 'CALLED'
            ORDER BY t.called_at DESC LIMIT 1
        """)
        called_row = cur.fetchone()
        current_token = dict(called_row) if called_row else None

        # Priority Mode
        priority_mode = get_setting('priority_mode', 'priority_first')

        # Waiting list ordered by policy
        if priority_mode == 'priority_first':
            order_clause = "ORDER BY t.is_priority DESC, t.id ASC"
        else:
            order_clause = "ORDER BY t.id ASC"

        cur.execute(f"""
            SELECT t.*, c.name, c.phone, c.preferred_language, c.priority_reason
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.status = 'WAITING'
            {order_clause}
        """)
        waiting_list = [dict(r) for r in cur.fetchall()]

        # Dynamic AI / Moving Average Estimated Wait Time (mins per patient)
        avg_duration = 3.5
        for idx, w in enumerate(waiting_list, start=1):
            w['position'] = idx
            w['estimated_wait_minutes'] = round(idx * avg_duration)

        # Statistics for today
        cur.execute("SELECT COUNT(*) AS total FROM tokens WHERE date(created_at) = date('now', 'localtime')")
        total_today = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS completed FROM tokens WHERE status = 'COMPLETED' AND date(created_at) = date('now', 'localtime')")
        completed_today = cur.fetchone()['completed']

        cur.execute("SELECT COUNT(*) AS skipped FROM tokens WHERE status = 'SKIPPED' AND date(created_at) = date('now', 'localtime')")
        skipped_today = cur.fetchone()['skipped']

        help_active = get_setting('help_alert_active', '0') == '1'
        help_time = get_setting('help_alert_time', '')

        return jsonify({
            'success': True,
            'current_token': current_token,
            'waiting_list': waiting_list,
            'stats': {
                'total_today': total_today,
                'waiting_count': len(waiting_list),
                'completed_today': completed_today,
                'skipped_today': skipped_today
            },
            'settings': {
                'counter_name': get_setting('counter_name', 'Counter 1'),
                'organization_name': get_setting('organization_name', 'SmartQ Service Center'),
                'priority_mode': priority_mode,
                'help_active': help_active,
                'help_time': help_time
            }
        })

def dispatch_consecutive_5_ahead_alerts(conn, current_serving_token_no, counter='Counter 1'):
    """
    Automated 5-Consecutive Queue Ahead WhatsApp Broadcast.
    When a token is called or completed (queue advances):
    Sends personalized WhatsApp notifications to the next 5 consecutive waiting tokens:
    e.g. If current serving token is 10:
    - Token 11 receives: "You are 1 ahead (NEXT IN LINE!) - Est. ~3 mins"
    - Token 12 receives: "You are 2 ahead in line - Est. ~6 mins"
    - Token 13 receives: "You are 3 ahead in line - Est. ~9 mins"
    - Token 14 receives: "You are 4 ahead in line - Est. ~12 mins"
    - Token 15 receives: "You are 5 ahead in line - Est. ~15 mins"
    
    Each message includes their personal live QR tracking URL:
    http://<lan_ip>:<port>/track/<token_no>
    Dispatches directly through the running WhatsApp microservice (Port 3005).
    """
    cur = conn.cursor()
    priority_mode = get_setting('priority_mode', 'priority_first')
    if priority_mode == 'priority_first':
        order_clause = "ORDER BY t.is_priority DESC, t.id ASC"
    else:
        order_clause = "ORDER BY t.id ASC"

    cur.execute(f"""
        SELECT t.id, t.token_no, t.is_priority, c.name, c.phone, c.preferred_language, c.priority_reason
        FROM tokens t
        LEFT JOIN customers c ON t.customer_id = c.id
        WHERE t.status = 'WAITING'
        {order_clause}
        LIMIT 5
    """)
    waiting_5 = cur.fetchall()

    lan_ip = get_lan_ip()
    org_name = get_setting('organization_name', 'SmartQ Service Center')
    dispatched = []

    for idx, row in enumerate(waiting_5, start=1):
        w_tok = dict(row)
        phone = w_tok.get('phone')
        if not phone:
            continue

        ahead_count = idx
        est_wait = idx * 3
        w_lang = w_tok.get('preferred_language') or 'en'
        w_track_url = f"{BASE_WEBSITE_URL}/track.html?token={w_tok['token_no']}"

        w_upcoming_msg = format_token_upcoming_message(
            token_no=w_tok['token_no'],
            patient_name=w_tok.get('name') or 'Patient',
            current_serving=current_serving_token_no or 'Current',
            ahead_count=ahead_count,
            counter=counter,
            tracking_url=w_track_url,
            est_wait=est_wait,
            org_name=org_name,
            language=w_lang
        )

        send_whatsapp_notification(conn, w_tok['id'], phone, w_upcoming_msg, f'TOKEN_UPCOMING_{ahead_count}_AHEAD')
        cur.execute("UPDATE tokens SET alert_5_ahead_sent = 1 WHERE id = ?", (w_tok['id'],))
        dispatched.append({
            'token_no': w_tok['token_no'],
            'name': w_tok.get('name'),
            'phone': phone,
            'ahead': ahead_count,
            'est_wait': est_wait
        })

    conn.commit()
    return dispatched

@app.route('/api/queue/call-next', methods=['POST'])
def api_call_next():
    """Call the next eligible token from the queue."""
    priority_mode = get_setting('priority_mode', 'priority_first')
    counter = get_setting('counter_name', 'Counter 1')

    with get_db() as conn:
        cur = conn.cursor()

        # If there is already a CALLED token, automatically mark it COMPLETED or update it
        data = request.get_json(silent=True) or {}
        auto_complete_previous = data.get('auto_complete_previous', True)

        if auto_complete_previous:
            cur.execute("""
                UPDATE tokens 
                SET status = 'COMPLETED', completed_at = datetime('now', 'localtime')
                WHERE status = 'CALLED'
            """)

        # Select next token based on priority policy
        if priority_mode == 'priority_first':
            query = """
                SELECT t.*, c.name, c.phone, c.preferred_language 
                FROM tokens t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.status = 'WAITING'
                ORDER BY t.is_priority DESC, t.id ASC
                LIMIT 1
            """
        else:
            query = """
                SELECT t.*, c.name, c.phone, c.preferred_language 
                FROM tokens t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.status = 'WAITING'
                ORDER BY t.id ASC
                LIMIT 1
            """

        cur.execute(query)
        next_token = cur.fetchone()

        if not next_token:
            return jsonify({'success': False, 'message': 'No waiting tokens in queue'}), 404

        token_data = dict(next_token)

        # Update status to CALLED
        cur.execute("""
            UPDATE tokens 
            SET status = 'CALLED', called_at = datetime('now', 'localtime'), counter = ?
            WHERE id = ?
        """, (counter, token_data['id']))

        token_data['status'] = 'CALLED'
        token_data['counter'] = counter

        lang = token_data['preferred_language'] or 'en'
        announcements = get_announcement_texts(token_data['token_no'], counter)

        # Dispatch WhatsApp Turn Alert
        whatsapp_link = None
        phone = token_data.get('phone')
        if phone:
            org_name = get_setting('organization_name', 'SmartQ Service Center')
            wa_call_msg = format_token_called_message(token_data['token_no'], token_data.get('name', 'Patient'), counter, org_name, lang)
            send_whatsapp_notification(conn, token_data['id'], phone, wa_call_msg, 'TOKEN_CALLED')
            whatsapp_link = build_whatsapp_direct_link(phone, wa_call_msg)

        token_data['whatsapp_link'] = whatsapp_link

        # Log event
        cur.execute("""
            INSERT INTO events (token_id, event_type, language, message)
            VALUES (?, 'TOKEN_CALLED', ?, ?)
        """, (token_data['id'], lang, f"Called token {token_data['token_no']} to {counter}"))

        # -------------------------------------------------------------
        # Automated 5-Consecutive Queue Ahead WhatsApp Broadcast
        # (Tokens 1 to 5 ahead automatically receive personalized alerts with their live pass link)
        # -------------------------------------------------------------
        dispatched_5_ahead = dispatch_consecutive_5_ahead_alerts(conn, token_data['token_no'], counter)

        # Sync called token to Supabase Cloud
        sync_token_to_supabase(token_data)
        sync_event_to_supabase(token_data['id'], 'TOKEN_CALLED', lang, f"Called token {token_data['token_no']} to {counter}")

        return jsonify({
            'success': True,
            'token': token_data,
            'announcement': announcements,
            'preferred_language': lang,
            'counter': counter,
            'whatsapp_link': whatsapp_link,
            'dispatched_5_ahead': dispatched_5_ahead
        })

@app.route('/api/queue/repeat', methods=['POST'])
def api_repeat_call():
    """Repeat announcement for currently called token."""
    counter = get_setting('counter_name', 'Counter 1')

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.name, c.phone, c.preferred_language
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.status = 'CALLED'
            ORDER BY t.called_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'No token is currently called'}), 400

        token_data = dict(row)
        lang = token_data['preferred_language'] or 'en'
        announcements = get_announcement_texts(token_data['token_no'], counter)

        # Dispatch repeat WhatsApp alert if phone available
        whatsapp_link = None
        phone = token_data.get('phone')
        if phone:
            org_name = get_setting('organization_name', 'SmartQ Service Center')
            wa_call_msg = format_token_called_message(token_data['token_no'], token_data.get('name', 'Patient'), counter, org_name, lang)
            send_whatsapp_notification(conn, token_data['id'], phone, wa_call_msg, 'TOKEN_REPEATED')
            whatsapp_link = build_whatsapp_direct_link(phone, wa_call_msg)

        cur.execute("""
            INSERT INTO events (token_id, event_type, language, message)
            VALUES (?, 'TOKEN_REPEATED', ?, ?)
        """, (token_data['id'], lang, f"Staff repeated call for {token_data['token_no']}"))
        conn.commit()

        return jsonify({
            'success': True,
            'token': token_data,
            'announcement': announcements,
            'preferred_language': lang,
            'whatsapp_link': whatsapp_link
        })

@app.route('/api/queue/complete', methods=['POST'])
def api_complete_service():
    """Complete service for currently called token with digital prescription & automated WhatsApp receipt."""
    data = request.get_json(silent=True) or {}
    token_id = data.get('token_id')
    diagnosis = data.get('diagnosis', 'General OPD Consultation & Health Checkup').strip()
    doctor_name = data.get('doctor_name', 'Dr. K. Sharma (Consultant Physician)').strip()
    doctor_notes = data.get('doctor_notes', 'Take prescribed medicines on time. Drink warm fluids. Review after 3 days if fever/symptoms persist.').strip()
    
    import json
    raw_prescription = data.get('prescription') or [
        {'name': 'Paracetamol 650mg', 'dosage': '1 tablet', 'frequency': 'Thrice daily (After food)', 'duration': '3 days', 'notes': 'For fever & pain relief'},
        {'name': 'Cetirizine 10mg', 'dosage': '1 tablet', 'frequency': 'Once daily (Night)', 'duration': '5 days', 'notes': 'At bedtime for allergy/cough'},
        {'name': 'Multivitamin + Zinc', 'dosage': '1 tablet', 'frequency': 'Once daily (Morning)', 'duration': '10 days', 'notes': 'Nutritional immunity booster'}
    ]
    prescription_json = json.dumps(raw_prescription) if isinstance(raw_prescription, (list, dict)) else str(raw_prescription)

    with get_db() as conn:
        cur = conn.cursor()
        if token_id:
            cur.execute("""
                SELECT t.*, c.name, c.phone, c.preferred_language
                FROM tokens t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.id = ?
            """, (token_id,))
        else:
            cur.execute("""
                SELECT t.*, c.name, c.phone, c.preferred_language
                FROM tokens t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.status = 'CALLED'
                ORDER BY t.called_at DESC LIMIT 1
            """)
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'No active token found to complete'}), 400

        completed_token = dict(row)
        tid = completed_token['id']

        cur.execute("""
            UPDATE tokens 
            SET status = 'COMPLETED', completed_at = datetime('now', 'localtime'),
                diagnosis = ?, prescription_json = ?, doctor_name = ?, doctor_notes = ?
            WHERE id = ?
        """, (diagnosis, prescription_json, doctor_name, doctor_notes, tid))

        # Automated WhatsApp notification for completion & digital prescription receipt
        phone = completed_token.get('phone')
        whatsapp_link = None
        if phone:
            prescription_url = f"{BASE_WEBSITE_URL}/track.html?token={completed_token['token_no']}"
            org_name = get_setting('organization_name', 'SmartQ Service Center')
            lang = completed_token.get('preferred_language') or 'en'
            wa_comp_msg = format_token_completed_message(
                token_no=completed_token['token_no'],
                patient_name=completed_token.get('name', 'Patient'),
                prescription_url=prescription_url,
                org_name=org_name,
                language=lang
            )
            send_whatsapp_notification(conn, tid, phone, wa_comp_msg, 'TOKEN_COMPLETED')
            whatsapp_link = build_whatsapp_direct_link(phone, wa_comp_msg)

        cur.execute("""
            INSERT INTO events (token_id, event_type, message)
            VALUES (?, 'TOKEN_COMPLETED', ?)
        """, (tid, f"Service completed for {completed_token['token_no']} - Digital Prescription Generated"))
        conn.commit()

        # Cloud Sync Completed State to Supabase
        sync_token_to_supabase({
            'id': tid,
            'token_no': completed_token['token_no'],
            'status': 'COMPLETED',
            'diagnosis': diagnosis,
            'prescription_json': prescription_json,
            'doctor_name': doctor_name,
            'doctor_notes': doctor_notes,
            'completed_at': datetime.now().isoformat()
        })
        sync_event_to_supabase(tid, 'TOKEN_COMPLETED', lang, f"Completed token {completed_token['token_no']}")

        # -------------------------------------------------------------
        # Automated 5-Consecutive Queue Ahead WhatsApp Broadcast
        # When token completes, the next 5 waiting tokens immediately get updated status
        # -------------------------------------------------------------
        cur.execute("SELECT token_no, counter FROM tokens WHERE status = 'CALLED' ORDER BY called_at DESC LIMIT 1")
        active_called = cur.fetchone()
        serving_tok_no = active_called['token_no'] if active_called else f"Completed #{completed_token['token_no']}"
        active_counter = active_called['counter'] if active_called else get_setting('counter_name', 'Counter 1')
        dispatched_5_ahead = dispatch_consecutive_5_ahead_alerts(conn, serving_tok_no, active_counter)

        return jsonify({
            'success': True,
            'message': 'Token service completed and digital prescription generated',
            'token_no': completed_token['token_no'],
            'prescription_url': f"/track/{completed_token['token_no']}",
            'whatsapp_link': whatsapp_link,
            'dispatched_5_ahead': dispatched_5_ahead
        })

@app.route('/api/queue/skip', methods=['POST'])
def api_skip_service():
    """Skip currently called token (or specified token_id)."""
    data = request.get_json(silent=True) or {}
    token_id = data.get('token_id')

    with get_db() as conn:
        cur = conn.cursor()
        if token_id:
            cur.execute("""
                UPDATE tokens 
                SET status = 'SKIPPED', completed_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (token_id,))
        else:
            cur.execute("""
                UPDATE tokens 
                SET status = 'SKIPPED', completed_at = datetime('now', 'localtime')
                WHERE status = 'CALLED'
            """)

        cur.execute("""
            INSERT INTO events (token_id, event_type, message)
            VALUES (?, 'TOKEN_SKIPPED', 'Customer skipped / absent')
        """, (token_id,))
        conn.commit()

        return jsonify({'success': True, 'message': 'Token skipped'})

@app.route('/api/queue/transfer', methods=['POST'])
def api_transfer_token():
    """
    Advanced Inter-Department Counter Routing & Patient Transfer.
    Allows transferring a patient to another department (e.g. Counter 1 -> Counter 3 Pharmacy or Counter 4 Diagnostics).
    Updates token's counter designation, keeps priority, and sends an automated WhatsApp alert to the patient.
    """
    data = request.get_json(silent=True) or {}
    token_id = data.get('token_id')
    token_no = data.get('token_no')
    target_counter = data.get('target_counter', 'Counter 3 (Pharmacy)').strip()
    transfer_notes = data.get('notes', 'Prescription forwarded for dispensing').strip()

    with get_db() as conn:
        cur = conn.cursor()
        if token_id:
            cur.execute("SELECT t.*, c.name, c.phone, c.preferred_language FROM tokens t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.id = ?", (token_id,))
        elif token_no:
            cur.execute("SELECT t.*, c.name, c.phone, c.preferred_language FROM tokens t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.token_no = ?", (token_no,))
        else:
            cur.execute("SELECT t.*, c.name, c.phone, c.preferred_language FROM tokens t LEFT JOIN customers c ON t.customer_id = c.id WHERE t.status = 'CALLED' ORDER BY t.called_at DESC LIMIT 1")
        
        row = cur.fetchone()
        if not row:
            # Fallback to most recent token if none currently called
            cur.execute("SELECT t.*, c.name, c.phone, c.preferred_language FROM tokens t LEFT JOIN customers c ON t.customer_id = c.id ORDER BY t.id DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'No eligible token found for transfer'}), 404

        tok = dict(row)
        tid = tok['id']
        t_num = tok['token_no']
        t_name = tok.get('name') or 'Patient'
        t_phone = tok.get('phone')
        t_lang = tok.get('preferred_language') or 'en'

        cur.execute("""
            UPDATE tokens 
            SET counter = ?, status = 'WAITING', is_priority = 1,
                doctor_notes = coalesce(doctor_notes, '') || ' | Transferred to ' || ? || ': ' || ?
            WHERE id = ?
        """, (target_counter, target_counter, transfer_notes, tid))

        whatsapp_link = None
        if t_phone:
            track_url = f"{BASE_WEBSITE_URL}/track.html?token={t_num}"
            if t_lang == 'te':
                msg = (
                    f"🏥 *SmartQ కేర్ - డిపార్ట్‌మెంట్ బదిలీ*\n"
                    f"--------------------------------\n"
                    f"నమస్కారం *{t_name}* గారు,\n"
                    f"మీ టోకెన్ *#{t_num}* విజయవంతంగా *{target_counter}* కి బదిలీ చేయబడింది.\n\n"
                    f"📝 వివరాలు: {transfer_notes}\n"
                    f"దయచేసి తదుపరి సేవ కోసం *{target_counter}* వద్దకు వెళ్లండి.\n\n"
                    f"🔗 లైవ్ ట్రాకింగ్: {track_url}"
                )
            elif t_lang == 'ta':
                msg = (
                    f"🏥 *SmartQ பராமரிப்பு - துறை மாற்றம்*\n"
                    f"--------------------------------\n"
                    f"வணக்கம் *{t_name}* அவர்களே,\n"
                    f"உங்கள் டோக்கன் *#{t_num}* வெற்றிகரமாக *{target_counter}* கவுண்டருக்கு மாற்றப்பட்டது.\n\n"
                    f"📝 விவரம்: {transfer_notes}\n"
                    f"தயவுசெய்து அடுத்த சேவைக்கு *{target_counter}* கவுண்டருக்கு செல்லவும்.\n\n"
                    f"🔗 நேரலை நிலை: {track_url}"
                )
            else:
                msg = (
                    f"🏥 *SmartQ Care - Department Transfer*\n"
                    f"--------------------------------\n"
                    f"Hello *{t_name}*,\n"
                    f"Your Token *#{t_num}* has been transferred to *{target_counter}*.\n\n"
                    f"📝 Notes: {transfer_notes}\n"
                    f"Please proceed to *{target_counter}* for the next stage of your consultation.\n\n"
                    f"🔗 Track live queue: {track_url}"
                )
            send_whatsapp_notification(conn, tid, t_phone, msg, 'TOKEN_TRANSFERRED')
            whatsapp_link = build_whatsapp_direct_link(t_phone, msg)

        cur.execute("INSERT INTO events (token_id, event_type, language, message) VALUES (?, 'TOKEN_TRANSFERRED', ?, ?)",
                    (tid, t_lang, f"Token {t_num} transferred to {target_counter}"))
        conn.commit()

        tok['counter'] = target_counter
        tok['status'] = 'WAITING'
        tok['is_priority'] = 1
        sync_token_to_supabase(tok)

        return jsonify({
            'success': True,
            'message': f"Token {t_num} transferred to {target_counter}",
            'target_counter': target_counter,
            'token_no': t_num,
            'whatsapp_link': whatsapp_link
        })

@app.route('/api/tokens/staff', methods=['POST'])
def api_staff_create_token():
    """Staff-assisted customer token creation."""
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip()
    language = data.get('preferred_language', 'en')
    is_priority = bool(data.get('is_priority', False))
    priority_reason = data.get('priority_reason', '').strip()

    result = create_token_record(
        name=name or 'Assisted Customer',
        phone=phone,
        email=email,
        language=language,
        is_priority=is_priority,
        priority_reason=priority_reason,
        source='staff'
    )

    return jsonify({
        'success': True,
        'token_no': result['token_no'],
        'position': result['position'],
        'ticket_url': f"/ticket/{result['token_no']}"
    }), 201

@app.route('/api/tokens/<int:token_id>/priority', methods=['POST'])
def api_toggle_priority(token_id):
    """Toggle priority flag for a waiting token."""
    data = request.get_json(silent=True) or {}
    is_priority = 1 if data.get('is_priority', True) else 0

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tokens SET is_priority = ? WHERE id = ?", (is_priority, token_id))
        cur.execute("""
            INSERT INTO events (token_id, event_type, message)
            VALUES (?, 'PRIORITY_CHANGED', ?)
        """, (token_id, f"Priority set to {is_priority}"))
        conn.commit()

        return jsonify({'success': True, 'is_priority': bool(is_priority)})

@app.route('/api/settings/priority-mode', methods=['POST'])
def api_set_priority_mode():
    """Switch queue policy between 'priority_first' and 'fifo'."""
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'priority_first')
    if mode not in ['priority_first', 'fifo']:
        return jsonify({'success': False, 'message': 'Invalid mode'}), 400

    set_setting('priority_mode', mode)
    return jsonify({'success': True, 'priority_mode': mode})

@app.route('/api/events', methods=['GET'])
def api_get_events():
    """Get recent events audit log."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.*, t.token_no 
            FROM events e
            LEFT JOIN tokens t ON e.token_id = t.id
            ORDER BY e.created_at DESC LIMIT 30
        """)
        events = [dict(r) for r in cur.fetchall()]
        return jsonify({'success': True, 'events': events})

@app.route('/api/whatsapp/outbox', methods=['GET'])
def api_whatsapp_outbox():
    """Get recent WhatsApp notifications sent/queued."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT o.*, t.token_no, c.name AS patient_name, c.phone, c.preferred_language
            FROM notification_outbox o
            LEFT JOIN tokens t ON o.token_id = t.id
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE o.channel = 'WHATSAPP'
            ORDER BY o.created_at DESC LIMIT 20
        """)
        rows = [dict(r) for r in cur.fetchall()]
        
        counter = get_setting('counter_name', 'Counter 1')
        org_name = get_setting('organization_name', 'SmartQ Service Center')
        lan_ip = get_lan_ip()

        # Add direct wa.me link for each outbox item
        for r in rows:
            token_no = r.get('token_no') or 'A001'
            p_name = r.get('patient_name') or 'Patient'
            lang = r.get('preferred_language') or 'en'
            phone = r.get('phone') or ''
            
            if r.get('event_type') == 'TOKEN_CALLED':
                msg = format_token_called_message(token_no, p_name, counter, org_name, lang)
            else:
                track_url = f"{BASE_WEBSITE_URL}/track.html?token={token_no}"
                msg = format_token_created_message(token_no, p_name, 1, counter, 3, track_url, org_name, lang)
            
            r['message_preview'] = msg
            r['direct_link'] = build_whatsapp_direct_link(phone, msg) if phone else ''

        return jsonify({'success': True, 'outbox': rows})

@app.route('/api/whatsapp/link', methods=['GET'])
def api_whatsapp_link():
    """Generate dynamic WhatsApp link for a given token."""
    token_no = request.args.get('token_no')
    action = request.args.get('action', 'ticket') # 'ticket' or 'call'
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, c.name, c.phone, c.preferred_language
            FROM tokens t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.token_no = ?
        """, (token_no,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'Token not found'}), 404

        token = dict(row)
        phone = token.get('phone', '')
        if not phone:
            return jsonify({'success': False, 'message': 'No mobile number associated with this token'}), 400

        counter = get_setting('counter_name', 'Counter 1')
        org_name = get_setting('organization_name', 'SmartQ Service Center')
        lang = token.get('preferred_language', 'en')
        tracking_url = f"{BASE_WEBSITE_URL}/track.html?token={token_no}"

        if action == 'call':
            msg = format_token_called_message(token_no, token.get('name', 'Patient'), counter, org_name, lang)
        else:
            msg = format_token_created_message(token_no, token.get('name', 'Patient'), 1, counter, 3, tracking_url, org_name, lang)

        link = build_whatsapp_direct_link(phone, msg)
        return jsonify({
            'success': True,
            'whatsapp_link': link,
            'phone': phone,
            'message_preview': msg
        })

@app.route('/api/whatsapp/send-direct', methods=['POST'])
def api_whatsapp_send_direct():
    """
    Directly dispatch an automated WhatsApp message to a phone number via local microservice (:3005).
    Zero browser tabs or manual wa.me links opened.
    """
    data = request.get_json(silent=True) or {}
    phone = data.get('phone')
    token_no = data.get('token_no')
    name = data.get('name', 'Patient')
    msg = data.get('message')

    if not phone:
        return jsonify({'success': False, 'message': 'Phone number required'}), 400

    lan_ip = get_lan_ip()
    org_name = get_setting('organization_name', 'SmartQ Service Center')
    counter = get_setting('counter_name', 'Counter 1')

    with get_db() as conn:
        if not msg and token_no:
            cur = conn.cursor()
            cur.execute("""
                SELECT t.*, c.name, c.preferred_language
                FROM tokens t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.token_no = ?
            """, (token_no,))
            t_row = cur.fetchone()
            if t_row:
                lang = t_row['preferred_language'] or 'en'
                t_dict = dict(t_row)
                if t_dict['status'] == 'CALLED':
                    msg = format_token_called_message(token_no, t_dict['name'] or name, counter, org_name, lang)
                elif t_dict['status'] == 'COMPLETED':
                    msg = format_token_completed_message(token_no, t_dict['name'] or name, f"{BASE_WEBSITE_URL}/track.html?token={token_no}", org_name, lang)
                else:
                    msg = format_token_created_message(token_no, t_dict['name'] or name, 1, counter, 6, f"{BASE_WEBSITE_URL}/track.html?token={token_no}", org_name, lang)

        if not msg:
            msg = f"🏥 *{org_name}*\nHello *{name}*, your Token *{token_no or ''}* live tracking pass: {BASE_WEBSITE_URL}/track.html?token={token_no or ''}"

        res = send_whatsapp_notification(conn, None, phone, msg, 'DIRECT_DASHBOARD_DISPATCH')
        return jsonify({
            'success': True,
            'message': f"Automated WhatsApp message dispatched to +91{phone} via local microservice (:3005)!",
            'dispatch_status': res.get('status')
        })

@app.route('/api/queue/reset', methods=['POST'])
def api_reset_queue():
    """Reset tokens sequence and clear active tokens for clean demonstration."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tokens SET status = 'COMPLETED' WHERE status IN ('WAITING', 'CALLED')")
        cur.execute("UPDATE settings SET value = '1' WHERE key = 'next_token_seq'")
        cur.execute("UPDATE settings SET value = '0' WHERE key = 'help_alert_active'")
        cur.execute("""
            INSERT INTO events (event_type, message)
            VALUES ('QUEUE_RESET', 'Demo queue reset completed')
        """)
        conn.commit()
    return jsonify({'success': True, 'message': 'Queue reset to initial state'})

@app.route('/api/queue/seed-demo', methods=['POST'])
def api_seed_demo_data():
    """Seed 28 realistic clinic patient tokens into SQLite & Supabase."""
    try:
        from seed_sample_data import seed_database
        seed_database()
        return jsonify({'success': True, 'message': '28 realistic queue tokens seeded and synced to Supabase!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ---------------------------------------------------------
# Supabase Cloud Synchronization APIs
# ---------------------------------------------------------

@app.route('/api/supabase/status', methods=['GET'])
def api_supabase_status():
    """Check connectivity to Supabase cloud database."""
    status = check_supabase_connection()
    return jsonify(status), 200

@app.route('/api/supabase/sync', methods=['POST'])
def api_supabase_sync():
    """Trigger complete sync of all local records to Supabase."""
    with get_db() as conn:
        res = sync_full_database_to_supabase(conn)
    return jsonify(res), 200

@app.route('/api/supabase/schema', methods=['GET'])
def api_supabase_schema():
    """Return the Supabase SQL schema for copying."""
    schema_path = os.path.join(BASE_DIR, 'supabase_schema.sql')
    if os.path.exists(schema_path):
        with open(schema_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'schema': content}), 200
    return jsonify({'success': False, 'message': 'Schema file not found'}), 404

@app.route('/api/realtime-bridge/status', methods=['GET'])
def api_realtime_bridge_status():
    """Return status of the Realtime Cloud-to-Local WhatsApp Bridge."""
    from realtime_bridge import realtime_bridge
    return jsonify({
        'running': realtime_bridge.running,
        'processed_count': realtime_bridge.processed_count,
        'last_poll': realtime_bridge.last_poll_time.isoformat() if realtime_bridge.last_poll_time else None
    })

# ---------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------

if __name__ == '__main__':
    init_db()
    
    # Start Realtime Cloud-to-Local WhatsApp Bridge
    try:
        from realtime_bridge import realtime_bridge
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
            realtime_bridge.start()
    except Exception as e:
        print(f"[Realtime Bridge] Could not start bridge: {e}")

    lan_ip = get_lan_ip()
    print("=" * 65)
    print(" SmartQ - Smart Queue Management & Automated Token Calling")
    print(" Principles of Digital Systems and Design (PDSD) Prototype")
    print("=" * 65)
    print(f" * Staff Dashboard:   http://localhost:{PORT}  or  http://{lan_ip}:{PORT}")
    print(f" * Customer Register: http://{lan_ip}:{PORT}/register")
    print(f" * ESP32 Server URL:  http://{lan_ip}:{PORT}")
    print("=" * 65)
    app.run(host=HOST, port=PORT, debug=True)
