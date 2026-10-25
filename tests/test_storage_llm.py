import io
import wave
from types import SimpleNamespace

import pytest

from dendrovox import storage
from dendrovox.llm import ContentBlocked, GeminiEngine, LLMUnavailable, pcm_to_wav
from dendrovox.storage import MemoryStore, Repository, SupabaseStore, build_repository, jwt_role

ANON_JWT = 'x.eyJyb2xlIjoiYW5vbiJ9.y'             # {"role":"anon"}
SERVICE_JWT = 'x.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.y'  # {"role":"service_role"}


# ── Supabase deposu ──

def test_supabase_store_flow(fake_supabase):
    store = SupabaseStore(fake_supabase)
    store.check_schema()
    store.seed_if_empty()
    assert [e['id'] for e in store.list_entities()] == ['agac-001', 'cicek-001', 'kedi-001']
    assert store.next_entity_id('tree') == 'agac-002' and store.next_entity_id('object') == 'nesne-001'
    store.seed_if_empty()
    assert len(fake_supabase.tables['entities']) == 3

    conv = store.create_conversation('agac-001', 'hash', 'tr', 'v1')
    first = store.add_messages(conv['id'], [('user', 'a', None), ('assistant', 'b', 'm')])
    store.add_messages(conv['id'], [('user', 'c', None), ('assistant', 'd', 'm')])
    assert [m['content'] for m in store.get_messages(conv['id'])] == ['a', 'b', 'c', 'd']
    assert [m['position'] for m in store.get_messages(conv['id'])] == [0, 1, 2, 3]
    assert store.get_conversation(conv['id'])['message_count'] == 4

    store.save_feedback(first[1]['id'], conv['id'], 1, None)
    store.save_feedback(first[1]['id'], conv['id'], -1, 'unclear')
    feedback = store.feedback_for([conv['id']])
    assert len(feedback) == 1 and feedback[0]['rating'] == -1

    rows, total = store.query_conversations(entity_id='agac-001', limit=10)
    assert total == 1 and rows[0]['id'] == conv['id']
    assert store.count_totals() == (1, 4)
    store.complete_conversation(conv['id'])
    assert store.get_conversation(conv['id'])['is_completed'] is True
    assert store.delete_conversation(conv['id']) is True


def test_supabase_entity_update_keeps_created_at(fake_supabase):
    store = SupabaseStore(fake_supabase)
    store.seed_if_empty()
    created = fake_supabase.tables['entities'][0]['created_at']
    entity = store.get_entity('agac-001')
    entity['name'] = 'Yeni Ad'
    store.save_entity(entity)
    row = next(r for r in fake_supabase.tables['entities'] if r['id'] == 'agac-001')
    assert row['name'] == 'Yeni Ad' and row['created_at'] == created


def test_supabase_paginates_past_1000_rows(fake_supabase, monkeypatch):
    monkeypatch.setattr(storage, 'PAGE_SIZE', 3)
    monkeypatch.setattr(storage, 'IN_CHUNK', 2)
    store = SupabaseStore(fake_supabase)
    ids = [store.create_conversation('agac-001', f'h{i}', 'tr', 'v1')['id'] for i in range(7)]
    rows, total = store.query_conversations()
    assert total == 7 and len(rows) == 7
    for conv_id in ids:
        store.add_messages(conv_id, [('user', 'x', None)])
    assert len(store.messages_for(ids)) == 7


def test_build_repository_falls_back_safely(monkeypatch):
    assert build_repository({}).warning and not build_repository({}).is_durable
    anon = build_repository({'SUPABASE_URL': 'https://x.supabase.co', 'SUPABASE_KEY': ANON_JWT})
    assert 'yetkisiz' in anon.warning and isinstance(anon.persistent, MemoryStore)

    import supabase
    monkeypatch.setattr(supabase, 'create_client', lambda url, key: (_ for _ in ()).throw(RuntimeError('no table')))
    broken = build_repository({'SUPABASE_URL': 'https://x.supabase.co', 'SUPABASE_KEY': SERVICE_JWT})
    assert 'supabase_setup.sql' in broken.warning


def test_jwt_role():
    assert jwt_role(ANON_JWT) == 'anon' and jwt_role(SERVICE_JWT) == 'service_role'
    assert jwt_role('sb_secret_abc') == 'service_role' and jwt_role('sb_publishable_abc') == 'anon'
    assert jwt_role('garbage') is None and jwt_role(None) is None


