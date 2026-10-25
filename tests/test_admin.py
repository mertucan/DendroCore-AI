import csv
import io
import json
import os

from PIL import Image

from dendrovox.llm import LLMUnavailable
from tests.conftest import chat, csrf_of, login, parse_sse


def entity_form(**overrides):
    data = {
        'type': 'tree', 'name': 'Bilge Meşe', 'species': 'Quercus', 'age_years': '80',
        'location': 'Fethi Paşa Korusu, İstanbul', 'latitude': '41.03', 'longitude': '29.05',
        'description': 'Korunun en sakin ağacıyım.', 'personality': 'Sakin ve düşünceli.',
        'backstory': '- Sincaplarla arkadaş.\n\nBoğazı izler.', 'quick_replies': 'Merhaba\nNasılsın?',
        'voice_profile': 'calm', 'is_active': 'on',
    }
    data.update(overrides)
    return data


def test_requires_login(client):
    for url in ('/admin/', '/admin/karakterler', '/admin/sohbetler', '/admin/disa-aktar', '/admin/disa-aktar/indir'):
        response = client.get(url)
        assert response.status_code == 302 and '/admin/giris' in response.headers['Location']
    assert client.post('/admin/api/ses-onizleme', json={}).status_code == 401


def test_wrong_password_and_csrf(client):
    response = login(client, 'yanlis')
    assert response.status_code == 200 and 'Şifre yanlış' in response.get_data(as_text=True)
    client.get('/admin/giris')
    assert client.post('/admin/giris', data={'password': 'dogru-sifre-123'}).status_code == 400


def test_admin_disabled_without_password(make_app):
    client = make_app(ADMIN_PASSWORD=None).test_client()
    page = client.get('/admin/giris').get_data(as_text=True)
    assert 'henüz açılmamış' in page
    assert login(client, '').status_code == 200
    assert client.get('/admin/').status_code == 302


def test_login_redirects_only_inside_site(client):
    client.get('/admin/giris')
    response = client.post('/admin/giris?next=//kotu-site.com', data={'password': 'dogru-sifre-123', 'csrf_token': csrf_of(client)})
    assert response.headers['Location'] == '/admin/'


def test_dashboard_and_pages_render(admin):
    chat(admin)
    for url in ('/admin/', '/admin/karakterler', '/admin/karakterler/yeni', '/admin/karakterler/agac-001',
                '/admin/sohbetler', '/admin/disa-aktar'):
        response = admin.get(url)
        assert response.status_code == 200, url
        assert response.headers['Cache-Control'] == 'no-store'
    assert 'Hoş geldiniz' in admin.get('/admin/').get_data(as_text=True)


def test_post_without_csrf_rejected(admin):
    assert admin.post('/admin/karakterler/yeni', data=entity_form()).status_code == 400
    assert admin.post('/admin/karakterler/agac-001/durum').status_code == 400


def test_create_entity(admin, repo, engine):
    response = admin.post('/admin/karakterler/yeni', data={**entity_form(), 'csrf_token': csrf_of(admin)})
    assert response.status_code == 302
    entity = repo.get_entity('agac-002')
    assert entity['name'] == 'Bilge Meşe' and entity['age_years'] == 80
    assert entity['backstory'] == 'Sincaplarla arkadaş.\nBoğazı izler.'
    assert entity['quick_replies'] == ['Merhaba', 'Nasılsın?'] and entity['voice_profile'] == 'calm'

    # Yeni karakter hemen sohbet edilebilir ve admin bilgileri prompta girer
    assert admin.get('/chat/agac-002').status_code == 200
    parse_sse(chat(admin, entity_id='agac-002'))
    prompt = engine.calls[-1]['system_prompt']
    assert 'Bilge Meşe' in prompt and '- Boğazı izler.' in prompt and 'Sakin ve düşünceli.' in prompt


