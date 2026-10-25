-- ═══════════════════════════════════════════════════════════════
-- DendroVox - Supabase Veritabanı Kurulumu / Güncellemesi
-- Bu SQL güvenle tekrar çalıştırılabilir (idempotent).
-- Mevcut verileri silmez; eksik sütun ve tabloları ekler.
--
-- ÖNEMLİ: Backend artık service_role (gizli) anahtarla çalışır.
-- .env içine SUPABASE_SERVICE_KEY=... yazın
-- (Supabase > Project Settings > API > service_role).
-- Bu anahtar yalnızca sunucuda durmalı, tarayıcıya asla gönderilmemeli.
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

-- Admin panelinden düzenlenen yeni alanlar
ALTER TABLE entities ADD COLUMN IF NOT EXISTS description_en TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS welcome_message TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS welcome_message_en TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS quick_replies JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS quick_replies_en JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS voice_profile TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
-- Doğrulanmış bilgi kartı ("Biliyor muydun?")
ALTER TABLE entities ADD COLUMN IF NOT EXISTS facts JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE entities ADD COLUMN IF NOT EXISTS facts_en JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    entity_id TEXT NOT NULL,
    session_id TEXT NOT NULL,          -- tarayıcı oturumunun tuzlanmış özeti (açık kimlik değil)
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    is_completed BOOLEAN DEFAULT FALSE
);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS lang TEXT DEFAULT 'tr';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS consent_version TEXT;  -- NULL = onay ekranı öncesi (eski) kayıt
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS message_count INTEGER NOT NULL DEFAULT 0;
-- Araştırma alanları
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ins_pre SMALLINT CHECK (ins_pre BETWEEN 1 AND 7);   -- doğaya yakınlık, sohbet öncesi
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ins_post SMALLINT CHECK (ins_post BETWEEN 1 AND 7); -- doğaya yakınlık, sohbet sonrası
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS visitor_hash TEXT;      -- tekrar gelen ziyaretçi (tuzlanmış özet)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS visit_number INTEGER;   -- ziyaretçinin kaçıncı sohbeti
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS metrics JSONB;          -- isimsiz etkileşim ölçümleri
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS flagged BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS flag_reviewed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS conversation_messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL CHECK (char_length(content) <= 5000),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS position INTEGER;  -- sohbet içindeki sıra
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS model TEXT;        -- cevabı üreten model
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS flag TEXT;         -- uygunsuz içerik kategorisi

-- Cevap başına mini anket
CREATE TABLE IF NOT EXISTS message_feedback (
    message_id UUID PRIMARY KEY REFERENCES conversation_messages(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    reason TEXT CHECK (reason IS NULL OR reason IN ('off_character', 'wrong_info', 'unclear', 'too_long', 'other')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Eski sohbetlerin mesaj sayısını doldur (yalnızca henüz sayılmamış olanlar)
UPDATE conversations c
SET message_count = sub.n
FROM (SELECT conversation_id, COUNT(*)::int AS n FROM conversation_messages GROUP BY conversation_id) sub
WHERE sub.conversation_id = c.id AND c.message_count = 0;


-- ───────────────────────────────────────────
-- 2) Indexler
-- ───────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_conversations_entity_id ON conversations(entity_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_started_at ON conversations(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON conversation_messages(conversation_id, position);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON conversation_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_conversation_id ON message_feedback(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_visitor_hash ON conversations(visitor_hash);
CREATE INDEX IF NOT EXISTS idx_conversations_needs_review ON conversations(flagged, flag_reviewed) WHERE flagged;


-- ───────────────────────────────────────────
-- 3) Row Level Security
-- Herkese açık (anon) anahtarla HİÇBİR işlem yapılamaz.
-- Tüm erişim, sunucudaki service_role anahtarıyla backend üzerinden olur.
-- ───────────────────────────────────────────

ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_feedback ENABLE ROW LEVEL SECURITY;

-- Önceki sürümün herkese açık politikalarını kaldır
DROP POLICY IF EXISTS "entities_anon_select" ON entities;
DROP POLICY IF EXISTS "entities_anon_insert" ON entities;
DROP POLICY IF EXISTS "conversations_anon_insert" ON conversations;
DROP POLICY IF EXISTS "conversations_anon_select" ON conversations;
DROP POLICY IF EXISTS "conversations_anon_update" ON conversations;
DROP POLICY IF EXISTS "messages_anon_insert" ON conversation_messages;
DROP POLICY IF EXISTS "messages_anon_select" ON conversation_messages;

-- Politika olmadığı için anon/authenticated roller tablolara erişemez;
-- service_role RLS'i atlar.
