"""Araştırma özellikleri: ön/son ölçüm, etkileşim ölçümleri, tekrar gelen ziyaretçi,
park rotası, doğrulanmış bilgi kartı ve uygunsuz mesaj işaretleme."""

import csv
import io
import json
import re
import uuid

import pytest

from dendrovox.entities import SEED_ENTITIES, build_system_prompt, distance_m, neighbors, neighbors_prompt
from dendrovox.llm import ContentBlocked
from dendrovox.moderation import moderate
from dendrovox.storage import SupabaseStore
from tests.conftest import chat, csrf_of, login, parse_sse


def start_chat(client, **extra):
    events = parse_sse(chat(client, **extra))
    return events[0]['conversation_id'], events[-1]


# ── Uygunsuz mesaj işaretleme ──

@pytest.mark.parametrize('text, category', [
    ('AMK ne biçim ağaç', 'profanity'),
    ('Sen aptal bir ağaçsın', 'profanity'),
    ('saaalaaak kedi', 'profanity'),
    ('what the fuck', 'profanity'),
    ('seni yakacağım', 'violence'),
    ('Ağacı keseceğim yarın', 'violence'),
    ('k3ndimi öldürmek istiyorum', 'self_harm'),
    ('Bazen ölmek istiyorum', 'self_harm'),
    ('intihar etmeyi düşünüyorum', 'self_harm'),
    ('porno izle', 'sexual'),
])
def test_moderation_flags(text, category):
    assert moderate(text) == category


@pytest.mark.parametrize('text', [
    'Seksen yaşındayım', 'Beni götür', 'Amcam burada', 'Eski bir sikke buldum', 'Shiitake mantarı',
    'Bombastik bir gün', 'Kökünü sulayayım mı?', 'Salata yedim', 'Merhaba, nasılsın?', 'Sıkıntılı bir gün',
])
def test_moderation_avoids_false_positives(text):
    assert moderate(text) is None


def test_flagged_message_is_recorded(client, repo):
    conv_id, done = start_chat(client, message='Sen aptal bir ağaçsın')
    conv = repo.get_conversation(conv_id)
    assert conv['flagged'] is True and conv['flag_reviewed'] is False
    assert repo.get_messages(conv)[0]['flag'] == 'profanity'
    assert done['support'] is False


def test_self_harm_shows_support(client):
    _, done = start_chat(client, message='Bazen ölmek istiyorum')
    assert done['support'] is True


def test_blocked_reply_is_flagged(client, engine, repo):
    engine.error = ContentBlocked()
    conv_id, _ = start_chat(client, message='zararsız görünen soru')
    assert repo.get_messages(repo.get_conversation(conv_id))[0]['flag'] == 'blocked'


def test_unconsented_flags_are_not_persisted(client, repo):
    start_chat(client, message='amk', consent=False)
    assert repo.query_conversations(filters={'flagged': True})[1] == 0


def test_prompt_has_safety_and_fact_rules():
    prompt = build_system_prompt(SEED_ENTITIES[0])
    assert '112' in prompt and 'uydurma' in prompt
    assert 'Kesin bilgiler' in prompt and 'Gövdesinin kabuğu parça parça dökülür' in prompt


# ── Doğaya yakınlık ölçeği ──

def test_pre_measure_and_visitor_are_saved(client, repo):
    visitor = str(uuid.uuid4())
    conv_id, _ = start_chat(client, ins_pre=3, visitor_id=visitor)
    conv = repo.get_conversation(conv_id)
    assert conv['ins_pre'] == 3 and conv['visit_number'] == 1
    assert conv['visitor_hash'] and visitor not in conv['visitor_hash']


@pytest.mark.parametrize('value', [0, 8, '5', 4.5, True, None])
def test_invalid_pre_measure_is_ignored(client, repo, value):
    conv_id, _ = start_chat(client, ins_pre=value)
    assert repo.get_conversation(conv_id)['ins_pre'] is None


def test_no_research_data_without_consent(client, repo):
    conv_id, _ = start_chat(client, consent=False, ins_pre=5, visitor_id=str(uuid.uuid4()))
    conv = repo.get_conversation(conv_id)
    assert conv.get('ins_pre') is None and conv.get('visitor_hash') is None


def test_post_measure(app, client, repo):
    conv_id, _ = start_chat(client)
    post = lambda body, c=client: c.post('/api/survey', json=body)  # noqa: E731
    assert post({'conversation_id': conv_id, 'value': 6}).json == {'ok': True}
    assert repo.get_conversation(conv_id)['ins_post'] == 6
    assert post({'conversation_id': conv_id, 'value': 9}).status_code == 400
    assert post({'conversation_id': conv_id, 'value': 2}, app.test_client()).status_code == 404
    hidden, _ = start_chat(client, consent=False)
    assert post({'conversation_id': hidden, 'value': 2}).json['code'] == 'no_consent'