def test_create_entity_validation_messages(admin, repo):
    response = admin.post('/admin/karakterler/yeni', data={
        **entity_form(name='', age_years='çok yaşlı', location='', description='', personality='',
                      quick_replies='\n'.join(str(i) for i in range(8)), latitude='abc'),
        'csrf_token': csrf_of(admin)})
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    for text in ('Lütfen karaktere bir isim verin.', 'Yaşı sadece rakamla yazın', 'bulunduğu yeri yazın',
                 'kısa bir tanıtım', 'birkaç kelimeyle', 'En fazla 6 soru', 'Haritadaki konum okunamadı'):
        assert text in page
    assert repo.get_entity('agac-002') is None


def test_photo_upload_strips_metadata(admin, repo, app):
    image = Image.new('RGB', (2400, 1600), (30, 160, 80))
    exif = Image.Exif()
    exif[0x8825] = {2: (41.0, 2.0, 3.0)}  # GPS bilgisi
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', exif=exif)
    buffer.seek(0)
    response = admin.post('/admin/karakterler/yeni', data={
        **entity_form(), 'csrf_token': csrf_of(admin), 'photo': (buffer, 'foto.jpg')},
        content_type='multipart/form-data')
    assert response.status_code == 302
    url = repo.get_entity('agac-002')['image_url']
    assert url.startswith('/uploads/agac-002-')
    path = os.path.join(app.config['UPLOAD_FOLDER'], url.rsplit('/', 1)[1])
    saved = Image.open(path)
    assert max(saved.size) == 1200 and not saved.getexif()
    assert admin.get(url).status_code == 200


def test_photo_upload_rejects_non_images(admin, repo):
    response = admin.post('/admin/karakterler/yeni', data={
        **entity_form(), 'csrf_token': csrf_of(admin), 'photo': (io.BytesIO(b'<script>alert(1)</script>'), 'x.jpg')},
        content_type='multipart/form-data')
    assert response.status_code == 400 and 'fotoğraf olarak açılamadı' in response.get_data(as_text=True)
    assert repo.get_entity('agac-002') is None


def test_edit_and_toggle_entity(admin, repo, client):
    form = entity_form(name='Ulu Çınar Dede', type='cat')  # tür değiştirilemez
    assert admin.post('/admin/karakterler/agac-001', data={**form, 'csrf_token': csrf_of(admin)}).status_code == 302
    entity = repo.get_entity('agac-001')
    assert entity['name'] == 'Ulu Çınar Dede'
    assert admin.post('/admin/karakterler/agac-001/durum', data={'csrf_token': csrf_of(admin)}).status_code == 302
    assert repo.get_entity('agac-001')['is_active'] is False
    assert 'agac-001' not in [e['id'] for e in client.get('/api/entities').json]
    assert admin.get('/admin/karakterler/yok-001').status_code == 404


def test_entity_name_is_escaped_everywhere(admin, repo):
    entity = repo.get_entity('agac-001')
    entity['name'] = '</script><img src=x onerror=alert(1)>'
    repo.save_entity(entity)
    for url in ('/chat/agac-001', '/explore', '/', '/admin/karakterler'):
        page = admin.get(url).get_data(as_text=True)
        assert '<img src=x onerror' not in page, url


def test_conversations_list_detail_delete(admin, repo):
    events = parse_sse(chat(admin, 'Merhaba ağaç'))
    conv_id, message_id = events[0]['conversation_id'], events[-1]['message_id']
    admin.post('/api/feedback', json={'message_id': message_id, 'rating': -1, 'reason': 'unclear'})
    parse_sse(chat(admin, 'Gizli sohbet', consent=False))

    page = admin.get('/admin/sohbetler').get_data(as_text=True)
    assert '1 sohbet bulundu' in page  # rızasız sohbet listede yok
    assert admin.get('/admin/sohbetler?karakter=kedi-001').get_data(as_text=True).count('sohbet bulundu') == 1
    assert '0 sohbet bulundu' in admin.get('/admin/sohbetler?karakter=kedi-001').get_data(as_text=True)
    assert '0 sohbet bulundu' in admin.get('/admin/sohbetler?baslangic=2001-01-01&bitis=2001-01-02').get_data(as_text=True)

    detail = admin.get(f'/admin/sohbetler/{conv_id}').get_data(as_text=True)
    assert 'Merhaba ağaç' in detail and 'Anlaşılmadı' in detail

    assert admin.post(f'/admin/sohbetler/{conv_id}/sil', data={'csrf_token': csrf_of(admin)}).status_code == 302
    assert repo.get_conversation(conv_id) is None
    assert admin.get(f'/admin/sohbetler/{conv_id}').status_code == 404


