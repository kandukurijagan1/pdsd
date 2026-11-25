"""
SmartQ - Supabase Cloud Synchronization Service
Connects the SmartQ Queue Management Engine to Supabase Cloud Database.
Provides two-way synchronization, real-time live updates, and resilient offline fallback.
"""

import os
import threading
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(DOTENV_PATH)

ENABLE_SUPABASE = os.getenv('ENABLE_SUPABASE', 'True').lower() in ('true', '1', 'yes')
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip()
SUPABASE_PUBLISHABLE_KEY = os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip()
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY', '').strip()

# Initialize Supabase Client
supabase_client = None
SUPABASE_INITIALIZED = False
SUPABASE_LAST_ERROR = None

if ENABLE_SUPABASE and SUPABASE_URL and (SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY):
    try:
        from supabase import create_client, Client
        active_key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
        supabase_client: Client = create_client(SUPABASE_URL, active_key)
        SUPABASE_INITIALIZED = True
        print(f"[Supabase] Connected to {SUPABASE_URL}")
    except Exception as e:
        SUPABASE_LAST_ERROR = str(e)
        print(f"[Supabase] Initialization error: {e}")

def get_supabase():
    """Return active Supabase client instance or None."""
    global supabase_client
    return supabase_client if SUPABASE_INITIALIZED else None

def check_supabase_connection():
    """
    Test live connectivity to Supabase and check if database tables exist.
    """
    client = get_supabase()
    if not client:
        return {
            'connected': False,
            'enabled': ENABLE_SUPABASE,
            'url': SUPABASE_URL or None,
            'error': SUPABASE_LAST_ERROR or 'Supabase credentials not configured',
            'tables_ready': False,
            'existing_tables': [],
            'missing_tables': ['customers', 'tokens', 'settings', 'events', 'notification_outbox']
        }

    expected_tables = ['customers', 'tokens', 'settings', 'events', 'notification_outbox']
    existing_tables = []
    missing_tables = []

    for tbl in expected_tables:
        try:
            # Probe table with limit 1
            client.table(tbl).select('id', count='exact').limit(1).execute()
            existing_tables.append(tbl)
        except Exception as e:
            err_msg = str(e)
            if 'PGRST205' in err_msg or 'Could not find the table' in err_msg:
                missing_tables.append(tbl)
            else:
                # Other error (e.g. settings uses 'key' instead of 'id')
                if tbl == 'settings':
                    try:
                        client.table('settings').select('key').limit(1).execute()
                        existing_tables.append('settings')
                    except Exception:
                        missing_tables.append('settings')
                else:
                    missing_tables.append(tbl)

    tables_ready = len(missing_tables) == 0

    return {
        'connected': True,
        'enabled': True,
        'url': SUPABASE_URL,
        'has_secret_key': bool(SUPABASE_SECRET_KEY),
        'tables_ready': tables_ready,
        'existing_tables': existing_tables,
        'missing_tables': missing_tables,
        'message': 'All tables synced and ready.' if tables_ready else f"Missing tables: {', '.join(missing_tables)}. Please run supabase_schema.sql in SQL Editor."
    }

def _clean_val(v):
    """Format value for JSON/Supabase serialization."""
    if isinstance(v, datetime):
        return v.isoformat()
    return v

def _run_in_background(func, *args, **kwargs):
    """Execute non-blocking cloud synchronization."""
    thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()

def sync_customer_to_supabase(cust_id, name, phone, email='', lang='en', reason=''):
    """Mirror customer record to Supabase."""
    client = get_supabase()
    if not client:
        return

    def _sync():
        try:
            payload = {
                'id': cust_id,
                'name': name,
                'phone': phone,
                'email': email,
                'preferred_language': lang,
                'priority_reason': reason,
                'created_at': datetime.now().isoformat()
            }
            client.table('customers').upsert(payload).execute()
            print(f"[Supabase] Synced customer #{cust_id} ({name})")
        except Exception as e:
            print(f"[Supabase] Customer sync notice: {e}")

    _run_in_background(_sync)

