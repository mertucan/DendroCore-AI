from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from dendrovox import context
from dendrovox.entities import SEED_ENTITIES, build_system_prompt, lines, public_entity, voice_profile
from dendrovox.privacy import hash_session, mask_pii
from dendrovox.reports import dashboard_stats, local_day_range, parse_ts
from dendrovox.storage import MemoryStore


@pytest.mark.parametrize('text, expected', [
    ('Ara beni 0532 123 45 67', 'Ara beni [TELEFON]'),
    ('+90 532 123 4567 numaram', '[TELEFON] numaram'),
    ('05321234567', '[TELEFON]'),
    ('Ev: (0212) 555 44 33', 'Ev: [TELEFON]'),
    ('ayse.k+test@mail.com.tr yaz', '[E-POSTA] yaz'),
    ('TC 12345678901', 'TC [KIMLIK_NO]'),
    ('IBAN TR33 0006 1005 1978 6457 8413 26', 'IBAN [IBAN]'),
    ('Kart 4111 1111 1111 1111', 'Kart [KART_NO]'),
])
def test_mask_pii(text, expected):
    assert mask_pii(text) == expected


@pytest.mark.parametrize('text', ['120 yaşındayım', '1923 yılında dikildim', 'Saat 14:30', 'Nisan 2026', '3 kedi, 25 mesaj'])
def test_mask_pii_keeps_normal_text(text):
    assert mask_pii(text) == text


def test_session_hash_is_salted():
    assert hash_session('abc', 's1') != hash_session('abc', 's2')
    assert len(hash_session('abc', 's1')) == 32 and 'abc' not in hash_session('abc', 's1')


def test_system_prompt():
    tree = SEED_ENTITIES[0]
    prompt = build_system_prompt(tree, 'tr', 'ŞU ANKİ ORTAM: test')
    assert 'Senin adın "Ulu Çınar"' in prompt and 'Platanus orientalis' in prompt and 'Yaşın: 120' in prompt
    assert "- Padişahların parkta gezindiğini hatırlıyorsun." in prompt
    assert 'ŞU ANKİ ORTAM: test' in prompt and 'Her zaman Türkçe konuş' in prompt
    assert 'Her zaman İngilizce (English) konuş' in build_system_prompt(tree, 'en')
    bench = {'name': 'Bank', 'type': 'object', 'location': 'Park'}
    assert 'Gözlemci' in build_system_prompt(bench) and 'Yaşın' not in build_system_prompt(bench)


def test_entity_helpers():
    assert lines('- a\n\n• b \n c') == ['a', 'b', 'c']
    assert voice_profile({'type': 'cat'})['voice'] == 'Puck'
    assert voice_profile({'type': 'tree', 'voice_profile': 'friendly'})['voice'] == 'Leda'
    assert public_entity(SEED_ENTITIES[2], 'en')['description'].startswith("I'm the king")


def test_seasons_and_time_of_day():
    assert [context.season_of(m) for m in (1, 4, 7, 10, 12)] == ['winter', 'spring', 'summer', 'autumn', 'winter']
    assert [context.time_of_day(h) for h in (3, 8, 12, 16, 20, 23)] == ['night', 'morning', 'noon', 'afternoon', 'evening', 'night']


def test_context_with_weather(monkeypatch):
    monkeypatch.setattr(context, 'fetch_weather', lambda lat, lng: {'temperature': 14, 'code': 61, 'wind': 12})
    now = datetime(2026, 10, 25, 8, 15, tzinfo=ZoneInfo('Europe/Istanbul'))
    ctx = context.get_context(SEED_ENTITIES[0], 'en', now=now)
    assert ctx['season_label'] == 'autumn' and ctx['time_label'] == 'morning' and ctx['weather']['label'] == 'light rain'
    prompt = context.context_prompt(ctx)
    assert 'sonbahar (Ekim ayı)' in prompt and 'sabah (saat 08:15)' in prompt and '14°C, hafif yağmurlu' in prompt


