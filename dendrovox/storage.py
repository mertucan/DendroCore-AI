"""Veri katmanı.

İki arka uç aynı arayüzü uygular:
- SupabaseStore: kalıcı kayıt (araştırma verisi).
- MemoryStore: Supabase yapılandırılmadığında ve testlerde; ayrıca rıza vermeyen
  kullanıcıların sohbetleri için süreli, kalıcı olmayan depo.

Repository ikisini birleştirir: rızalı sohbetler kalıcı depoya, rızasızlar geçici depoya gider.
"""

import copy
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from .entities import ENTITY_TYPES, SEED_ENTITIES, normalize_entity

log = logging.getLogger('dendrovox')

PAGE_SIZE = 1000
IN_CHUNK = 100

# Araştırma alanları (supabase_setup.sql ile eklenir)
CONVERSATION_DEFAULTS = {
    'ins_pre': None,         # sohbet öncesi doğaya yakınlık (1-7)
    'ins_post': None,        # sohbet sonrası doğaya yakınlık (1-7)
    'visitor_hash': None,    # tekrar gelen ziyaretçi için tuzlanmış tarayıcı kodu
    'visit_number': None,    # bu ziyaretçinin kaçıncı sohbeti
    'metrics': None,         # isimsiz etkileşim ölçümleri
    'flagged': False,        # uygunsuz olabilecek mesaj içeriyor
    'flag_reviewed': False,  # admin inceledi
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _next_id(existing_ids, entity_type):
    prefix = ENTITY_TYPES.get(entity_type, ENTITY_TYPES['object'])[0]
    numbers = [int(i.split('-')[1]) for i in existing_ids if i.startswith(prefix + '-') and i.split('-')[1].isdigit()]
    return f'{prefix}-{(max(numbers) + 1) if numbers else 1:03d}'


class MemoryStore:
    def __init__(self, seed=True, ttl_seconds=None):
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        self.entities = {}
        self.conversations = {}
        self.messages = {}       # conversation_id -> [mesaj]
        self.message_index = {}  # mesaj id -> mesaj
        self.feedback = {}       # mesaj id -> geri bildirim
        self._touched = {}
        if seed:
            for entity in SEED_ENTITIES:
                self.save_entity(copy.deepcopy(entity))

    # ── Süre dolumu (yalnızca geçici depo) ──
    def _prune(self):
        if not self.ttl:
            return
        limit = time.monotonic() - self.ttl
        for conv_id in [c for c, t in self._touched.items() if t < limit]:
            self.delete_conversation(conv_id)

    # ── Karakterler ──
    def list_entities(self, include_inactive=False):
        with self._lock:
            items = sorted(self.entities.values(), key=lambda e: (e.get('created_at') or '', e['id']))
            return [copy.deepcopy(e) for e in items if include_inactive or e.get('is_active', True)]

    def get_entity(self, entity_id):
        with self._lock:
            entity = self.entities.get(entity_id)
            return copy.deepcopy(entity) if entity else None

    def next_entity_id(self, entity_type):
        with self._lock:
            return _next_id(self.entities.keys(), entity_type)

    def save_entity(self, entity):
        with self._lock:
            entity = normalize_entity(entity)
            existing = self.entities.get(entity['id'], {})
            entity['created_at'] = existing.get('created_at') or entity.get('created_at') or utcnow()
            entity['updated_at'] = utcnow()
            self.entities[entity['id']] = entity
            return copy.deepcopy(entity)

    # ── Sohbetler ──
    def create_conversation(self, entity_id, session_hash, lang, consent_version, extra=None):
        with self._lock:
            self._prune()
            conv = {
                'id': str(uuid.uuid4()),
                'entity_id': entity_id,
                'session_id': session_hash,
                'lang': lang,
                'consent_version': consent_version,
                'started_at': utcnow(),
                'ended_at': None,
                'is_completed': False,
                'message_count': 0,
                **CONVERSATION_DEFAULTS,
                **(extra or {}),
            }
            self.conversations[conv['id']] = conv
            self.messages[conv['id']] = []
            self._touched[conv['id']] = time.monotonic()
            return dict(conv)

    def get_conversation(self, conversation_id):
        with self._lock:
            self._prune()
            conv = self.conversations.get(conversation_id)
            return dict(conv) if conv else None

    def add_messages(self, conversation_id, items):
        """items: [(role, content, model[, flag])] — sırası korunarak eklenir."""
        with self._lock:
            conv = self.conversations[conversation_id]
            saved = []
            for role, content, model, *rest in items:
                msg = {
                    'id': str(uuid.uuid4()),
                    'conversation_id': conversation_id,
                    'role': role,
                    'content': content,
                    'model': model,
                    'flag': rest[0] if rest else None,
                    'position': conv['message_count'],
                    'created_at': utcnow(),
                }
                conv['message_count'] += 1
                self.messages[conversation_id].append(msg)
                self.message_index[msg['id']] = msg
                saved.append(dict(msg))
            self._touched[conversation_id] = time.monotonic()
            return saved

    def get_messages(self, conversation_id):
        with self._lock:
            return [dict(m) for m in self.messages.get(conversation_id, [])]

    def get_message(self, message_id):
        with self._lock:
            msg = self.message_index.get(message_id)
            return dict(msg) if msg else None

    def complete_conversation(self, conversation_id):
        with self._lock:
            conv = self.conversations.get(conversation_id)
            if conv:
                conv['is_completed'] = True
                conv['ended_at'] = utcnow()

    def update_conversation(self, conversation_id, fields):
        with self._lock:
            conv = self.conversations.get(conversation_id)
            if conv:
                conv.update(fields)

    def count_visitor_conversations(self, visitor_hash):
        with self._lock:
            return sum(1 for c in self.conversations.values() if c.get('visitor_hash') == visitor_hash)

    def save_feedback(self, message_id, conversation_id, rating, reason):
        with self._lock:
            self.feedback[message_id] = {
                'message_id': message_id,
                'conversation_id': conversation_id,
                'rating': rating,
                'reason': reason,
                'created_at': utcnow(),
            }

    def delete_conversation(self, conversation_id):
        with self._lock:
            for msg in self.messages.pop(conversation_id, []):
                self.message_index.pop(msg['id'], None)
                self.feedback.pop(msg['id'], None)
            self._touched.pop(conversation_id, None)
            return self.conversations.pop(conversation_id, None) is not None

    # ── Yönetim / dışa aktarım ──
    def query_conversations(self, entity_id=None, since=None, until=None, limit=None, offset=0, filters=None):
        """Yeniden eskiye sıralı (satırlar, toplam). filters: {sütun: değer} eşitlik koşulları."""
        with self._lock:
            rows = [
                dict(c) for c in self.conversations.values()
                if (not entity_id or c['entity_id'] == entity_id)
                and (not since or c['started_at'] >= since)
                and (not until or c['started_at'] < until)
                and all(c.get(k) == v for k, v in (filters or {}).items())
            ]
            rows.sort(key=lambda c: c['started_at'], reverse=True)
            total = len(rows)
            if limit is not None:
                rows = rows[offset:offset + limit]
            return rows, total

    def messages_for(self, conversation_ids):
        with self._lock:
            return [dict(m) for cid in conversation_ids for m in self.messages.get(cid, [])]

    def feedback_for(self, conversation_ids):
        wanted = set(conversation_ids)
        with self._lock:
            return [dict(f) for f in self.feedback.values() if f['conversation_id'] in wanted]

    def count_totals(self):
        with self._lock:
            return len(self.conversations), sum(len(m) for m in self.messages.values())


class SupabaseStore:
    """Supabase (PostgREST) üzerinden aynı arayüz. Gizli (service_role) anahtar gerektirir."""

    def __init__(self, client):
        self.db = client

    def _all(self, build):
        """1000 satır sınırını aşmak için sayfa sayfa okur."""
        rows, start = [], 0
        while True:
            batch = build().range(start, start + PAGE_SIZE - 1).execute().data or []
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                return rows
            start += PAGE_SIZE

    def check_schema(self):
        """Yeni sütunlar/tablolar yoksa hata fırlatır (supabase_setup.sql çalıştırılmamış demektir)."""
        self.db.table('entities').select('id,voice_profile,is_active,quick_replies,facts,facts_en').limit(1).execute()
        self.db.table('conversations').select(
            'id,lang,consent_version,message_count,' + ','.join(CONVERSATION_DEFAULTS)).limit(1).execute()
        self.db.table('conversation_messages').select('id,position,model,flag').limit(1).execute()
        self.db.table('message_feedback').select('message_id').limit(1).execute()

    # ── Karakterler ──
    def list_entities(self, include_inactive=False):
        def build():
            query = self.db.table('entities').select('*')
            if not include_inactive:
                query = query.eq('is_active', True)
            return query.order('created_at').order('id')
        return [normalize_entity(e) for e in self._all(build)]

    def get_entity(self, entity_id):
        data = self.db.table('entities').select('*').eq('id', entity_id).limit(1).execute().data
        return normalize_entity(data[0]) if data else None

    def next_entity_id(self, entity_type):
        prefix = ENTITY_TYPES.get(entity_type, ENTITY_TYPES['object'])[0]
        data = self.db.table('entities').select('id').like('id', f'{prefix}-%').execute().data or []
        return _next_id([row['id'] for row in data], entity_type)

    def save_entity(self, entity):
        entity = normalize_entity(entity)
        entity.pop('created_at', None)
        entity['updated_at'] = utcnow()
        data = self.db.table('entities').upsert(entity).execute().data
        return normalize_entity(data[0]) if data else entity

    def seed_if_empty(self):
        if not self.db.table('entities').select('id').limit(1).execute().data:
            for entity in SEED_ENTITIES:
                self.save_entity(copy.deepcopy(entity))
            log.info('Supabase: örnek karakterler eklendi.')

    # ── Sohbetler ──
    def create_conversation(self, entity_id, session_hash, lang, consent_version, extra=None):
        conv = {
            'id': str(uuid.uuid4()),
            'entity_id': entity_id,
            'session_id': session_hash,
            'lang': lang,
            'consent_version': consent_version,
            'message_count': 0,
            **(extra or {}),
        }
        data = self.db.table('conversations').insert(conv).execute().data
        return data[0] if data else conv

    def get_conversation(self, conversation_id):
        data = self.db.table('conversations').select('*').eq('id', conversation_id).limit(1).execute().data
        return data[0] if data else None

    def add_messages(self, conversation_id, items):
        conv = self.get_conversation(conversation_id)
        start = conv.get('message_count') or 0
        rows = [
            {
                'id': str(uuid.uuid4()),
                'conversation_id': conversation_id,
                'role': role,
                'content': content[:5000],
                'model': model,
                'flag': rest[0] if rest else None,
                'position': start + i,
            }
            for i, (role, content, model, *rest) in enumerate(items)
        ]
        self.db.table('conversation_messages').insert(rows).execute()
        self.db.table('conversations').update({'message_count': start + len(rows)}).eq('id', conversation_id).execute()
        return rows

    def get_messages(self, conversation_id):
        return self._all(lambda: self.db.table('conversation_messages').select('*')
                         .eq('conversation_id', conversation_id).order('position').order('created_at'))

    def get_message(self, message_id):
        data = self.db.table('conversation_messages').select('*').eq('id', message_id).limit(1).execute().data
        return data[0] if data else None

    def complete_conversation(self, conversation_id):
        self.db.table('conversations').update({'ended_at': utcnow(), 'is_completed': True}) \
            .eq('id', conversation_id).execute()

    def update_conversation(self, conversation_id, fields):
        self.db.table('conversations').update(fields).eq('id', conversation_id).execute()

    def count_visitor_conversations(self, visitor_hash):
        result = self.db.table('conversations').select('id', count='exact').eq('visitor_hash', visitor_hash) \
            .limit(1).execute()
        return result.count or 0

    def save_feedback(self, message_id, conversation_id, rating, reason):
        self.db.table('message_feedback').upsert({
            'message_id': message_id,
            'conversation_id': conversation_id,
            'rating': rating,
            'reason': reason,
            'created_at': utcnow(),
        }, on_conflict='message_id').execute()

    def delete_conversation(self, conversation_id):
        data = self.db.table('conversations').delete().eq('id', conversation_id).execute().data
        return bool(data)

    # ── Yönetim / dışa aktarım ──
    def _conversation_query(self, entity_id, since, until, filters=None, count=None):
        query = self.db.table('conversations').select('*', count=count) if count else self.db.table('conversations').select('*')
        if entity_id:
            query = query.eq('entity_id', entity_id)
        if since:
            query = query.gte('started_at', since)
        if until:
            query = query.lt('started_at', until)
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        return query.order('started_at', desc=True)

    def query_conversations(self, entity_id=None, since=None, until=None, limit=None, offset=0, filters=None):
        if limit is None:
            rows = self._all(lambda: self._conversation_query(entity_id, since, until, filters))
            return rows, len(rows)
        result = self._conversation_query(entity_id, since, until, filters, count='exact') \
            .range(offset, offset + limit - 1).execute()
        return result.data or [], result.count or 0

    def _in_chunks(self, table, column, ids, order=None):
        rows = []
        ids = list(ids)
        for i in range(0, len(ids), IN_CHUNK):
            chunk = ids[i:i + IN_CHUNK]

            def build(chunk=chunk):
                query = self.db.table(table).select('*').in_(column, chunk)
                for col in order or ():
                    query = query.order(col)
                return query
            rows.extend(self._all(build))
        return rows

    def messages_for(self, conversation_ids):
        return self._in_chunks('conversation_messages', 'conversation_id', conversation_ids,
                               order=('conversation_id', 'position', 'created_at'))

    def feedback_for(self, conversation_ids):
        return self._in_chunks('message_feedback', 'conversation_id', conversation_ids)

    def count_totals(self):
        convs = self.db.table('conversations').select('id', count='exact').limit(1).execute()
        msgs = self.db.table('conversation_messages').select('id', count='exact').limit(1).execute()
        return convs.count or 0, msgs.count or 0


class Repository:
    """Kalıcı depo + rızasız sohbetler için geçici bellek deposu."""

    EPHEMERAL_TTL = 2 * 60 * 60

    def __init__(self, persistent, warning=None):
        self.persistent = persistent
        self.ephemeral = MemoryStore(seed=False, ttl_seconds=self.EPHEMERAL_TTL)
        self.warning = warning  # admin panelinde gösterilecek kurulum uyarısı
        self.is_durable = isinstance(persistent, SupabaseStore)

    def __getattr__(self, name):
        # Karakter ve yönetim işlemleri doğrudan kalıcı depoya gider.
        return getattr(self.persistent, name)

    def _store_for(self, conversation):
        return self.persistent if conversation.get('consent') else self.ephemeral

    def create_conversation(self, entity_id, session_hash, lang, consent, consent_version, extra=None):
        """extra (ölçüm, ziyaretçi kodu vb.) yalnızca rızalı sohbetlerde saklanır."""
        if consent:
            conv = self.persistent.create_conversation(entity_id, session_hash, lang, consent_version, extra)
        else:
            conv = self.ephemeral.create_conversation(entity_id, session_hash, lang, None)
        conv['consent'] = bool(consent)
        return conv

    def update_conversation(self, conversation, fields):
        self._store_for(conversation).update_conversation(conversation['id'], fields)

    def get_conversation(self, conversation_id):
        conv = self.ephemeral.get_conversation(conversation_id)
        if conv:
            conv['consent'] = False
            return conv
        conv = self.persistent.get_conversation(conversation_id)
        if conv:
            conv['consent'] = True
        return conv

    def add_messages(self, conversation, items):
        return self._store_for(conversation).add_messages(conversation['id'], items)

    def get_messages(self, conversation):
        return self._store_for(conversation).get_messages(conversation['id'])

    def get_message(self, message_id):
        return self.ephemeral.get_message(message_id) or self.persistent.get_message(message_id)

    def complete_conversation(self, conversation):
        self._store_for(conversation).complete_conversation(conversation['id'])


def jwt_role(key):
    """Supabase anahtarının rolünü (anon / service_role) değeri açığa çıkarmadan bulur."""
    import base64
    import json
    if not key:
        return None
    if key.startswith('sb_secret_'):
        return 'service_role'
    if key.startswith('sb_publishable_'):
        return 'anon'
    try:
        payload = key.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get('role')
    except Exception:
        return None


def build_repository(config):
    url, key = config.get('SUPABASE_URL'), config.get('SUPABASE_KEY')
    if not (url and key):
        log.warning('Supabase yapılandırılmamış: veriler yalnızca bellekte tutulacak.')
        return Repository(MemoryStore(), warning='Veritabanı bağlı değil. Sohbetler sunucu yeniden başlatılınca silinir.')
    role = jwt_role(key)
    if role != 'service_role':
        log.error('SUPABASE_KEY "%s" rolünde. Backend için service_role (gizli) anahtar gerekir.', role)
        return Repository(MemoryStore(), warning=(
            'Veritabanı anahtarı yetkisiz (herkese açık anahtar). .env dosyasına SUPABASE_SERVICE_KEY olarak '
            'Supabase > Project Settings > API > service_role anahtarını yazın. Şimdilik veriler kaydedilmiyor.'))
    try:
        from supabase import create_client
        store = SupabaseStore(create_client(url, key))
        store.check_schema()
        store.seed_if_empty()
        log.info('Supabase bağlantısı hazır.')
        return Repository(store)
    except Exception as error:
        log.error('Supabase kullanılamıyor: %s', error)
        return Repository(MemoryStore(), warning=(
            'Veritabanı tabloları güncel değil. Supabase SQL Editor\'de supabase_setup.sql dosyasını çalıştırın. '
            'Şimdilik veriler kaydedilmiyor.'))
