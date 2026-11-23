"""
SmartQ - Comprehensive Demo Data Seed Script
Generates 28 realistic patient queue records covering:
- 15 COMPLETED consultations with full diagnoses, structured prescriptions, and doctor notes
- 1 CALLED (actively serving) token at Counter 1
- 1 SKIPPED token
- 11 WAITING tokens with mixed Priority Care (Senior Citizens, Pregnancy), Languages (Telugu/English), and Channels (Voice Kiosk, QR Scan, Reception)
- Synchronizes all data to both local SQLite database and Supabase Cloud.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smartq.db')
sys.path.append(BASE_DIR)

# Doctors
DOC_SHARMA = "Dr. K. Sharma (Consultant Physician)"
DOC_ANANYA = "Dr. P. Ananya (General Medicine)"
DOC_RAO = "Dr. R. V. Rao (Senior Cardiologist & Diabetologist)"

# Prescription Templates
RX_VIRAL_FEVER = json.dumps([
    {"name": "Dolo 650mg (Paracetamol)", "dosage": "1-0-1", "duration": "5 days", "notes": "After meals"},
    {"name": "Pantoprazole 40mg (Pan-40)", "dosage": "1-0-0", "duration": "5 days", "notes": "Morning empty stomach"},
    {"name": "Cetirizine 10mg", "dosage": "0-0-1", "duration": "5 days", "notes": "Bedtime"}
])

RX_DIABETES = json.dumps([
    {"name": "Metformin 500mg (Glyciphage)", "dosage": "1-0-1", "duration": "30 days", "notes": "With meals"},
    {"name": "Glimepiride 1mg", "dosage": "1-0-0", "duration": "30 days", "notes": "Before breakfast"},
    {"name": "Vitamin B12 & Alpha Lipoic Acid", "dosage": "0-1-0", "duration": "30 days", "notes": "After lunch"}
])

RX_PHARYNGITIS = json.dumps([
    {"name": "Amoxicillin + Clavulanic Acid 625mg", "dosage": "1-0-1", "duration": "5 days", "notes": "After meals"},
    {"name": "Benadryl Cough Syrup (10ml)", "dosage": "1-1-1", "duration": "5 days", "notes": "Post meals"},
    {"name": "Salt water gargles 3x daily", "dosage": "SOS", "duration": "5 days", "notes": "Warm water"}
])

RX_HYPERTENSION = json.dumps([
    {"name": "Telmisartan 40mg (Telma-40)", "dosage": "1-0-0", "duration": "30 days", "notes": "Morning after breakfast"},
    {"name": "Amlodipine 5mg", "dosage": "0-0-1", "duration": "30 days", "notes": "Night before sleep"},
    {"name": "Low Sodium Diet & Daily 30min Walking", "dosage": "Lifestyle", "duration": "Ongoing", "notes": "Salt < 5g/day"}
])

RX_GASTRITIS = json.dumps([
    {"name": "Rabeprazole 20mg + Domperidone 30mg", "dosage": "1-0-0", "duration": "14 days", "notes": "30 mins before breakfast"},
    {"name": "Gelusil Antacid Syrup (15ml)", "dosage": "1-1-1", "duration": "7 days", "notes": "After meals & bedtime"}
])

RX_ANTENATAL = json.dumps([
    {"name": "Ferrous Ascorbate 100mg + Folic Acid", "dosage": "0-1-0", "duration": "30 days", "notes": "After lunch with lemon water"},
    {"name": "Calcium Carbonate 500mg + Vitamin D3", "dosage": "1-0-0", "duration": "30 days", "notes": "Morning with milk"},
    {"name": "Ultrasound Anomaly Scan scheduled", "dosage": "Checkup", "duration": "Week 20", "notes": "Radiology Department"}
])

RX_ALLERGY = json.dumps([
    {"name": "Montelukast 10mg + Levocetirizine 5mg", "dosage": "0-0-1", "duration": "10 days", "notes": "At bedtime"},
    {"name": "Fluticasone Furoate Nasal Spray", "dosage": "1 spray each nostril", "duration": "14 days", "notes": "Morning"}
])

RX_ARTHRITIS = json.dumps([
    {"name": "Paracetamol 1000mg Sustained Release", "dosage": "1-0-1", "duration": "10 days", "notes": "After food"},
    {"name": "Diacerein 50mg + Glucosamine 750mg", "dosage": "1-0-0", "duration": "30 days", "notes": "After breakfast"},
    {"name": "Volini Pain Relief Gel", "dosage": "Apply 2x daily", "duration": "10 days", "notes": "Gentle local application"}
])

RX_BACKPAIN = json.dumps([
    {"name": "Aceclofenac 100mg + Thiocolchicoside 4mg", "dosage": "1-0-1", "duration": "5 days", "notes": "After food"},
    {"name": "Pantoprazole 40mg", "dosage": "1-0-0", "duration": "5 days", "notes": "Empty stomach"},
    {"name": "Physiotherapy core strengthening", "dosage": "Daily", "duration": "2 weeks", "notes": "Avoid heavy lifting"}
])

RX_ANEMIA = json.dumps([
    {"name": "Ferrous Fumarate 150mg + Zinc + Folic Acid", "dosage": "1-0-1", "duration": "60 days", "notes": "After meals"},
    {"name": "Vitamin C 500mg Chewable (Limcee)", "dosage": "0-1-0", "duration": "60 days", "notes": "Mid-day chewable"}
])

RX_GASTRO = json.dumps([
    {"name": "Ofloxacin 200mg + Ornidazole 500mg", "dosage": "1-0-1", "duration": "3 days", "notes": "After food"},
    {"name": "Electral ORS (1 sachet in 1 Litre boiled water)", "dosage": "Ad libitum", "duration": "3 days", "notes": "Sip frequently"},
    {"name": "Racecadotril 100mg (Redotil)", "dosage": "1-1-1", "duration": "3 days", "notes": "Before food"}
])

RX_VERTIGO = json.dumps([
    {"name": "Betahistine 16mg (Vertin-16)", "dosage": "1-0-1", "duration": "7 days", "notes": "After meals"},
    {"name": "Propranolol 20mg (Ciplar)", "dosage": "1-0-0", "duration": "14 days", "notes": "Morning"}
])

RX_HEADACHE = json.dumps([
    {"name": "Naproxen 250mg + Domperidone 10mg", "dosage": "1-0-0 (SOS)", "duration": "As needed", "notes": "At onset of headache"},
    {"name": "Magnesium Glycinate 250mg", "dosage": "0-0-1", "duration": "30 days", "notes": "Bedtime"}
])

RX_BRONCHITIS = json.dumps([
    {"name": "Azithromycin 500mg (Azithral)", "dosage": "1-0-0", "duration": "5 days", "notes": "1 hour before meals"},
    {"name": "Levosalbutamol + Budesonide Respules", "dosage": "1 neb 2x daily", "duration": "5 days", "notes": "Nebulization"},
    {"name": "Ambroxol Cough Syrup 10ml", "dosage": "1-1-1", "duration": "5 days", "notes": "Warm water after dose"}
])

RX_DERMATITIS = json.dumps([
    {"name": "Desloratadine 5mg", "dosage": "0-0-1", "duration": "10 days", "notes": "Night"},
    {"name": "Hydrocortisone 1% Cream", "dosage": "Apply 2x daily", "duration": "7 days", "notes": "Thin layer on affected patch"},
    {"name": "Calamine Soothing Lotion", "dosage": "Apply 3x daily", "duration": "14 days", "notes": "External use"}
])


# 28 Sample Patients (15 Completed, 1 Called, 1 Skipped, 11 Waiting)
SAMPLE_DATA = [
    # 1. Completed
    {
        "token_no": "A001", "name": "Ramesh Kumar", "phone": "9876543210", "email": "ramesh.k@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 420, "dur_min": 12,
        "doctor": DOC_SHARMA, "diagnosis": "Seasonal Viral Pyrexia & Mild Pharyngitis", "rx": RX_VIRAL_FEVER,
        "notes": "Patient advised 3 days bed rest and adequate fluid intake. Review if temperature > 101F."
    },
    {
        "token_no": "A002", "name": "Lakshmi Devi", "phone": "9848012345", "email": "lakshmi.d@yahoo.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Senior Citizen (72 yrs)", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 395, "dur_min": 14,
        "doctor": DOC_SHARMA, "diagnosis": "Type-2 Diabetes Routine Follow-up & Glycemic Review", "rx": RX_DIABETES,
        "notes": "Fasting blood sugar 132 mg/dL. HbA1c 6.9%. Medication continued with dietary counseling."
    },
    {
        "token_no": "A003", "name": "Sai Krishna", "phone": "9949023456", "email": "saikrishna@outlook.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 370, "dur_min": 10,
        "doctor": DOC_ANANYA, "diagnosis": "Acute Streptococcal Pharyngitis & Cough", "rx": RX_PHARYNGITIS,
        "notes": "Throat swab clear. Warm saline gargles recommended."
    },
    {
        "token_no": "A004", "name": "Sunita Sharma", "phone": "9811234567", "email": "sunita.sharma@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 345, "dur_min": 11,
        "doctor": DOC_SHARMA, "diagnosis": "Essential Hypertension Stage-1 Monitoring", "rx": RX_HYPERTENSION,
        "notes": "BP: 138/88 mmHg. Advised salt restriction and regular aerobic walking."
    },
    {
        "token_no": "A005", "name": "Venkatesh Babu", "phone": "8367047947", "email": "venkatesh.babu@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 320, "dur_min": 13,
        "doctor": DOC_RAO, "diagnosis": "Gastroesophageal Reflux Disease (GERD) & Dyspepsia", "rx": RX_GASTRITIS,
        "notes": "Avoid late night meals and oily food. Follow up after 2 weeks."
    },
    {
        "token_no": "A006", "name": "Pooja Reddy", "phone": "9703456789", "email": "pooja.reddy@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Pregnancy Care (2nd Trimester)", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 290, "dur_min": 16,
        "doctor": DOC_ANANYA, "diagnosis": "Routine Antenatal Assessment (G1P0 - 22 Weeks)", "rx": RX_ANTENATAL,
        "notes": "Fetal heart rate 144 bpm normal. Blood pressure normal. Anomaly scan scheduled."
    },
    {
        "token_no": "A007", "name": "Murugan Pandian", "phone": "9885123456", "email": "murugan.p@gmail.com",
        "lang": "ta", "is_priority": 0, "priority_reason": "", "source": "manual", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 260, "dur_min": 9,
        "doctor": DOC_SHARMA, "diagnosis": "Allergic Rhinosinusitis & Sneezing Spells", "rx": RX_ALLERGY,
        "notes": "Avoid exposure to dust and cold air. Steam inhalation twice daily."
    },
    {
        "token_no": "A008", "name": "Anasuya Devi", "phone": "9440123456", "email": "anasuya.d@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Senior Citizen (80 yrs)", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 235, "dur_min": 15,
        "doctor": DOC_RAO, "diagnosis": "Bilateral Knee Osteoarthritis - Grade 2", "rx": RX_ARTHRITIS,
        "notes": "Quadriceps isometric exercises demonstrated. Use knee support while walking."
    },
    {
        "token_no": "A009", "name": "Rajesh Kannan", "phone": "9841234567", "email": "rajesh.k@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 205, "dur_min": 12,
        "doctor": DOC_SHARMA, "diagnosis": "Acute Lumbar Muscular Spasm / Strain", "rx": RX_BACKPAIN,
        "notes": "Ergonomic chair posture advised. Lumbo-sacral belt recommended during long travel."
    },
    {
        "token_no": "A010", "name": "Sangeetha Kumari", "phone": "9121234567", "email": "sangeetha.k@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 180, "dur_min": 11,
        "doctor": DOC_ANANYA, "diagnosis": "Microcytic Hypochromic Anemia (Hb: 9.8 g/dL)", "rx": RX_ANEMIA,
        "notes": "Iron-rich diet encouraged (spinach, dates, pomegranate). Repeat CBC after 1 month."
    },
    {
        "token_no": "A011", "name": "David Christopher", "phone": "9849123456", "email": "david.c@yahoo.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 155, "dur_min": 10,
        "doctor": DOC_SHARMA, "diagnosis": "Acute Bacterial Gastroenteritis & Mild Dehydration", "rx": RX_GASTRO,
        "notes": "ORS hydration therapy initiated. Avoid outside food."
    },
    {
        "token_no": "A012", "name": "Padmavati Rao", "phone": "9490234567", "email": "padma.rao@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Senior Citizen (69 yrs)", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 130, "dur_min": 14,
        "doctor": DOC_RAO, "diagnosis": "Benign Paroxysmal Positional Vertigo (BPPV)", "rx": RX_VERTIGO,
        "notes": "Epley maneuver performed. Advised slow postural transitions."
    },
    {
        "token_no": "A013", "name": "Anand Varma", "phone": "9618123456", "email": "anand.v@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "manual", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 105, "dur_min": 9,
        "doctor": DOC_ANANYA, "diagnosis": "Episodic Tension Type Headache & Eye Strain", "rx": RX_HEADACHE,
        "notes": "Refraction examination advised. Screen time limits recommended."
    },
    {
        "token_no": "A014", "name": "Bhanu Prakash", "phone": "9550123456", "email": "bhanu.p@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "COMPLETED",
        "counter": "Counter 1", "offset_min": 80, "dur_min": 12,
        "doctor": DOC_SHARMA, "diagnosis": "Acute Tracheobronchitis with Wheezing", "rx": RX_BRONCHITIS,
        "notes": "Inhaler technique demonstrated. Keep away from smoke and dust."
    },
    {
        "token_no": "A015", "name": "Divya Nair", "phone": "9745123456", "email": "divya.nair@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "COMPLETED",
        "counter": "Counter 2", "offset_min": 55, "dur_min": 10,
        "doctor": DOC_ANANYA, "diagnosis": "Allergic Contact Dermatitis (Forearm Patch)", "rx": RX_DERMATITIS,
        "notes": "Avoid suspect synthetic detergents. Keep skin moisturized."
    },

    # 2. Currently Serving (CALLED)
    {
        "token_no": "A016", "name": "Sunitha Murthy", "phone": "9848022334", "email": "sunitha.m@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "CALLED",
        "counter": "Counter 1", "offset_min": 6, "dur_min": None,
        "doctor": DOC_SHARMA, "diagnosis": None, "rx": None, "notes": None
    },

    # 3. Skipped
    {
        "token_no": "A017", "name": "Harish Chandra", "phone": "9989012345", "email": "harish.c@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "SKIPPED",
        "counter": "Counter 1", "offset_min": 25, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": "Patient did not respond to 3 repeated audio calls."
    },

    # 4. Active Waiting Queue (11 Tokens)
    {
        "token_no": "A018", "name": "Venkateswara Rao", "phone": "9440987654", "email": "v.rao@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Senior Citizen (76 yrs)", "source": "voice", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 22, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A019", "name": "Swapna Priya", "phone": "9849554433", "email": "swapna.p@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Pregnancy Care (3rd Trimester)", "source": "qr", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 19, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A020", "name": "K.K", "phone": "8367047947", "email": "kk.user@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 17, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A021", "name": "Selvamani Natarajan", "phone": "9949112233", "email": "selvamani.n@gmail.com",
        "lang": "ta", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 15, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A022", "name": "Lakshmi Narayana", "phone": "9440156789", "email": "l.narayana@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 13, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A023", "name": "Mohammed Farooq", "phone": "9885012345", "email": "farooq.m@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "manual", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 11, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A024", "name": "Sridevi Kalyani", "phone": "9121098765", "email": "sridevi.k@gmail.com",
        "lang": "te", "is_priority": 1, "priority_reason": "Senior Citizen (71 yrs)", "source": "voice", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 9, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A025", "name": "Senthil Kumar", "phone": "9841023456", "email": "senthil.k@gmail.com",
        "lang": "ta", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 7, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A026", "name": "Anitha Devi", "phone": "9490123456", "email": "anitha.d@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "voice", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 5, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A027", "name": "Kavitha Reddy", "phone": "9849988776", "email": "kavitha.r@gmail.com",
        "lang": "te", "is_priority": 0, "priority_reason": "", "source": "qr", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 3, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    },
    {
        "token_no": "A028", "name": "Vijay Kumar", "phone": "9701234567", "email": "vijay.kumar@gmail.com",
        "lang": "en", "is_priority": 0, "priority_reason": "", "source": "manual", "status": "WAITING",
        "counter": "Counter 1", "offset_min": 1, "dur_min": None,
        "doctor": None, "diagnosis": None, "rx": None, "notes": None
    }
]


def seed_database():
    print("=" * 65)
    print("🌱 SmartQ Database Seeder - Generating 28 Realistic Queue Records")
    print("=" * 65)

    now = datetime.now()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Clear existing sample tables
    print("[1/5] Clearing prior records from local SQLite...")
    cur.execute("DELETE FROM notification_outbox")
    cur.execute("DELETE FROM events")
    cur.execute("DELETE FROM tokens")
    cur.execute("DELETE FROM customers")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('customers', 'tokens', 'events', 'notification_outbox')")
    conn.commit()

    # 2. Insert records into SQLite
    print("[2/5] Inserting 28 customers and queue tokens...")
    supabase_customers = []
    supabase_tokens = []

    for idx, item in enumerate(SAMPLE_DATA, start=1):
        # Timestamps
        created_time = (now - timedelta(minutes=item['offset_min'])).strftime('%Y-%m-%d %H:%M:%S')
        called_time = None
        completed_time = None

        if item['status'] == 'COMPLETED':
            called_time = (now - timedelta(minutes=item['offset_min'] - 2)).strftime('%Y-%m-%d %H:%M:%S')
            completed_time = (now - timedelta(minutes=item['offset_min'] - item['dur_min'])).strftime('%Y-%m-%d %H:%M:%S')
        elif item['status'] == 'CALLED':
            called_time = (now - timedelta(minutes=item['offset_min'])).strftime('%Y-%m-%d %H:%M:%S')
        elif item['status'] == 'SKIPPED':
            called_time = (now - timedelta(minutes=item['offset_min'])).strftime('%Y-%m-%d %H:%M:%S')

        # Customer row
        cur.execute("""
            INSERT INTO customers (id, name, phone, email, preferred_language, priority_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (idx, item['name'], item['phone'], item['email'], item['lang'], item['priority_reason'], created_time))

        # Token row
        cur.execute("""
            INSERT INTO tokens (
                id, token_no, customer_id, status, is_priority, source, counter,
                created_at, called_at, completed_at, alert_5_ahead_sent,
                diagnosis, prescription_json, doctor_name, doctor_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            idx, item['token_no'], idx, item['status'], item['is_priority'], item['source'], item['counter'],
            created_time, called_time, completed_time, 1 if item['status'] in ('COMPLETED', 'CALLED') else 0,
            item['diagnosis'], item['rx'], item['doctor'], item['notes']
        ))

        # Event log
        cur.execute("""
            INSERT INTO events (token_id, event_type, language, message, created_at)
            VALUES (?, 'TOKEN_CREATED', ?, ?, ?)
        """, (idx, item['lang'], f"Token {item['token_no']} generated for {item['name']}", created_time))

        if called_time:
            cur.execute("""
                INSERT INTO events (token_id, event_type, language, message, created_at)
                VALUES (?, 'TOKEN_CALLED', ?, ?, ?)
            """, (idx, item['lang'], f"Token {item['token_no']} called to {item['counter']}", called_time))

        if completed_time:
            cur.execute("""
                INSERT INTO events (token_id, event_type, language, message, created_at)
                VALUES (?, 'TOKEN_COMPLETED', ?, ?, ?)
            """, (idx, item['lang'], f"Token {item['token_no']} consultation completed by {item['doctor']}", completed_time))

        # Outbox row
        cur.execute("""
            INSERT INTO notification_outbox (token_id, phone, message_text, channel, event_type, status, created_at)
            VALUES (?, ?, ?, 'WHATSAPP', 'REGISTRATION', 'SENT', ?)
        """, (idx, item['phone'], f"SmartQ Token Pass #{item['token_no']} for {item['name']}", created_time))

        # Supabase payload
        supabase_customers.append({
            'id': idx,
            'name': item['name'],
            'phone': item['phone'],
            'email': item['email'],
            'preferred_language': item['lang'],
            'priority_reason': item['priority_reason'],
            'created_at': created_time
        })

        supabase_tokens.append({
            'id': idx,
            'token_no': item['token_no'],
            'customer_id': idx,
            'status': item['status'],
            'is_priority': item['is_priority'],
            'source': item['source'],
            'counter': item['counter'],
            'created_at': created_time,
            'called_at': called_time,
            'completed_at': completed_time,
            'alert_5_ahead_sent': 1 if item['status'] in ('COMPLETED', 'CALLED') else 0,
            'diagnosis': item['diagnosis'],
            'prescription_json': item['rx'],
            'doctor_name': item['doctor'],
            'doctor_notes': item['notes']
        })

    # Update sequence in settings
    cur.execute("UPDATE settings SET value = '29' WHERE key = 'next_token_seq'")
    conn.commit()
    conn.close()
    print("   [OK] Local SQLite successfully populated.")

    # 3. Synchronize to Supabase Cloud
    print("[3/5] Mirroring 28 records to Supabase Cloud...")
    try:
        from supabase_service import get_supabase
        sb = get_supabase()
        if sb:
            # Clean child tables first to avoid foreign key conflicts
            try:
                sb.table('events').delete().neq('id', 0).execute()
                sb.table('notification_outbox').delete().neq('id', 0).execute()
                sb.table('tokens').delete().neq('id', 0).execute()
                sb.table('customers').delete().neq('id', 0).execute()
            except Exception as e:
                print(f"   [!] Pre-clean notice: {e}")

            # Batch upsert customers
            res_cust = sb.table('customers').upsert(supabase_customers).execute()
            print(f"   [OK] Supabase: {len(res_cust.data)} customer rows synced.")

            # Batch upsert tokens
            res_tok = sb.table('tokens').upsert(supabase_tokens, on_conflict='token_no').execute()
            print(f"   [OK] Supabase: {len(res_tok.data)} token rows synced.")
        else:
            print("   [!] Supabase client not available, skipping cloud sync.")
    except Exception as e:
        print(f"   [!] Supabase sync note: {e}")

    # 4. Summary Statistics
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT status, count(*) FROM tokens GROUP BY status")
    counts = dict(cur.fetchall())
    conn.close()

    print("[4/5] Queue Verification:")
    print(f"   Total Generated : {len(SAMPLE_DATA)}")
    print(f"   COMPLETED       : {counts.get('COMPLETED', 0)} (Consulted earlier today)")
    print(f"   CALLED          : {counts.get('CALLED', 0)} (Currently serving: A016 at Counter 1)")
    print(f"   SKIPPED         : {counts.get('SKIPPED', 0)}")
    print(f"   WAITING         : {counts.get('WAITING', 0)} (Live queue ready for staff)")
    print(f"   Next Token Seq  : A029")
    print("[5/5] All operations completed successfully! 🎉")
    print("=" * 65)

if __name__ == '__main__':
    seed_database()
