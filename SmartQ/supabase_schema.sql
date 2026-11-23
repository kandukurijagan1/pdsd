-- =====================================================================
-- SmartQ - Supabase Database Schema Migration
-- Principles of Digital Systems and Design (PDSD)
-- Project: https://mnsfeojsbzomvhcuiaur.supabase.co
-- =====================================================================

-- 1. Customers Table
CREATE TABLE IF NOT EXISTS public.customers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    phone TEXT,
    email TEXT,
    preferred_language TEXT DEFAULT 'en',
    priority_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Tokens Table
CREATE TABLE IF NOT EXISTS public.tokens (
    id BIGSERIAL PRIMARY KEY,
    token_no TEXT UNIQUE NOT NULL,
    customer_id BIGINT REFERENCES public.customers(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'WAITING',
    is_priority INTEGER DEFAULT 0,
    source TEXT NOT NULL,
    counter TEXT DEFAULT 'Counter 1',
    created_at TIMESTAMPTZ DEFAULT now(),
    called_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    alert_5_ahead_sent INTEGER DEFAULT 0,
    diagnosis TEXT,
    prescription_json TEXT,
    doctor_name TEXT,
    doctor_notes TEXT
);

-- Indexes for lightning-fast queries
CREATE INDEX IF NOT EXISTS idx_tokens_status ON public.tokens(status);
CREATE INDEX IF NOT EXISTS idx_tokens_token_no ON public.tokens(token_no);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON public.customers(phone);

-- 3. Settings Table
CREATE TABLE IF NOT EXISTS public.settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Seed default settings
INSERT INTO public.settings (key, value)
VALUES 
    ('counter_name', 'Counter 1'),
    ('priority_mode', 'priority_first'),
    ('organization_name', 'SmartQ Service Center'),
    ('default_language', 'en'),
    ('hardware_connected', 'true')
ON CONFLICT (key) DO NOTHING;

-- 4. Events Log Table
CREATE TABLE IF NOT EXISTS public.events (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT REFERENCES public.tokens(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    language TEXT DEFAULT 'en',
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Notification Outbox (WhatsApp / SMS)
CREATE TABLE IF NOT EXISTS public.notification_outbox (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT,
    phone TEXT,
    message_text TEXT,
    channel TEXT DEFAULT 'WHATSAPP',
    event_type TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- =====================================================================
-- Row Level Security (RLS) & Access Policies
-- Enables public read/write while maintaining security
-- =====================================================================

ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_outbox ENABLE ROW LEVEL SECURITY;

-- Allow public and service role access for SmartQ operations
DROP POLICY IF EXISTS "SmartQ Customers Public Access" ON public.customers;
CREATE POLICY "SmartQ Customers Public Access" ON public.customers FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "SmartQ Tokens Public Access" ON public.tokens;
CREATE POLICY "SmartQ Tokens Public Access" ON public.tokens FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "SmartQ Settings Public Access" ON public.settings;
CREATE POLICY "SmartQ Settings Public Access" ON public.settings FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "SmartQ Events Public Access" ON public.events;
CREATE POLICY "SmartQ Events Public Access" ON public.events FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "SmartQ Outbox Public Access" ON public.notification_outbox;
CREATE POLICY "SmartQ Outbox Public Access" ON public.notification_outbox FOR ALL USING (true) WITH CHECK (true);

-- Enable Supabase Realtime for live queue synchronization
ALTER PUBLICATION supabase_realtime ADD TABLE public.tokens;