# ── Tekrar gelen ziyaretçi ──

def test_returning_visitor_across_sessions(app, repo):
    visitor = str(uuid.uuid4())
    first, second = app.test_client(), app.test_client()  # farklı günler / oturumlar
    a, _ = start_chat(first, visitor_id=visitor)
    b, _ = start_chat(second, visitor_id=visitor, entity_id='kedi-001')
    c, _ = start_chat(second, visitor_id=str(uuid.uuid4()))
    conv_a, conv_b, conv_c = (repo.get_conversation(x) for x in (a, b, c))
    assert conv_a['visitor_hash'] == conv_b['visitor_hash'] != conv_c['visitor_hash']
    assert (conv_a['visit_number'], conv_b['visit_number'], conv_c['visit_number']) == (1, 2, 1)
    assert conv_a['session_id'] != conv_b['session_id']


def test_invalid_visitor_id_is_ignored(client, repo):
    conv_id, _ = start_chat(client, visitor_id='<script>')
    assert repo.get_conversation(conv_id)['visitor_hash'] is None


# ── Etkileşim ölçümleri ──

def test_metrics_are_cleaned(app, client, repo):
    conv_id, _ = start_chat(client)
    response = client.post('/api/metrics', json={'conversation_id': conv_id, 'metrics': {
        'visible_ms': 125_000, 'listens': 2, 'typed': -5, 'quick_replies': 10 ** 9, 'auto_read': True,
        'ended': 'finish', 'note': 'adım Ayşe', 'first_message_ms': 'çok', 'facts_opened': True,
    }})
    assert response.json == {'ok': True}
    assert repo.get_conversation(conv_id)['metrics'] == {
        'visible_ms': 125_000, 'listens': 2, 'typed': 0, 'quick_replies': 100, 'auto_read': True, 'ended': 'finish'}
    assert app.test_client().post('/api/metrics', json={'conversation_id': conv_id, 'metrics': {}}).status_code == 400
    assert client.post('/api/metrics', json={'conversation_id': conv_id, 'metrics': 'x'}).status_code == 400


def test_metrics_ignored_without_consent(client, repo):
    conv_id, _ = start_chat(client, consent=False)
    assert client.post('/api/metrics', json={'conversation_id': conv_id, 'metrics': {'listens': 1}}).status_code == 200
    assert repo.get_conversation(conv_id).get('metrics') is None


# ── Park rotası ──

def test_distance_and_neighbors():
    tree, flower, cat = SEED_ENTITIES
    assert 6000 < distance_m(tree, flower) < 8000
    assert distance_m(tree, {'latitude': None, 'longitude': None}) is None
    near = neighbors(tree, SEED_ENTITIES)
    assert [n['id'] for n in near] == ['cicek-001', 'kedi-001']
    assert neighbors_prompt(near) == ''  # 2 km'den uzaktakiler promptta anılmaz


def test_nearby_character_is_mentioned_in_prompt(client, repo, engine):
    bench = dict(SEED_ENTITIES[0], id='nesne-001', name='Yaşlı Bank', type='object', latitude=41.0490, longitude=29.0125)
    repo.save_entity(bench)
    start_chat(client)
    assert 'YAKINDAKİ KOMŞULARIN' in engine.calls[0]['system_prompt'] and 'Yaşlı Bank' in engine.calls[0]['system_prompt']


def chat_config(page_html):
    match = re.search(r'route: (\[.*?\]),\n', page_html)
    return json.loads(match.group(1))


def test_chat_page_includes_route_and_facts(client):
    page = client.get('/chat/agac-001').get_data(as_text=True)
    route = chat_config(page)
    assert [r['id'] for r in route] == ['cicek-001', 'kedi-001'] and route[0]['distance_m'] > 0
    assert 'Doğrulanmış bilgiler' in page and 'Gövdesinin kabuğu' in page
    english = client.get('/chat/agac-001?lang=en').get_data(as_text=True)
    assert 'Verified facts' in english and 'bark peels off' in english


def test_facts_card_hidden_when_empty(client, repo):
    entity = repo.get_entity('kedi-001')
    entity['facts'] = []
    repo.save_entity(entity)
    assert 'id="facts-btn"' not in client.get('/chat/kedi-001').get_data(as_text=True)


# ── Admin ──

