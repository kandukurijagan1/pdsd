"""
SmartQ - WhatsApp Web Automation Engine
Uses Playwright to link directly with the staff/clinic's real WhatsApp account via QR Code scan.
Once linked, sends automated messages to customers instantly without third-party API fees.
"""

import os
import time
import queue
import urllib.parse
import threading
from datetime import datetime

class WhatsAppWebEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '.whatsapp_web_profile'))
        os.makedirs(self.profile_dir, exist_ok=True)
        self.status = 'DISCONNECTED'  # DISCONNECTED, INITIALIZING, SCAN_QR, CONNECTED, SENDING, ERROR
        self.qr_png_bytes = None
        self.qr_updated_at = None
        self.last_error = None
        self.message_queue = queue.Queue()
        self.thread = None
        self.running = False
        self.playwright = None
        self.browser_context = None
        self.page = None
        self.sent_count = 0
        self.logs = []
        self.lock = threading.Lock()
        self.add_log("Local WhatsApp Web Engine initialized.")

    def add_log(self, text):
        """Append log event with timestamp."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {text}"
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 60:
                self.logs.pop(0)
        print(f"[WhatsApp Web] {text}")

    def start(self):
        """Start background WhatsApp Web automation worker."""
        if self.running and self.thread and self.thread.is_alive():
            return
        self.running = True
        self.status = 'INITIALIZING'
        self.add_log("Starting local WhatsApp Web automation worker...")
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop background worker and close browser."""
        self.running = False
        self.status = 'DISCONNECTED'
        self.add_log("Stopping WhatsApp Web worker...")
        if self.browser_context:
            try:
                self.browser_context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

    def get_status(self):
        """Return live connection state, checking local microservice first."""
        local_gateway = os.getenv('WHATSAPP_LOCAL_GATEWAY_URL', 'http://127.0.0.1:3005').strip()
        if local_gateway:
            try:
                import requests
                r = requests.get(f"{local_gateway}/api/whatsapp/status", timeout=1.5)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('connected'):
                        return {
                            'status': 'CONNECTED',
                            'connected': True,
                            'has_qr': False,
                            'provider': 'KK Security WhatsApp Microservice (Port 3005)',
                            'user': d.get('user', {'phone': '918367047947', 'name': 'K.K'}),
                            'qr_updated_at': None,
                            'queue_size': self.message_queue.qsize(),
                            'sent_count': self.sent_count,
                            'last_error': None,
                            'logs': self.logs[-25:]
                        }
            except Exception:
                pass

        return {
            'status': self.status,
            'connected': self.status in ('CONNECTED', 'SENDING'),
            'has_qr': bool(self.qr_png_bytes),
            'qr_updated_at': self.qr_updated_at.isoformat() if self.qr_updated_at else None,
            'queue_size': self.message_queue.qsize(),
            'sent_count': self.sent_count,
            'last_error': self.last_error,
            'logs': self.logs[-25:]
        }

    def get_qr_bytes(self):
        """Return current QR code PNG bytes."""
        return self.qr_png_bytes

    def send_message(self, phone, message_text, token_id=None):
        """Send message via local microservice (:3005) or queue for WhatsApp Web."""
        if not phone or not message_text:
            return False
        digits = ''.join(filter(str.isdigit, str(phone)))
        if len(digits) == 12 and digits.startswith('91'):
            digits = digits[2:]
        if len(digits) != 10:
            self.add_log(f"⚠️ Invalid phone number for WhatsApp: {phone}")
            return False

        # 1. Try local microservice (Port 3005) first for zero-latency direct delivery!
        local_gateway = os.getenv('WHATSAPP_LOCAL_GATEWAY_URL', 'http://127.0.0.1:3005').strip()
        if local_gateway:
            try:
                import requests
                resp = requests.post(
                    f"{local_gateway}/api/whatsapp/sendMessage",
                    json={'phone': f"91{digits}", 'message': message_text},
                    timeout=5
                )
                if resp.status_code == 200 and resp.json().get('success'):
                    self.sent_count += 1
                    preview = message_text.split('\n')[0][:30]
                    self.add_log(f"✅ DELIVERED to +91{digits} via Microservice (:3005)! ({preview})")
                    return True
            except Exception as e:
                self.add_log(f"Notice: Microservice (:3005) offline ({e}), queuing in Playwright browser...")

        # 2. Fallback to Playwright Chromium queue
        item = {
            'phone': digits,
            'message': message_text,
            'token_id': token_id,
            'queued_at': datetime.now()
        }
        self.message_queue.put(item)
        preview = message_text.split('\n')[0][:30]
        self.add_log(f"📩 Queued automated message for +91{digits} ({preview}...)")
        return True

    def _worker_loop(self):
        """Playwright browser automation loop."""
        from playwright.sync_api import sync_playwright

        try:
            self.playwright = sync_playwright().start()
            print("[WhatsApp Web] Launching persistent browser context...")
            self.browser_context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=True,
                viewport={'width': 1280, 'height': 800},
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
            self.page = self.browser_context.pages[0] if self.browser_context.pages else self.browser_context.new_page()
            self.page.goto('https://web.whatsapp.com', timeout=60000)
            print("[WhatsApp Web] Navigated to https://web.whatsapp.com")
        except Exception as e:
            self.status = 'ERROR'
            self.last_error = f"Browser startup error: {e}"
            print(f"[WhatsApp Web] Startup error: {e}")
            return

        last_qr_refresh_check = 0

        while self.running:
            try:
                # 1. Check if already logged in (chat pane is present)
                is_logged_in = False
                try:
                    chat_pane = self.page.query_selector('#pane-side, div[data-testid="chat-list"]')
                    if chat_pane:
                        is_logged_in = True
                except Exception:
                    is_logged_in = False

                if is_logged_in:
                    if self.status != 'CONNECTED' and self.status != 'SENDING':
                        self.status = 'CONNECTED'
                        self.qr_png_bytes = None
                        self.add_log("🟢 WhatsApp Web Logged In & Ready to Send Messages!")

                    # Process pending message from queue
                    if not self.message_queue.empty():
                        msg_item = self.message_queue.get()
                        self._dispatch_message(msg_item)
                        self.message_queue.task_done()
                    else:
                        time.sleep(0.8)
                else:
                    # 2. Not logged in yet -> Look for QR code
                    self.status = 'SCAN_QR'
                    try:
                        # Auto-click "Reload QR code" button if expired
                        now = time.time()
                        if now - last_qr_refresh_check > 5:
                            last_qr_refresh_check = now
                            refresh_btn = self.page.query_selector('button:has-text("Click to reload QR code"), span[data-icon="refresh"]')
                            if refresh_btn:
                                self.add_log("🔄 QR code expired on screen, auto-refreshing...")
                                refresh_btn.click()
                                time.sleep(1)

                        canvas = self.page.query_selector('canvas')
                        if canvas:
                            self.qr_png_bytes = canvas.screenshot()
                            self.qr_updated_at = datetime.now()
                    except Exception as e:
                        pass
                    time.sleep(1.5)

            except Exception as e:
                self.add_log(f"Worker notice: {e}")
                time.sleep(2)

    def _dispatch_message(self, msg_item):
        """Navigate to chat and send message instantly."""
        phone = msg_item['phone']
        text = msg_item['message']
        self.status = 'SENDING'
        self.add_log(f"🚀 Dispatching WhatsApp message to +91{phone}...")

        try:
            encoded_text = urllib.parse.quote(text)
            url = f"https://web.whatsapp.com/send?phone=91{phone}&text={encoded_text}"
            self.page.goto(url, timeout=30000)

            # Wait for either the send button or compose box (up to 20s)
            sent = False
            for _ in range(40):
                # Check for invalid phone number dialog
                invalid_dialog = self.page.query_selector('div[data-animate-modal-popup="true"]')
                if invalid_dialog:
                    self.add_log(f"⚠️ Phone +91{phone} is not registered on WhatsApp.")
                    ok_btn = self.page.query_selector('div[role="button"]:has-text("OK")')
                    if ok_btn:
                        ok_btn.click()
                    break

                # Check for send button (multiple standard selectors)
                send_btn = self.page.query_selector('span[data-icon="send"], button[aria-label="Send"], button:has(span[data-icon="send"])')
                if send_btn:
                    send_btn.click()
                    sent = True
                    break

                # Alternatively, check compose input and press Enter
                compose_input = self.page.query_selector('footer div[contenteditable="true"]')
                if compose_input:
                    time.sleep(0.3)
                    compose_input.press('Enter')
                    sent = True
                    break

                time.sleep(0.5)

            if sent:
                time.sleep(1.5)  # Wait for message submission into WhatsApp pipeline
                self.sent_count += 1
                self.add_log(f"✅ DELIVERED to +91{phone}! (Total automated sent: {self.sent_count})")
            else:
                self.add_log(f"⚠️ Timeout waiting for send button for +91{phone}.")

        except Exception as e:
            self.add_log(f"❌ Error dispatching to +91{phone}: {e}")
        finally:
            self.status = 'CONNECTED'

# Global Singleton
whatsapp_web_engine = WhatsAppWebEngine.get_instance()