def sync_token_to_supabase(token_data):
    """Mirror token creation or status update to Supabase."""
    client = get_supabase()
    if not client:
        return

    def _sync():
        try:
            payload = {
                'id': token_data.get('id'),
                'token_no': token_data.get('token_no'),
                'customer_id': token_data.get('customer_id'),
                'status': token_data.get('status', 'WAITING'),
                'is_priority': 1 if token_data.get('is_priority') else 0,
                'source': token_data.get('source', 'kiosk'),
                'counter': token_data.get('counter', 'Counter 1'),
                'called_at': _clean_val(token_data.get('called_at')),
                'completed_at': _clean_val(token_data.get('completed_at')),
                'alert_5_ahead_sent': 1 if token_data.get('alert_5_ahead_sent') else 0,
                'diagnosis': token_data.get('diagnosis'),
                'prescription_json': token_data.get('prescription_json'),
                'doctor_name': token_data.get('doctor_name'),
                'doctor_notes': token_data.get('doctor_notes')
            }
            # Remove keys with None if inserting new row so defaults apply
            clean_payload = {k: v for k, v in payload.items() if v is not None}
            client.table('tokens').upsert(clean_payload, on_conflict='token_no').execute()
            print(f"[Supabase] Synced token {token_data.get('token_no')} (status: {token_data.get('status')})")
        except Exception as e:
            print(f"[Supabase] Token sync notice: {e}")

    _run_in_background(_sync)

def sync_event_to_supabase(token_id, event_type, language='en', message=''):
    """Mirror queue event to Supabase."""
    client = get_supabase()
    if not client:
        return

    def _sync():
        try:
            payload = {
                'token_id': token_id,
                'event_type': event_type,
                'language': language,
                'message': message,
                'created_at': datetime.now().isoformat()
            }
            client.table('events').insert(payload).execute()
        except Exception as e:
            pass

    _run_in_background(_sync)

def sync_outbox_to_supabase(token_id, phone, message_text, event_type, status='SENT'):
    """Mirror notification outbox entry to Supabase."""
    client = get_supabase()
    if not client:
        return

    def _sync():
        try:
            payload = {
                'token_id': token_id,
                'phone': phone,
                'message_text': message_text,
                'channel': 'WHATSAPP',
                'event_type': event_type,
                'status': status,
                'created_at': datetime.now().isoformat()
            }
            client.table('notification_outbox').insert(payload).execute()
        except Exception as e:
            pass

    _run_in_background(_sync)