def test_repository_routes_by_consent():
    repo = Repository(MemoryStore())
    kept = repo.create_conversation('agac-001', 'h', 'tr', True, 'v1')
    temp = repo.create_conversation('agac-001', 'h', 'tr', False, 'v1')
    repo.add_messages(temp, [('user', 'gizli', None)])
    assert repo.persistent.get_conversation(kept['id']) and not repo.persistent.get_conversation(temp['id'])
    assert repo.get_conversation(temp['id'])['consent_version'] is None
    assert repo.persistent.count_totals() == (1, 0)


# ── Gemini motoru ──

class APIError(Exception):
    def __init__(self, code):
        super().__init__(f'{code} error')
        self.code = code


class FakeModels:
    def __init__(self, script):
        self.script = script  # model adı -> sırayla yanıt/hata listesi
        self.calls = []

    def generate_content_stream(self, model, contents, config):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        def stream():
            for item in outcome:
                if isinstance(item, Exception):
                    raise item
                yield SimpleNamespace(text=item)
        return stream()

    def generate_content(self, model, contents, config):
        self.calls.append((model, bool(config.speech_config)))
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        part = SimpleNamespace(inline_data=SimpleNamespace(data=outcome, mime_type='audio/L16;codec=pcm;rate=24000'))
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


def make_engine(script, models=('m1', 'm2'), tts=('t1', 't2')):
    engine = GeminiEngine('test-key', models, tts, max_retries=2, retry_delay=0.01, sleep=lambda s: None)
    engine.client = SimpleNamespace(models=FakeModels(script))
    return engine


def run(engine):
    return list(engine.stream_reply('sistem', [{'role': 'user', 'content': 'a'}, {'role': 'assistant', 'content': 'b'}], 'c'))


def test_stream_success():
    engine = make_engine({'m1': [['Mer', 'haba']]})
    assert run(engine) == [('delta', 'Mer'), ('delta', 'haba'), ('model', 'm1')]


def test_transient_errors_are_retried():
    engine = make_engine({'m1': [APIError(503), APIError(503), ['ok']]})
    assert run(engine)[-1] == ('model', 'm1')
    assert engine.client.models.calls == ['m1', 'm1', 'm1']


def test_quota_switches_to_next_model():
    engine = make_engine({'m1': [APIError(429)], 'm2': [['yedek']]})
    assert run(engine) == [('delta', 'yedek'), ('model', 'm2')]


def test_all_models_failing():
    engine = make_engine({'m1': [APIError(404)], 'm2': [APIError(500), APIError(500), APIError(500)]})
    with pytest.raises(LLMUnavailable):
        run(engine)


def test_empty_reply_is_blocked():
    with pytest.raises(ContentBlocked):
        run(make_engine({'m1': [['', '']]}))


def test_error_mid_stream_keeps_partial_reply():
    engine = make_engine({'m1': [['Yarım', APIError(503)]]})
    assert run(engine) == [('delta', 'Yarım'), ('model', 'm1')]


def test_tts_converts_pcm_and_caches():
    pcm = b'\x00\x01' * 2400
    engine = make_engine({'t1': [pcm]})
    audio = engine.synthesize('Merhaba', 'Leda', 'sıcak')
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getframerate() == 24000 and wav.getnchannels() == 1 and wav.readframes(10_000) == pcm
    assert engine.synthesize('Merhaba', 'Leda', 'sıcak') == audio
    assert engine.client.models.calls == [('t1', True)]


def test_tts_retries_without_voice_then_next_model():
    engine = make_engine({'t1': [APIError(400), APIError(429)], 't2': [b'\x00\x00']})
    assert engine.synthesize('x', 'BilinmeyenSes', 'stil')
    assert engine.client.models.calls == [('t1', True), ('t1', False), ('t2', True)]
    engine.client.models.script['t2'].append(b'\x00\x00')
    engine.synthesize('başka', 'Leda', 'stil')
    assert engine.client.models.calls[-1] == ('t2', True)  # çalışan model hatırlanır


def test_tts_unavailable():
    engine = make_engine({'t1': [APIError(429)], 't2': [APIError(404)]})
    with pytest.raises(LLMUnavailable):
        engine.synthesize('x', 'Leda', 'stil')


def test_pcm_to_wav_header():
    assert pcm_to_wav(b'\x00\x00', 16000)[:4] == b'RIFF'