def test_admin_facts_field(admin, repo):
    from tests.test_admin import entity_form
    response = admin.post('/admin/karakterler/yeni', data={
        **entity_form(facts='Bu bank 1950 yılında yapıldı.\n- Dökme demirdendir.'), 'csrf_token': csrf_of(admin)})
    assert response.status_code == 302
    assert repo.get_entity('agac-002')['facts'] == ['Bu bank 1950 yılında yapıldı.', 'Dökme demirdendir.']
    too_many = admin.post('/admin/karakterler/yeni', data={
        **entity_form(facts='\n'.join(f'bilgi {i}' for i in range(9))), 'csrf_token': csrf_of(admin)})
    assert too_many.status_code == 400 and 'En fazla 8 bilgi' in too_many.get_data(as_text=True)


def test_admin_review_flow(client, repo):
    flagged, _ = start_chat(client, message='amk')
    start_chat(client, message='Merhaba')
    login(client)
    assert '1 sohbet incelenmeyi bekliyor' in client.get('/admin/').get_data(as_text=True)
    listing = client.get('/admin/sohbetler?incelenecek=on').get_data(as_text=True)
    assert '1 sohbet bulundu' in listing and 'İncelenecek' in listing
    detail = client.get(f'/admin/sohbetler/{flagged}').get_data(as_text=True)
    assert 'Uygunsuz olabilir: Küfür veya hakaret' in detail
    assert client.post(f'/admin/sohbetler/{flagged}/incelendi', data={'csrf_token': csrf_of(client)}).status_code == 302
    assert repo.get_conversation(flagged)['flag_reviewed'] is True
    assert 'incelenmeyi bekliyor' not in client.get('/admin/').get_data(as_text=True)
    assert '0 sohbet bulundu' in client.get('/admin/sohbetler?incelenecek=on').get_data(as_text=True)


def test_admin_research_summary_and_export(app, repo):
    visitor = str(uuid.uuid4())
    first, second = app.test_client(), app.test_client()
    a, _ = start_chat(first, ins_pre=3, visitor_id=visitor)
    first.post('/api/survey', json={'conversation_id': a, 'value': 5})
    first.post('/api/metrics', json={'conversation_id': a, 'metrics': {'visible_ms': 180_000, 'listens': 1, 'ended': 'finish'}})
    b, _ = start_chat(second, ins_pre=4, visitor_id=visitor)
    second.post('/api/survey', json={'conversation_id': b, 'value': 4})
    # Tekrar gelen ziyaretçi farklı günlerde gelmiş olsun
    repo.persistent.update_conversation(a, {'started_at': '2026-10-20T10:00:00+00:00'})

    from dendrovox.reports import research_summary
    summary = research_summary(repo.query_conversations()[0])
    assert summary['pairs'] == 2 and summary['pre_avg'] == 3.5 and summary['post_avg'] == 4.5
    assert summary['change_avg'] == 1.0 and summary['improved'] == 1
    assert summary['visitors'] == 1 and summary['returning'] == 1
    assert summary['avg_minutes'] == 3.0 and summary['listen_share'] == 100

    admin = app.test_client()
    login(admin)
    assert 'Araştırma özeti' in admin.get('/admin/').get_data(as_text=True)
    detail = admin.get(f'/admin/sohbetler/{a}').get_data(as_text=True)
    assert 'Kendisi bitirdi' in detail

    text = admin.get('/admin/disa-aktar/indir?bicim=csv').get_data(as_text=True)
    rows = list(csv.DictReader(io.StringIO(text.lstrip('﻿')), delimiter=';'))
    assert {r['katilimci_kodu'] for r in rows} == {'K001'}  # iki farklı oturum, aynı ziyaretçi
    by_conv = {r['sohbet_kodu']: r for r in rows}
    assert by_conv['S0001']['doga_yakinlik_once'] == '3' and by_conv['S0001']['doga_yakinlik_sonra'] == '5'
    assert by_conv['S0001']['sure_sn'] == '180' and by_conv['S0001']['bitis_sekli'] == 'kendisi bitirdi'
    assert by_conv['S0002']['ziyaret_sirasi'] == '2'
    assert visitor not in text


# ── Supabase deposu ──

def test_supabase_research_fields(fake_supabase):
    store = SupabaseStore(fake_supabase)
    conv = store.create_conversation('agac-001', 'h', 'tr', 'v1', {'visitor_hash': 'v', 'ins_pre': 2})
    store.create_conversation('agac-001', 'h2', 'tr', 'v1', {'visitor_hash': 'v'})
    assert store.count_visitor_conversations('v') == 2
    store.add_messages(conv['id'], [('user', 'amk', None, 'profanity')])
    store.update_conversation(conv['id'], {'flagged': True, 'flag_reviewed': False, 'ins_post': 6})
    rows, total = store.query_conversations(limit=5, filters={'flagged': True, 'flag_reviewed': False})
    assert total == 1 and rows[0]['ins_post'] == 6 and rows[0]['ins_pre'] == 2
    assert store.get_messages(conv['id'])[0]['flag'] == 'profanity'