def sync_full_database_to_supabase(sqlite_conn):
    """
    Perform a complete sync of all SQLite data to Supabase.
    Useful when connecting Supabase for the first time or performing manual sync.
    """
    client = get_supabase()
    if not client:
        return {'success': False, 'message': 'Supabase client is not connected'}

    cur = sqlite_conn.cursor()
    stats = {'customers': 0, 'tokens': 0, 'events': 0, 'settings': 0}

    # 1. Sync Customers
    try:
        cur.execute("SELECT * FROM customers")
        for row in cur.fetchall():
            d = dict(row)
            payload = {
                'id': d['id'],
                'name': d.get('name'),
                'phone': d.get('phone'),
                'email': d.get('email'),
                'preferred_language': d.get('preferred_language', 'en'),
                'priority_reason': d.get('priority_reason'),
                'created_at': _clean_val(d.get('created_at'))
            }
            client.table('customers').upsert(payload).execute()
            stats['customers'] += 1
    except Exception as e:
        print(f"[Supabase Full Sync] Customers error: {e}")

    # 2. Sync Tokens
    try:
        cur.execute("SELECT * FROM tokens")
        for row in cur.fetchall():
            d = dict(row)
            payload = {
                'id': d['id'],
                'token_no': d['token_no'],
                'customer_id': d.get('customer_id'),
                'status': d.get('status', 'WAITING'),
                'is_priority': d.get('is_priority', 0),
                'source': d.get('source', 'kiosk'),
                'counter': d.get('counter', 'Counter 1'),
                'called_at': _clean_val(d.get('called_at')),
                'completed_at': _clean_val(d.get('completed_at')),
                'alert_5_ahead_sent': d.get('alert_5_ahead_sent', 0),
                'diagnosis': d.get('diagnosis'),
                'prescription_json': d.get('prescription_json'),
                'doctor_name': d.get('doctor_name'),
                'doctor_notes': d.get('doctor_notes')
            }
            client.table('tokens').upsert(payload, on_conflict='token_no').execute()
            stats['tokens'] += 1
    except Exception as e:
        print(f"[Supabase Full Sync] Tokens error: {e}")

    # 3. Sync Settings
    try:
        cur.execute("SELECT * FROM settings")
        for row in cur.fetchall():
            d = dict(row)
            client.table('settings').upsert({'key': d['key'], 'value': d['value']}).execute()
            stats['settings'] += 1
    except Exception as e:
        print(f"[Supabase Full Sync] Settings error: {e}")

    return {
        'success': True,
        'message': f"Synced {stats['customers']} customers, {stats['tokens']} tokens, and {stats['settings']} settings to Supabase.",
        'stats': stats
    }


def sync_from_supabase_to_local_db(db_path=None):
    """
    Pulls all tokens and customers from Supabase Cloud down into the local SQLite database,
    ensuring 100% real-time dynamic parity between GitHub Pages and localhost.
    """
    client = get_supabase()
    if not client:
        return {'success': False, 'error': 'Supabase not connected'}

    if db_path is None:
        db_path = os.path.join(BASE_DIR, 'smartq.db')

    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # 1. Fetch customers from Supabase Cloud
        res_cust = client.table('customers').select('*').execute()
        if res_cust and res_cust.data:
            for c in res_cust.data:
                cur.execute("""
                    INSERT INTO customers (id, name, phone, email, preferred_language, priority_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name,
                        phone=excluded.phone,
                        email=excluded.email,
                        preferred_language=excluded.preferred_language,
                        priority_reason=excluded.priority_reason
                """, (c.get('id'), c.get('name'), c.get('phone'), c.get('email'), c.get('preferred_language', 'en'), c.get('priority_reason')))

        # 2. Fetch tokens from Supabase Cloud
        res_tok = client.table('tokens').select('*').order('id', desc=False).execute()
        if res_tok and res_tok.data:
            for t in res_tok.data:
                # Format token_no to pure digits
                raw_tok = str(t.get('token_no', ''))
                digits = ''.join(ch for ch in raw_tok if ch.isdigit())
                clean_tok = str(int(digits)) if digits else raw_tok

                cur.execute("""
                    INSERT INTO tokens (id, token_no, customer_id, status, is_priority, source, counter, called_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        token_no=excluded.token_no,
                        customer_id=excluded.customer_id,
                        status=excluded.status,
                        is_priority=excluded.is_priority,
                        source=excluded.source,
                        counter=excluded.counter,
                        called_at=excluded.called_at,
                        completed_at=excluded.completed_at
                """, (t.get('id'), clean_tok, t.get('customer_id'), t.get('status', 'WAITING'), t.get('is_priority', 0), t.get('source', 'kiosk'), t.get('counter', 'Counter 1'), t.get('called_at'), t.get('completed_at')))

        conn.commit()
        conn.close()
        print(f"[Supabase Sync Down] Successfully synchronized {len(res_tok.data)} tokens to local database.")
        return {'success': True, 'count': len(res_tok.data)}
    except Exception as e:
        print(f"[Supabase Sync Down] Error: {e}")
        return {'success': False, 'error': str(e)}

