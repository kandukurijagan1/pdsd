"""
SmartQ Automated Test & Verification Suite
Tests all Modules of the SmartQ System:
  Module 1: Customer Registration (Voice Kiosk, Mandatory Name & 10-digit Mobile, QR scan)
  Module 2: Token Generation (Sequential uniqueness, SQLite persistence)
  Module 3: Queue Management (Priority-first vs FIFO, Call Next, Complete, Skip)
  Module 4: Voice Announcements (English & Telugu text generation)
  Module 5: Display, Monitoring & Device APIs (ESP32 LCD status, Voice Session, Help alert, QR code)
"""

import unittest
import json
import os
import sqlite3
from app import app, init_db, get_db, DATABASE_PATH, set_setting, get_setting

class SmartQTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        init_db()

        # Clean tables for each test
        with get_db() as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM tokens")
            conn.execute("DELETE FROM customers")
            conn.execute("DELETE FROM notification_outbox")
            conn.execute("UPDATE settings SET value = '1' WHERE key = 'next_token_seq'")
            conn.execute("UPDATE settings SET value = '0' WHERE key = 'help_alert_active'")
            conn.execute("UPDATE settings SET value = 'IDLE' WHERE key = 'voice_session_state'")
            conn.execute("UPDATE settings SET value = '' WHERE key = 'voice_session_patient_name'")
            conn.execute("UPDATE settings SET value = '' WHERE key = 'voice_session_token_no'")
            conn.execute("UPDATE settings SET value = 'priority_first' WHERE key = 'priority_mode'")
            conn.commit()

    def test_01_database_tables_created(self):
        """Verify all 5 required tables and default settings exist."""
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r['name'] for r in cur.fetchall()]

            self.assertIn('customers', tables)
            self.assertIn('tokens', tables)
            self.assertIn('settings', tables)
            self.assertIn('events', tables)
            self.assertIn('notification_outbox', tables)

            self.assertEqual(get_setting('next_token_seq'), '1')
            self.assertEqual(get_setting('token_prefix'), 'A')
            self.assertEqual(get_setting('priority_mode'), 'priority_first')
            self.assertEqual(get_setting('help_alert_active'), '0')
        print("✓ Test 1 Passed: Database schema and tables verified.")

    def test_02_kiosk_physical_token_creation(self):
        """Module 1 & 2: Test ESP32 GET TOKEN physical button endpoint."""
        res = self.client.post('/api/device/token')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['state'], 'LISTENING_NAME')
        self.assertEqual(get_setting('voice_session_state'), 'LISTENING_NAME')
        print("✓ Test 2 Passed: Kiosk physical button activates Voice Assistant session.")

    def test_03_customer_qr_registration_mandatory_validation(self):
        """Module 1: Test QR registration with mandatory Name and 10-digit mobile number."""
        # 1. Missing name should fail with 400
        res_fail_name = self.client.post('/api/tokens/register', json={
            'name': '',
            'phone': '9876543210'
        })
        self.assertEqual(res_fail_name.status_code, 400)

        # 2. Invalid phone (< 10 digits) should fail with 400
        res_fail_phone = self.client.post('/api/tokens/register', json={
            'name': 'Ramesh Kumar',
            'phone': '12345'
        })
        self.assertEqual(res_fail_phone.status_code, 400)

        # 3. Valid Customer with English
        res1 = self.client.post('/api/tokens/register', json={
            'name': 'Ramesh Kumar',
            'phone': '9876543210',
            'preferred_language': 'en',
            'is_priority': False
        })
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()
        self.assertEqual(data1['token_no'], 'A001')
        self.assertEqual(data1['patient_name'], 'Ramesh Kumar')
        self.assertEqual(data1['phone'], '9876543210')

        # 4. Valid Customer with Telugu and Priority
        res2 = self.client.post('/api/tokens/register', json={
            'name': 'వెంకటేశ్వర రావు',
            'phone': '919876543210', # handles +91 prefix
            'preferred_language': 'te',
            'is_priority': True,
            'priority_reason': 'Senior Citizen (65 yrs)'
        })
        self.assertEqual(res2.status_code, 201)
        data2 = res2.get_json()
        self.assertEqual(data2['token_no'], 'A002')
        self.assertEqual(data2['phone'], '9876543210')
        print("✓ Test 3 Passed: Customer web registration with mandatory fields & Telugu works.")

    def test_04_priority_queue_ordering(self):
        """Module 3: Priority-first FIFO ordering vs Standard FIFO."""
        self.client.post('/api/tokens/register', json={'name': 'Normal 1', 'phone': '9876543211', 'is_priority': False})
        self.client.post('/api/tokens/register', json={'name': 'Normal 2', 'phone': '9876543212', 'is_priority': False})
        self.client.post('/api/tokens/register', json={'name': 'Priority 1', 'phone': '9876543213', 'is_priority': True})

        # Under 'priority_first' policy, Call Next must serve A003 first!
        res_call = self.client.post('/api/queue/call-next')
        self.assertEqual(res_call.status_code, 200)
        data_call = res_call.get_json()
        self.assertEqual(data_call['token']['token_no'], 'A003')
        self.assertEqual(data_call['token']['status'], 'CALLED')

        # Next call should serve A001
        res_call2 = self.client.post('/api/queue/call-next')
        self.assertEqual(res_call2.status_code, 200)
        self.assertEqual(res_call2.get_json()['token']['token_no'], 'A001')

        # Next call should serve A002
        res_call3 = self.client.post('/api/queue/call-next')
        self.assertEqual(res_call3.status_code, 200)
        self.assertEqual(res_call3.get_json()['token']['token_no'], 'A002')
        print("✓ Test 4 Passed: Priority-first queue policy verified.")

    def test_05_voice_announcements_english_telugu(self):
        """Module 4: Verify English and Telugu announcement texts."""
        self.client.post('/api/tokens/register', json={
            'name': 'Sita',
            'phone': '9876543210',
            'preferred_language': 'te'
        })
        res = self.client.post('/api/queue/call-next')
        data = res.get_json()
        ann = data['announcement']

        self.assertIn('Token number A 0 0 1, please proceed to Counter 1.', ann['en'])
        self.assertIn('టోకెన్ సంఖ్య A 0 0 1, దయచేసి Counter 1 వద్దకు రండి.', ann['te'])
        print(f"✓ Test 5 Passed: Announcements generated successfully:\n   EN: {ann['en']}\n   TE: {ann['te']}")

    def test_06_esp32_device_lcd_status_polling(self):
        """Module 5: Test ESP32 status polling and dynamic LCD lines."""
        # Initial status
        res1 = self.client.get('/api/device/status')
        self.assertEqual(res1.status_code, 200)
        d1 = res1.get_json()
        self.assertEqual(d1['serving'], 'None')
        self.assertEqual(d1['waiting'], 0)
        self.assertIn('lcd_line0', d1)
        self.assertIn('lcd_line1', d1)

        # After calling a token
        self.client.post('/api/tokens/register', json={'name': 'Patient A', 'phone': '9876543210'})
        self.client.post('/api/queue/call-next')

        res2 = self.client.get('/api/device/status')
        d2 = res2.get_json()
        self.assertEqual(d2['serving'], 'A001')
        self.assertIn('A001', d2['lcd_line0'])
        print("✓ Test 6 Passed: ESP32 LCD polling status verified.")

    def test_07_esp32_help_alert_workflow(self):
        """Module 4 & 5: Test Help button trigger and staff acknowledgment."""
        res_help = self.client.post('/api/device/help')
        self.assertEqual(res_help.status_code, 200)
        self.assertEqual(get_setting('help_alert_active'), '1')

        res_status = self.client.get('/api/device/status')
        self.assertTrue(res_status.get_json()['help_alert'])

        res_ack = self.client.post('/api/device/help/ack')
        self.assertEqual(res_ack.status_code, 200)
        self.assertEqual(get_setting('help_alert_active'), '0')
        print("✓ Test 7 Passed: ESP32 Help alert and Staff ACK workflow verified.")

    def test_08_complete_and_skip_transitions(self):
        """Module 3: Verify token lifecycle WAITING -> CALLED -> COMPLETED / SKIPPED."""
        self.client.post('/api/tokens/register', json={'name': 'P1', 'phone': '9876543210'})
        self.client.post('/api/tokens/register', json={'name': 'P2', 'phone': '9876543211'})

        # Call A001
        self.client.post('/api/queue/call-next')
        # Complete A001
        res_comp = self.client.post('/api/queue/complete')
        self.assertEqual(res_comp.status_code, 200)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status FROM tokens WHERE token_no = 'A001'")
            self.assertEqual(cur.fetchone()['status'], 'COMPLETED')

        # Call A002
        self.client.post('/api/queue/call-next')
        # Skip A002
        res_skip = self.client.post('/api/queue/skip')
        self.assertEqual(res_skip.status_code, 200)

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status FROM tokens WHERE token_no = 'A002'")
            self.assertEqual(cur.fetchone()['status'], 'SKIPPED')
        print("✓ Test 8 Passed: Token status transitions (COMPLETED & SKIPPED) verified.")

    def test_09_voice_kiosk_full_interactive_registration(self):
        """Advanced Feature: Voice Kiosk token creation with spoken name and 10-digit mobile."""
        # 1. Start session
        self.client.post('/api/device/voice-session/start')
        self.assertEqual(get_setting('voice_session_state'), 'LISTENING_NAME')

        # 2. Patient speaks name -> Kiosk updates session
        self.client.post('/api/device/voice-session/update', json={
            'state': 'LISTENING_PHONE',
            'name': 'Laxmamma'
        })
        self.assertEqual(get_setting('voice_session_state'), 'LISTENING_PHONE')

        # 3. Patient speaks 10-digit mobile -> Complete voice token creation
        res_voice = self.client.post('/api/tokens/voice-kiosk', json={
            'name': 'Laxmamma',
            'phone': '9848012345',
            'preferred_language': 'te'
        })
        self.assertEqual(res_voice.status_code, 201)
        data = res_voice.get_json()
        self.assertEqual(data['token_no'], 'A001')
        self.assertEqual(data['patient_name'], 'Laxmamma')
        self.assertEqual(data['phone'], '9848012345')
        self.assertIn('ధన్యవాదాలు', data['voice_message'])
        self.assertIn('A001', data['voice_message'])

        # Verify LCD lines for ESP32
        res_status = self.client.get('/api/device/status')
        d = res_status.get_json()
        self.assertIn('A001', d['lcd_line0'])
        self.assertIn('Laxmamma', d['lcd_line1'])
        print(f"✓ Test 9 Passed: Advanced Voice Kiosk registration succeeded for Laxmamma (A001).")

    def test_10_whatsapp_connectivity_and_outbox(self):
        """Feature: WhatsApp notification dispatch and outbox tracking."""
        # 1. Register customer with phone
        res_reg = self.client.post('/api/tokens/register', json={
            'name': 'Kalyan',
            'phone': '9876543210',
            'preferred_language': 'en'
        })
        self.assertEqual(res_reg.status_code, 201)
        data_reg = res_reg.get_json()
        self.assertIn('whatsapp_link', data_reg)
        self.assertIn('https://wa.me/919876543210', data_reg['whatsapp_link'])

        # 2. Check notification_outbox table
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM notification_outbox WHERE channel = 'WHATSAPP'")
            outbox_rows = cur.fetchall()
            self.assertGreaterEqual(len(outbox_rows), 1)
            self.assertEqual(outbox_rows[0]['event_type'], 'TOKEN_CREATED')

        # 3. Call next -> Should trigger TOKEN_CALLED WhatsApp alert
        res_call = self.client.post('/api/queue/call-next')
        self.assertEqual(res_call.status_code, 200)
        data_call = res_call.get_json()
        self.assertIn('whatsapp_link', data_call)

        # 4. Check outbox API endpoint
        res_outbox = self.client.get('/api/whatsapp/outbox')
        self.assertEqual(res_outbox.status_code, 200)
        d_outbox = res_outbox.get_json()
        self.assertTrue(d_outbox['success'])
        self.assertGreaterEqual(len(d_outbox['outbox']), 2)
        print("✓ Test 10 Passed: WhatsApp notification dispatch, outbox logging & direct links verified.")

    def test_11_speech_transcription_and_digit_parsing(self):
        """Feature: Dual-mode speech transcription endpoint and Telugu/English digit parsing."""
        from app import parse_spoken_digits

        # 1. Test digit parsing of spoken English
        en_spoken = "nine eight four nine zero one two three four five"
        self.assertEqual(parse_spoken_digits(en_spoken), "9849012345")

        # 2. Test digit parsing of spoken Telugu
        te_spoken = "తొమ్మిది ఎనిమిది నాలుగు తొమ్మిది సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు"
        self.assertEqual(parse_spoken_digits(te_spoken), "9849012345")

        # 3. Test empty request on /api/speech/transcribe returns 400
        res_empty = self.client.post('/api/speech/transcribe')
        self.assertEqual(res_empty.status_code, 400)
        print("✓ Test 11 Passed: Dual-mode speech transcription & multilingual digit parsing verified.")

    def test_12_proactive_5_ahead_alert_and_completed_prescription_qr(self):
        """Feature: 5-Ahead automatic WhatsApp alerts, QR tracking & Digital Prescription upon completion."""
        # 1. Register 7 tokens with phone numbers
        for i in range(1, 8):
            res = self.client.post('/api/tokens/register', json={
                'name': f'Patient {i}',
                'phone': f'987654321{i}',
                'preferred_language': 'en'
            })
            self.assertEqual(res.status_code, 201)

        # 2. Call next token (A001)
        res_call = self.client.post('/api/queue/call-next')
        self.assertEqual(res_call.status_code, 200)

        # 3. Verify that Token A006 (5 ahead of current counter) received TOKEN_UPCOMING_5_AHEAD
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT n.*, t.token_no 
                FROM notification_outbox n
                JOIN tokens t ON n.token_id = t.id
                WHERE n.event_type = 'TOKEN_UPCOMING_5_AHEAD'
            """)
            alerts_5_ahead = cur.fetchall()
            self.assertGreaterEqual(len(alerts_5_ahead), 1)
            self.assertEqual(alerts_5_ahead[0]['token_no'], 'A006')
            self.assertIn('You are 5 ahead in line', alerts_5_ahead[0]['message_text'])

        # 4. Track Token A001 while CALLED -> Live queue tracker active
        res_track_live = self.client.get('/track/A001')
        self.assertEqual(res_track_live.status_code, 200)
        self.assertIn(b'IT\'S YOUR TURN NOW!', res_track_live.data)

        # 5. Complete A001 with custom medical prescription
        res_comp = self.client.post('/api/queue/complete', json={
            'diagnosis': 'Acute Seasonal Bronchitis',
            'doctor_notes': 'Take antibiotics after meals. Review in 5 days.',
            'prescription': [
                {'name': 'Amoxicillin 500mg', 'dosage': '1 Cap', 'frequency': 'Thrice daily', 'duration': '5 Days', 'notes': 'Antibiotic course'},
                {'name': 'Paracetamol 650mg', 'dosage': '1 Tab', 'frequency': 'As needed', 'duration': '3 Days', 'notes': 'For fever'}
            ]
        })
        self.assertEqual(res_comp.status_code, 200)
        d_comp = res_comp.get_json()
        self.assertTrue(d_comp['success'])

        # 6. Track Token A001 after completion -> QR tracking deactivated, Digital Prescription displayed!
        res_track_done = self.client.get('/track/A001')
        self.assertEqual(res_track_done.status_code, 200)
        self.assertIn(b'Active Queue Ticket Expired', res_track_done.data)
        self.assertIn(b'Acute Seasonal Bronchitis', res_track_done.data)
        self.assertIn(b'Amoxicillin 500mg', res_track_done.data)

        # 7. Verify Token specific QR code endpoint
        res_qr = self.client.get('/api/qr/token/A001')
        self.assertEqual(res_qr.status_code, 200)
        self.assertEqual(res_qr.content_type, 'image/png')
        print("✓ Test 12 Passed: 5-Ahead automated WhatsApp alerts, QR tracking lock & Digital Prescription verified.")

    def test_13_whatsapp_login_otp_and_handshake_session(self):
        """Test complete WhatsApp Login Suite: OTP dispatch, OTP verification, QR handshake session & Inbound Webhook."""
        test_phone = '9849099887'
        test_name = 'Srinivas Rao'

        # 1. Request WhatsApp OTP
        res_send = self.client.post('/api/auth/whatsapp/send-otp', json={
            'phone': test_phone,
            'name': test_name
        })
        self.assertEqual(res_send.status_code, 200)
        d_send = res_send.get_json()
        self.assertTrue(d_send['success'])
        self.assertIn('otp', d_send)

        # 2. Reject incorrect OTP
        res_bad_otp = self.client.post('/api/auth/whatsapp/verify-otp', json={
            'phone': test_phone,
            'otp': '000000',
            'name': test_name
        })
        self.assertEqual(res_bad_otp.status_code, 401)

        # 3. Accept valid OTP (using demo master code '123456' or returned otp)
        res_verify = self.client.post('/api/auth/whatsapp/verify-otp', json={
            'phone': test_phone,
            'otp': '123456',
            'name': test_name,
            'preferred_language': 'te'
        })
        self.assertEqual(res_verify.status_code, 200)
        d_verify = res_verify.get_json()
        self.assertTrue(d_verify['success'])
        token_no = d_verify['token_no']
        self.assertIsNotNone(token_no)
        self.assertEqual(d_verify['redirect_url'], f"/track/{token_no}")

        # 4. Check returning user fast login (already has active token)
        res_relogin = self.client.post('/api/auth/whatsapp/verify-otp', json={
            'phone': test_phone,
            'otp': '123456',
            'name': test_name
        })
        self.assertEqual(res_relogin.status_code, 200)
        d_relogin = res_relogin.get_json()
        self.assertTrue(d_relogin['already_active'])
        self.assertEqual(d_relogin['token_no'], token_no)

        # 5. Create WhatsApp Scan-to-Login QR Session
        res_qr_sess = self.client.post('/api/auth/whatsapp/qr-session')
        self.assertEqual(res_qr_sess.status_code, 200)
        d_qr_sess = res_qr_sess.get_json()
        session_id = d_qr_sess['session_id']
        self.assertIn('LOGIN%20SMARTQ', d_qr_sess['whatsapp_url'])

        # 6. Fetch QR Code PNG
        res_qr_img = self.client.get(f"/api/auth/whatsapp/qr-image/{session_id}")
        self.assertEqual(res_qr_img.status_code, 200)
        self.assertEqual(res_qr_img.content_type, 'image/png')

        # 7. Check session before scan (must be PENDING)
        res_chk_pre = self.client.get(f"/api/auth/whatsapp/check-session/{session_id}")
        self.assertEqual(res_chk_pre.get_json()['status'], 'PENDING')

        # 8. Simulate inbound WhatsApp Webhook handshake from patient
        res_webhook = self.client.post('/api/whatsapp/webhook', json={
            'phone': '9848123456',
            'message': f"LOGIN SMARTQ {session_id}"
        })
        self.assertEqual(res_webhook.status_code, 200)
        d_webhook = res_webhook.get_json()
        self.assertEqual(d_webhook['status'], 'authenticated')
        handshake_token = d_webhook['token_no']

        # 9. Verify session polled status is now LOGGED_IN
        res_chk_post = self.client.get(f"/api/auth/whatsapp/check-session/{session_id}")
        d_chk_post = res_chk_post.get_json()
        self.assertEqual(d_chk_post['status'], 'LOGGED_IN')
        self.assertEqual(d_chk_post['token_no'], handshake_token)

        # 10. Test general incoming message to WhatsApp bot auto-generates token
        res_bot_msg = self.client.post('/api/whatsapp/webhook', json={
            'phone': '9123456789',
            'message': 'Hi, I need a token for doctor visit'
        })
        self.assertEqual(res_bot_msg.status_code, 200)
        self.assertEqual(res_bot_msg.get_json()['status'], 'token_created')

        print("✓ Test 13 Passed: Complete WhatsApp Login Suite (OTP, QR Handshake, Returning User & Inbound Webhook) verified.")

    def test_14_supabase_connection_and_sync(self):
        """Test Supabase Cloud connection status, schema retrieval, and synchronization APIs."""
        # 1. Test Supabase Status endpoint
        res_status = self.client.get('/api/supabase/status')
        self.assertEqual(res_status.status_code, 200)
        d_status = res_status.get_json()
        self.assertTrue(d_status['connected'])
        self.assertEqual(d_status['url'], 'https://mnsfeojsbzomvhcuiaur.supabase.co')
        self.assertTrue(d_status['has_secret_key'])

        # 2. Test Supabase Schema retrieval endpoint
        res_schema = self.client.get('/api/supabase/schema')
        self.assertEqual(res_schema.status_code, 200)
        d_schema = res_schema.get_json()
        self.assertTrue(d_schema['success'])
        self.assertIn('CREATE TABLE IF NOT EXISTS public.tokens', d_schema['schema'])
        self.assertIn('CREATE TABLE IF NOT EXISTS public.customers', d_schema['schema'])

        # 3. Test Full Sync endpoint
        res_sync = self.client.post('/api/supabase/sync')
        self.assertEqual(res_sync.status_code, 200)
        d_sync = res_sync.get_json()
        self.assertIn('success', d_sync)

        print("✓ Test 14 Passed: Supabase Cloud Database Connection, Schema & Sync APIs verified.")

    def test_15_whatsapp_web_engine(self):
        """Test WhatsApp Web direct account linking status, message queuing, and registration dispatch."""
        # 1. Test WhatsApp Web Status endpoint
        res_status = self.client.get('/api/whatsapp/web/status')
        self.assertEqual(res_status.status_code, 200)
        d_status = res_status.get_json()
        self.assertIn('status', d_status)
        self.assertIn('queue_size', d_status)

        # 2. Test send-test message endpoint
        res_send = self.client.post('/api/whatsapp/web/send-test', json={
            'phone': '9849012345',
            'message': 'SmartQ Automated Registration Alert'
        })
        self.assertEqual(res_send.status_code, 200)
        d_send = res_send.get_json()
        self.assertTrue(d_send['success'])

        # 3. Register a new patient and verify WhatsApp notification is instantly queued
        res_reg = self.client.post('/api/tokens/register', json={
            'name': 'WhatsApp Auto Test',
            'phone': '9876543210',
            'preferred_language': 'en'
        })
        self.assertEqual(res_reg.status_code, 201)
        d_reg = res_reg.get_json()
        self.assertTrue(d_reg['success'])

        # Check outbox
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM notification_outbox WHERE phone LIKE '%9876543210%' ORDER BY id DESC LIMIT 1")
            outbox_row = cur.fetchone()
            self.assertIsNotNone(outbox_row)
            self.assertIn('A0', outbox_row['message_text'])

        print("✓ Test 15 Passed: WhatsApp Web Sender Status, Queuing & Instant Registration Alert verified.")

    def test_16_public_display_and_inter_department_transfer(self):
        """Test Hospital Public TV Wall Display, Inter-Department Counter Transfer & Inbound Bot Commands."""
        # 1. Test /display Public TV screen route
        res_display = self.client.get('/display')
        self.assertEqual(res_display.status_code, 200)
        self.assertIn(b'Waiting Hall Display', res_display.data)
        self.assertIn(b'tvLiveClock', res_display.data)

        # Register and call token to test transfer
        self.client.post('/api/tokens/register', json={
            'name': 'Transfer Patient',
            'phone': '9848011223',
            'preferred_language': 'en'
        })
        self.client.post('/api/queue/call-next')

        # 2. Test Inter-Department Token Transfer to Pharmacy (Counter 3)
        res_transfer = self.client.post('/api/queue/transfer', json={
            'target_counter': 'Counter 3 (Pharmacy)',
            'notes': 'Consultation completed. Forwarded for prescription dispensing.'
        })
        self.assertEqual(res_transfer.status_code, 200)
        d_transfer = res_transfer.get_json()
        self.assertTrue(d_transfer['success'])
        self.assertEqual(d_transfer['target_counter'], 'Counter 3 (Pharmacy)')

        # 3. Test Inbound WhatsApp Bot Command: STATUS
        res_bot_status = self.client.post('/api/whatsapp/webhook', json={
            'phone': '9876543210',
            'message': 'STATUS'
        })
        self.assertEqual(res_bot_status.status_code, 200)
        d_bot = res_bot_status.get_json()
        self.assertIn(d_bot['status'], ('status_replied', 'token_created'))

        print("✓ Test 16 Passed: Public TV Wall Display, Inter-Department Counter Transfer & Inbound Bot Commands verified.")

if __name__ == '__main__':
    unittest.main()
