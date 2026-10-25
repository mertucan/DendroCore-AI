import re

import pytest

from dendrovox.routes.pages import CHAT_JS_STRINGS
from tests import i18n_keys

PAGES = ['/', '/story', '/how-it-works', '/features', '/faq', '/explore', '/chat/agac-001', '/chat/kedi-001', '/chat/cicek-001']


@pytest.mark.parametrize('lang', ['tr', 'en'])
def test_all_pages_render(client, lang):
    client.get(f'/lang/{lang}')
    for url in PAGES:
        response = client.get(url)
        assert response.status_code == 200, url
        assert f'lang="{lang}"' in response.get_data(as_text=True)


def test_english_content(client):
    client.get('/lang/en')
    assert 'Who Would You Like to Talk To?' in client.get('/explore').get_data(as_text=True)
    chat_page = client.get('/chat/kedi-001').get_data(as_text=True)
    assert 'Before we start' in chat_page and 'coolest cat' in chat_page
    assert 'favourite food?' in chat_page  # karaktere özel İngilizce öneriler


def test_language_via_query_and_header(client):
    assert 'Who Would You Like' in client.get('/explore?lang=en').get_data(as_text=True)
    assert 'Who Would You Like' in client.get('/explore', headers={'Accept-Language': 'en-US,en;q=0.9'}).get_data(as_text=True)
    assert 'Kiminle Konuşmak' in client.get('/explore', headers={'Accept-Language': 'de'}).get_data(as_text=True)


def test_language_switch_is_safe(client):
    response = client.get('/lang/en?next=/faq')
    assert response.headers['Location'] == '/faq' and 'dendrovox-lang=en' in response.headers['Set-Cookie']
    for target in ('//kotu.com', 'https://kotu.com', '/\\kotu.com'):
        assert client.get(f'/lang/en?next={target}').headers['Location'] == '/'
    assert 'Set-Cookie' not in client.get('/lang/de').headers or 'dendrovox-lang=de' not in client.get('/lang/de').headers.get('Set-Cookie', '')


def test_not_found_pages(client):
    assert client.get('/chat/yok-001').status_code == 404
    assert client.get('/chat/<script>').status_code == 404
    assert client.get('/olmayan-sayfa').status_code == 404
    assert client.get('/api/olmayan').json['code'] == 'not_found'


def test_security_headers(client):
    response = client.get('/')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert 'Access-Control-Allow-Origin' not in response.headers
    cookie = response.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie and 'SameSite=Lax' in cookie


def test_chat_page_contains_consent_and_accessibility(client):
    page = client.get('/chat/agac-001').get_data(as_text=True)
    assert 'role="dialog"' in page and 'aria-modal="true"' in page
    assert 'Kayıt olmadan sohbet et' in page
    assert 'id="sr-announcer"' in page and 'aria-pressed' in page


def test_explore_lists_entities_from_store(client, repo):
    entity = repo.get_entity('cicek-001')
    entity['name'] = 'Lale Teyze'
    repo.save_entity(entity)
    assert 'Lale Teyze' in client.get('/explore').get_data(as_text=True)


def test_faq_shows_configured_limit(make_app):
    client = make_app(CHAT_LIMIT=7).test_client()
    assert '7 mesaj hakkınız' in client.get('/faq').get_data(as_text=True)


def test_every_string_has_english_translation():
    translations = i18n_keys.load('en')
    missing = [k for k in i18n_keys.all_keys() if k not in translations]
    assert not missing, missing
    placeholders = re.compile(r'\{\w+\}')
    for key in i18n_keys.all_keys():
        assert set(placeholders.findall(key)) == set(placeholders.findall(translations[key])), key


def test_chat_js_strings_are_registered():
    unknown = [k for k in i18n_keys.js_keys() if k not in CHAT_JS_STRINGS]
    assert not unknown, unknown