def test_export_is_anonymous(admin, repo):
    events = parse_sse(chat(admin, '=HYPERLINK("http://kotu") tel 0555 444 33 22'))
    admin.post('/api/feedback', json={'message_id': events[-1]['message_id'], 'rating': 1})
    parse_sse(chat(admin, 'İkinci karakter', entity_id='kedi-001'))
    # Onay ekranı öncesinden kalma eski kayıt
    legacy = repo.persistent.create_conversation('cicek-001', 'eski-oturum', 'tr', None)
    repo.persistent.add_messages(legacy['id'], [('user', 'eski mesaj', None)])

    response = admin.get('/admin/disa-aktar/indir?bicim=csv')
    text = response.get_data(as_text=True)
    assert response.mimetype == 'text/csv' and text.startswith('﻿')
    assert 'attachment' in response.headers['Content-Disposition']
    reader = csv.DictReader(io.StringIO(text.lstrip('﻿')), delimiter=';')
    body = list(reader)
    assert reader.fieldnames[0] == 'katilimci_kodu' and len(body) == 4
    assert {r['katilimci_kodu'] for r in body} == {'K001'}  # aynı tarayıcı = aynı takma kod
    assert {r['sohbet_kodu'] for r in body} == {'S0001', 'S0002'}
    first = body[0]
    assert first['mesaj'].startswith("'=HYPERLINK") and '[TELEFON]' in first['mesaj']
    assert body[1]['begeni'] == '1' and body[0]['begeni'] == ''
    assert 'eski mesaj' not in text
    session_hashes = {c['session_id'] for c in repo.query_conversations()[0]}
    assert not any(h in text for h in session_hashes)

    with_legacy = admin.get('/admin/disa-aktar/indir?bicim=csv&eski=on').get_data(as_text=True)
    assert 'eski mesaj' in with_legacy and 'eski-bilgilendirme' in with_legacy

    data = json.loads(admin.get('/admin/disa-aktar/indir?bicim=json&karakter=kedi-001').get_data(as_text=True))
    assert len(data['conversations']) == 1 and data['conversations'][0]['entity_name'] == 'Tekir'
    assert data['conversations'][0]['messages'][0] == {
        'order': 1, 'role': 'kullanici', 'text': 'İkinci karakter', 'rating': None, 'reason': None, 'model': None,
        'flag': None}


def test_voice_preview(admin, engine):
    headers = {'X-CSRF-Token': csrf_of(admin)}
    response = admin.post('/admin/api/ses-onizleme', json={'voice_profile': 'friendly', 'name': 'Pamuk'}, headers=headers)
    assert response.status_code == 200 and response.mimetype == 'audio/wav'
    assert engine.tts_calls[0]['voice'] == 'Leda' and 'Pamuk' in engine.tts_calls[0]['text']
    assert admin.post('/admin/api/ses-onizleme', json={'voice_profile': 'friendly'}).status_code == 400  # CSRF yok
    assert admin.post('/admin/api/ses-onizleme', json={'voice_profile': 'yok'}, headers=headers).status_code == 400
    engine.tts_error = LLMUnavailable('x')
    fallback = admin.post('/admin/api/ses-onizleme', json={'voice_profile': 'wise'}, headers=headers)
    assert fallback.status_code == 503 and fallback.json['browser']['pitch'] == 0.8


def test_logout(admin):
    assert admin.post('/admin/cikis', data={'csrf_token': csrf_of(admin)}).status_code == 302
    assert admin.get('/admin/').status_code == 302


def test_database_warning_shown(make_app, repo):
    repo.warning = 'Veritabanı bağlı değil.'
    client = make_app().test_client()
    login(client)
    assert 'Teknik bir ayar eksik' in client.get('/admin/').get_data(as_text=True)