def test_context_without_coordinates_or_weather(monkeypatch):
    called = []
    monkeypatch.setattr(context, 'fetch_weather', lambda *a: called.append(a))
    ctx = context.get_context({'name': 'X'}, 'tr')
    assert ctx['weather'] is None and not called
    assert context.get_context(SEED_ENTITIES[0], 'tr', weather_enabled=False)['weather'] is None
    assert 'Hava' not in context.context_prompt(ctx)


def test_weather_fetch_failure_and_cache(monkeypatch):
    context._cache.clear()
    calls = []

    def broken(*args, **kwargs):
        calls.append(1)
        raise httpx.ConnectTimeout('timeout')
    monkeypatch.setattr(context.httpx, 'get', broken)
    assert context.fetch_weather(41.0, 29.0) is None
    assert context.fetch_weather(41.0, 29.0) is None
    assert len(calls) == 1  # hata da önbelleklenir; servis yavaşsa her mesajda beklenmez

    class Ok:
        def raise_for_status(self):
            pass

        def json(self):
            return {'current': {'temperature_2m': 21.6, 'weather_code': 0, 'wind_speed_10m': 5.2}}
    monkeypatch.setattr(context.httpx, 'get', lambda *a, **k: Ok())
    assert context.fetch_weather(40.0, 28.0) == {'temperature': 22, 'code': 0, 'wind': 5}


def test_parse_timestamps():
    assert parse_ts('2026-03-06T12:34:56.12345+00:00') == datetime(2026, 3, 6, 12, 34, 56, 123450, tzinfo=timezone.utc)
    assert parse_ts('2026-03-06T12:34:56Z').tzinfo is not None
    assert parse_ts('2026-03-06T12:34:56').tzinfo == timezone.utc
    assert parse_ts('2026-03-06T15:34:56.1234567+03:00').hour == 15
    assert parse_ts(None) is None


def test_local_day_range_uses_istanbul_time():
    since, until = local_day_range(date(2026, 10, 25), date(2026, 10, 25), 'Europe/Istanbul')
    assert since == '2026-10-24T21:00:00+00:00' and until == '2026-10-25T21:00:00+00:00'
    assert local_day_range(None, None, 'Europe/Istanbul') == (None, None)


def test_dashboard_stats():
    store = MemoryStore()
    for entity_id in ('agac-001', 'agac-001', 'kedi-001'):
        conv = store.create_conversation(entity_id, 'h', 'tr', 'v1')
        msgs = store.add_messages(conv['id'], [('user', 'x', None), ('assistant', 'y', 'm')])
        store.save_feedback(msgs[1]['id'], conv['id'], 1 if entity_id == 'agac-001' else -1, None if entity_id == 'agac-001' else 'unclear')
    stats = dashboard_stats(store, store.list_entities(), 'Europe/Istanbul')
    assert stats['today'] == 3 and stats['week'] == 3 and stats['total_messages'] == 6
    assert stats['by_entity'][0] == {'id': 'agac-001', 'name': 'Ulu Çınar', 'count': 2}
    assert stats['likes'] == 2 and stats['dislikes'] == 1 and stats['like_ratio'] == 67
    assert stats['reasons'] == [{'label': 'Anlaşılmadı', 'count': 1}]
    assert len(stats['days']) == 14 and stats['days'][-1]['count'] == 3


def test_ephemeral_store_expires(monkeypatch):
    from dendrovox import storage
    clock = [1000.0]
    monkeypatch.setattr(storage.time, 'monotonic', lambda: clock[0])
    store = MemoryStore(seed=False, ttl_seconds=60)
    conv = store.create_conversation('agac-001', 'h', 'tr', None)
    clock[0] += 30
    assert store.get_conversation(conv['id'])
    clock[0] += 61
    assert store.get_conversation(conv['id']) is None
