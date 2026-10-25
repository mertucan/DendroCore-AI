import json
import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from dendrovox import create_app  # noqa: E402
from dendrovox.llm import ContentBlocked, LLMUnavailable  # noqa: E402
from dendrovox.storage import MemoryStore, Repository  # noqa: E402

ADMIN_PASSWORD = 'dogru-sifre-123'


class FakeEngine:
    """Gemini yerine: çağrıları kaydeder, ayarlanabilir cevap/hata üretir."""

    def __init__(self):
        self.calls = []
        self.tts_calls = []
        self.chunks = ['Merhaba ', 'gezgin!']
        self.error = None
        self.tts_error = None

    def stream_reply(self, system_prompt, history, message):
        self.calls.append({'system_prompt': system_prompt, 'history': [dict(m) for m in history], 'message': message})
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield ('delta', chunk)
        yield ('model', 'fake-model')

    def synthesize(self, text, voice_name, style, lang='tr'):
        self.tts_calls.append({'text': text, 'voice': voice_name, 'style': style, 'lang': lang})
        if self.tts_error:
            raise self.tts_error
        return b'RIFF0000WAVEfake'


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def repo():
    return Repository(MemoryStore())


@pytest.fixture
def make_app(tmp_path, engine, repo):
    def factory(**overrides):
        config = {
            'TESTING': True,
            'SECRET_KEY': 'test-secret',
            'WEATHER_ENABLED': False,
            'RATELIMIT_ENABLED': False,
            'ADMIN_PASSWORD': ADMIN_PASSWORD,
            'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
            'CHAT_LIMIT': 12,
        }
        config.update(overrides)
        return create_app(config, repository=repo, engine=engine)
    return factory


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


def parse_sse(response):
    events = []
    for block in response.get_data(as_text=True).split('\n\n'):
        line = block.strip()
        if line.startswith('data: '):
            events.append(json.loads(line[6:]))
    return events


def chat(client, message='Merhaba', entity_id='agac-001', conversation_id=None, consent=True, **extra):
    body = {'entity_id': entity_id, 'message': message, 'consent': consent, **extra}
    if conversation_id:
        body['conversation_id'] = conversation_id
    return client.post('/api/chat', json=body)


def csrf_of(client):
    with client.session_transaction() as sess:
        return sess.get('_csrf')


def login(client, password=ADMIN_PASSWORD):
    client.get('/admin/giris')
    return client.post('/admin/giris', data={'password': password, 'csrf_token': csrf_of(client)})


@pytest.fixture
def admin(client):
    response = login(client)
    assert response.status_code == 302
    return client


class FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class FakeQuery:
    """Supabase/PostgREST sorgu oluşturucusunun testte kullanılan alt kümesi."""

    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload, self.filters, self.orders = 'select', None, [], []
        self.count, self.window, self.max_rows, self.conflict = None, None, None, None

    def select(self, columns='*', count=None):
        self.op, self.count = 'select', count
        return self

    def insert(self, payload):
        self.op, self.payload = 'insert', payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.op, self.payload, self.conflict = 'upsert', payload, on_conflict
        return self

    def update(self, payload):
        self.op, self.payload = 'update', payload
        return self

    def delete(self):
        self.op = 'delete'
        return self

    def eq(self, col, value):
        self.filters.append(lambda r: r.get(col) == value)
        return self

    def gte(self, col, value):
        self.filters.append(lambda r: (r.get(col) or '') >= value)
        return self

    def lt(self, col, value):
        self.filters.append(lambda r: (r.get(col) or '') < value)
        return self

    def like(self, col, pattern):
        prefix = pattern.rstrip('%')
        self.filters.append(lambda r: str(r.get(col, '')).startswith(prefix))
        return self

    def in_(self, col, values):
        values = set(values)
        self.filters.append(lambda r: r.get(col) in values)
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def range(self, start, end):
        self.window = (start, end)
        return self

    def limit(self, n):
        self.max_rows = n
        return self

    def execute(self):
        self.db.calls.append((self.table, self.op))
        rows = self.db.tables.setdefault(self.table, [])
        if self.op in ('insert', 'upsert'):
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            key = self.conflict or self.db.keys.get(self.table, 'id')
            saved = []
            for item in items:
                item = dict(item)
                existing = next((r for r in rows if r.get(key) == item.get(key)), None)
                if existing and self.op == 'upsert':
                    existing.update(item)
                    saved.append(dict(existing))
                else:
                    # Sütun varsayılanları (DEFAULT NOW()) yalnızca yeni satırda uygulanır
                    item.setdefault('created_at', self.db.now())
                    if self.table == 'conversations':
                        item.setdefault('started_at', self.db.now())
                    rows.append(item)
                    saved.append(dict(item))
            return FakeResult(saved)
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == 'update':
            for row in matched:
                row.update(self.payload)
            return FakeResult([dict(r) for r in matched])
        if self.op == 'delete':
            self.db.tables[self.table] = [r for r in rows if r not in matched]
            return FakeResult([dict(r) for r in matched])
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r: (r.get(col) is None, r.get(col) or 0 if isinstance(r.get(col), (int, float)) else r.get(col) or ''), reverse=desc)
        total = len(matched)
        if self.window:
            matched = matched[self.window[0]:self.window[1] + 1]
        if self.max_rows is not None:
            matched = matched[:self.max_rows]
        return FakeResult([dict(r) for r in matched], total if self.count else None)


class FakeSupabase:
    def __init__(self):
        self.tables = {}
        self.calls = []
        self.keys = {'message_feedback': 'message_id'}
        self._tick = 0

    def now(self):
        self._tick += 1
        return f'2026-10-25T10:{self._tick // 60:02d}:{self._tick % 60:02d}.000000+00:00'

    def table(self, name):
        return FakeQuery(self, name)


@pytest.fixture
def fake_supabase():
    return FakeSupabase()


__all__ = ['FakeEngine', 'ContentBlocked', 'LLMUnavailable', 'parse_sse', 'chat', 'login', 'csrf_of']
