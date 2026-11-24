"""
SmartQ - Realtime Cloud-to-Local WhatsApp Bridge
Subject: Principles of Digital Systems and Design (PDSD)

Architecture & Real-Time Product Flow:
1. Public Website / Mobile Web (GitHub Pages / QR code on patient's phone):
   - Patients register on the website anywhere via cellular data or Wi-Fi.
   - The website directly inserts the customer, token, and a PENDING outbox entry into Supabase Cloud.
2. Local Machine (Clinic / Hospital Laptop where WhatsApp is logged in):
   - The WhatsApp microservice runs locally on http://127.0.0.1:3005 (Sender: K.K +91 8367047947).
   - This Realtime Bridge runs continuously on the local laptop.
   - It polls/subscribes to Supabase Cloud notification_outbox for PENDING alerts.
   - Instantly detects website registrations, formats the trilingual WhatsApp alert, and delivers it via port 3005!
   - Updates Supabase outbox status to DELIVERED.
   - Syncs the new patient into local SQLite smartq.db so the counter staff dashboard & waiting hall TV display update in real time!
"""

import os
import sys
import time
import sqlite3
import requests
import threading
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env'))

LOCAL_GATEWAY_URL = os.getenv('WHATSAPP_LOCAL_GATEWAY_URL', 'http://127.0.0.1:3005').strip()
DB_PATH = os.path.join(BASE_DIR, 'smartq.db')

def get_local_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def send_whatsapp_via_local_microservice(phone, message):
    """Deliver WhatsApp message directly via the local microservice on port 3005."""
    digits = ''.join(filter(str.isdigit, str(phone)))
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    if len(digits) != 10:
        return False, f"Invalid 10-digit phone number: {phone}"

    target_phone = f"91{digits}"
    try:
        res = requests.post(
            f"{LOCAL_GATEWAY_URL}/api/whatsapp/sendMessage",
            json={'phone': target_phone, 'message': message},
            timeout=8
        )
        if res.status_code == 200:
            d = res.json()
            if d.get('success'):
                return True, "Delivered"
            return False, d.get('message', 'Failed')
        return False, f"HTTP {res.status_code}"
    except Exception as e:
        return False, str(e)

class RealtimeWhatsAppBridge:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.running = False
        self.thread = None
        self.last_poll_time = None
        self.processed_count = 0
        self.supabase_client = None

    def _init_supabase(self):
        from supabase_service import get_supabase
        self.supabase_client = get_supabase()
        return self.supabase_client is not None

    def start(self):
        """Start the background cloud listener thread."""
        if self.running and self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="SmartQ-RealtimeBridge")
        self.thread.start()
        print("[Realtime Bridge] 🚀 SmartQ Realtime Cloud-to-Local WhatsApp Bridge started successfully!")

    def stop(self):
        self.running = False

    def _run_loop(self):
        print("[Realtime Bridge] Connecting to Supabase Cloud and local WhatsApp microservice (:3005)...")
        time.sleep(1.0)
        
        while self.running:
            try:
                if not self.supabase_client:
                    if not self._init_supabase():
                        time.sleep(3.0)
                        continue

                # 1. Process PENDING outbox messages (Website Registrations & 5-Ahead alerts)
                self._process_pending_notifications()

                # 2. Sync any newly registered tokens from Cloud to Local SQLite
                self._sync_cloud_tokens_to_local()

                self.last_poll_time = datetime.now()

            except Exception as e:
                # print error quietly without crashing
                time.sleep(2.0)

            time.sleep(1.2)

    def _process_pending_notifications(self):
        """Check Supabase Cloud notification_outbox for PENDING alerts and send them locally."""
        try:
            res = self.supabase_client.table('notification_outbox') \
                .select('id, token_id, phone, message_text, event_type') \
                .eq('status', 'PENDING') \
                .order('id', desc=False) \
                .limit(10) \
                .execute()

            rows = res.data or []
            for r in rows:
                notif_id = r['id']
                phone = r['phone']
                msg = r['message_text']
                event_type = r.get('event_type') or 'TOKEN_ALERT'

                print(f"[Realtime Bridge] ⚡ Processing website notification for +91{phone} (Event: {event_type})...")
                success, reason = send_whatsapp_via_local_microservice(phone, msg)

                if success:
                    self.processed_count += 1
                    print(f"[Realtime Bridge] ✅ DELIVERED WhatsApp alert to +91{phone} via local microservice (:3005)!")
                    # Mark as DELIVERED in Supabase Cloud
                    self.supabase_client.table('notification_outbox') \
                        .update({'status': 'DELIVERED'}) \
                        .eq('id', notif_id) \
                        .execute()
                else:
                    print(f"[Realtime Bridge] ⚠️ WhatsApp dispatch to +91{phone} temporarily failed: {reason}")
                    # Keep as PENDING or retry next cycle
        except Exception as e:
            pass

    def _sync_cloud_tokens_to_local(self):
        """Sync any tokens registered on the website into local SQLite."""
        try:
            with get_local_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT coalesce(max(id), 0) as max_id FROM tokens")
                local_max_id = cur.fetchone()['max_id']

                res = self.supabase_client.table('tokens') \
                    .select('id, token_no, customer_id, status, is_priority, source, counter, created_at, customers(id, name, phone, preferred_language, priority_reason)') \
                    .gt('id', local_max_id) \
                    .order('id', desc=False) \
                    .execute()

                new_tokens = res.data or []
                for tok in new_tokens:
                    cust = tok.get('customers')
                    cust_id = tok.get('customer_id')
                    if cust:
                        cur.execute("""
                            INSERT OR REPLACE INTO customers (id, name, phone, preferred_language, priority_reason, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            cust.get('id', cust_id),
                            cust.get('name', 'Online Patient'),
                            cust.get('phone', ''),
                            cust.get('preferred_language', 'en'),
                            cust.get('priority_reason', ''),
                            cust.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        ))

                    cur.execute("""
                        INSERT OR REPLACE INTO tokens (id, token_no, customer_id, status, is_priority, source, counter, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        tok['id'],
                        tok['token_no'],
                        cust_id,
                        tok.get('status', 'WAITING'),
                        tok.get('is_priority', 0),
                        tok.get('source', 'web-online'),
                        tok.get('counter', 'Counter 1'),
                        tok.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    ))
                    print(f"[Realtime Bridge] 📥 New online patient token #{tok['token_no']} ({cust.get('name') if cust else 'Patient'}) synced to local counter queue!")
                conn.commit()
        except Exception:
            pass

realtime_bridge = RealtimeWhatsAppBridge.get_instance()

if __name__ == '__main__':
    realtime_bridge.start()
    print("Realtime WhatsApp Bridge is running. Press CTRL+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        realtime_bridge.stop()
        print("Realtime Bridge stopped.")
