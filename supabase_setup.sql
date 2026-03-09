-- ═══════════════════════════════════════════════════════════════
-- DendroVox - Supabase Veritabanı Kurulumu
-- Bu SQL güvenle tekrar çalıştırılabilir (idempotent).
-- ═══════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────
-- 1) Tablolar
-- ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('tree', 'cat', 'flower', 'object')),
    species TEXT,
    age_years INTEGER,
    location TEXT,
    description TEXT,
    personality TEXT,
    backstory TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    entity_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    is_completed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL CHECK (char_length(content) <= 5000),
    created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ───────────────────────────────────────────
-- 2) Indexler
-- ───────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_conversations_entity_id ON conversations(entity_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_started_at ON conversations(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON conversation_messages(created_at);


-- ───────────────────────────────────────────
-- 3) Row Level Security
-- ───────────────────────────────────────────

ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;

-- Önce mevcut policy'leri temizle, sonra yeniden oluştur
DROP POLICY IF EXISTS "entities_anon_select" ON entities;
DROP POLICY IF EXISTS "entities_anon_insert" ON entities;
DROP POLICY IF EXISTS "conversations_anon_insert" ON conversations;
DROP POLICY IF EXISTS "conversations_anon_select" ON conversations;
DROP POLICY IF EXISTS "conversations_anon_update" ON conversations;
DROP POLICY IF EXISTS "messages_anon_insert" ON conversation_messages;
DROP POLICY IF EXISTS "messages_anon_select" ON conversation_messages;

-- entities
CREATE POLICY "entities_anon_select" ON entities FOR SELECT TO anon USING (true);
CREATE POLICY "entities_anon_insert" ON entities FOR INSERT TO anon WITH CHECK (true);

-- conversations
CREATE POLICY "conversations_anon_insert" ON conversations FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "conversations_anon_select" ON conversations FOR SELECT TO anon USING (true);
CREATE POLICY "conversations_anon_update" ON conversations FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- conversation_messages
CREATE POLICY "messages_anon_insert" ON conversation_messages FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "messages_anon_select" ON conversation_messages FOR SELECT TO anon USING (true);

-- DELETE politikası YOK = anon key ile silme yasak
-- service_role key tüm işlemleri yapabilir (admin panel için)
