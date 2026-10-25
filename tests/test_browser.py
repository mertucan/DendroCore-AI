"""Gerçek tarayıcıda uçtan uca testler (Playwright + yüklü Edge/Chrome).

Çalıştırmak için:  RUN_BROWSER_TESTS=1 python -m pytest tests/test_browser.py
Ekran görüntüleri BROWSER_SHOTS klasörüne (varsa) kaydedilir.
"""

import os
import re
import threading

import pytest

if os.environ.get('RUN_BROWSER_TESTS') != '1':
    pytest.skip('Tarayıcı testleri için RUN_BROWSER_TESTS=1 verin.', allow_module_level=True)

playwright = pytest.importorskip('playwright.sync_api')
from werkzeug.serving import make_server  # noqa: E402

from dendrovox import create_app  # noqa: E402
from dendrovox.llm import pcm_to_wav  # noqa: E402
from dendrovox.storage import MemoryStore, Repository  # noqa: E402
from tests.conftest import ADMIN_PASSWORD, FakeEngine  # noqa: E402

SHOTS = os.environ.get('BROWSER_SHOTS')


class AudioEngine(FakeEngine):
    def synthesize(self, text, voice_name, style, lang='tr'):
        self.tts_calls.append({'text': text, 'voice': voice_name})
        return pcm_to_wav(b'\x00\x00' * 4800)  # 0,2 sn sessizlik


@pytest.fixture(scope='module')
def server(tmp_path_factory):
    repo = Repository(MemoryStore())
    engine = AudioEngine()
    app = create_app({
        'TESTING': True, 'SECRET_KEY': 'browser-test', 'WEATHER_ENABLED': False, 'RATELIMIT_ENABLED': False,
        'ADMIN_PASSWORD': ADMIN_PASSWORD, 'CHAT_LIMIT': 3,
        'UPLOAD_FOLDER': str(tmp_path_factory.mktemp('uploads')),
    }, repository=repo, engine=engine)
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield {'url': f'http://127.0.0.1:{http.server_port}', 'repo': repo, 'engine': engine}
    http.shutdown()


@pytest.fixture(scope='module')
def browser():
    with playwright.sync_playwright() as p:
        channel = os.environ.get('BROWSER_CHANNEL', 'msedge')
        instance = p.chromium.launch(channel=channel, args=['--autoplay-policy=no-user-gesture-required'])
        yield instance
        instance.close()


_font_cache = {}


def _proxy_fonts(route):
    """Bazı ağlarda tarayıcı fonts.gstatic.com'a ulaşamıyor; yazı tipleri Python üzerinden getirilir."""
    import httpx
    url = route.request.url
    try:
        if url not in _font_cache:
            _font_cache[url] = httpx.get(url, timeout=10).content
        route.fulfill(body=_font_cache[url], content_type='font/woff2', headers={'Access-Control-Allow-Origin': '*'})
    except Exception:
        route.abort()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, locale='tr-TR')
    context.route('https://fonts.gstatic.com/**', _proxy_fonts)
    page = context.new_page()
    page.errors = []
    page.on('pageerror', lambda error: page.errors.append(str(error)))
    page.on('console', lambda msg: msg.type == 'error' and page.errors.append(msg.text))
    yield page
    context.close()


def shot(page, name):
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, f'{name}.png'), full_page=True)


def send(page, text):
    """Gönder düğmesi açılınca (karşılama geldikten / cevap bittikten sonra) mesaj yazar."""
    playwright.expect(page.locator('#chat-form button[type="submit"]')).to_be_enabled()
    page.fill('#message-input', text)
    page.keyboard.press('Enter')


def own_errors(page):
    # Dış kaynaklar (harita karoları, yazı tipleri) ağ ortamına bağlıdır; uygulama hatalarına bakılır.
    return [e for e in page.errors if 'Failed to load resource' not in e and 'tailwindcss.com should not be used' not in e]


def test_chat_with_consent_feedback_voice_and_collection(server, page):
    page.goto(server['url'] + '/chat/agac-001')
    modal = page.locator('#consent-modal')
    playwright.expect(modal).to_be_visible()
    shot(page, '01-riza-ekrani')
    page.click('#consent-yes')
    playwright.expect(modal).to_be_hidden()
    playwright.expect(page.locator('#consent-chip')).to_have_text('Kayıt açık')

    # Sohbet öncesi doğaya yakınlık sorusu
    playwright.expect(page.locator('#ins-modal')).to_be_visible()
    playwright.expect(page.locator('#ins-title')).to_have_text('Başlamadan önce tek bir soru')
    shot(page, '01b-olcek')
    page.get_by_role('radio', name='3: Doğaya biraz uzak').click()
    playwright.expect(page.locator('#ins-modal')).to_be_hidden()

    # Karşılama + önerilen sorular
    playwright.expect(page.locator('#messages-container')).to_contain_text('Ulu Çınar')
    quick = page.locator('#quick-replies button').first
    playwright.expect(quick).to_be_visible()
    quick.click()

    playwright.expect(page.locator('#messages-container')).to_contain_text('Merhaba gezgin!')
    playwright.expect(page.locator('#sr-announcer')).to_contain_text('Ulu Çınar diyor ki: Merhaba gezgin!')
    playwright.expect(page.locator('#toast')).to_contain_text('Koleksiyonuna eklendi')
    shot(page, '02-sohbet')

    # Mini anket
    page.get_by_role('button', name='Beğenmedim').click()
    page.get_by_role('button', name='Çok uzun').click()
    playwright.expect(page.locator('#messages-container')).to_contain_text('Teşekkürler!')
    feedback = server['repo'].feedback_for([c['id'] for c in server['repo'].query_conversations()[0]])
    assert any(f['reason'] == 'too_long' for f in feedback)

    # Dinle düğmesi sunucudaki karakter sesini ister
    calls = len(server['engine'].tts_calls)
    page.get_by_role('button', name='Dinle').last.click()
    playwright.expect(page.get_by_role('button', name='Dinle').last).to_be_visible(timeout=5000)
    assert len(server['engine'].tts_calls) == calls + 1

    # Sesli okuma düğmesi kalıcı
    toggle = page.locator('#auto-read-toggle')
    toggle.click()
    playwright.expect(toggle).to_have_attribute('aria-pressed', 'true')
    page.reload()
    playwright.expect(page.locator('#auto-read-toggle')).to_have_attribute('aria-pressed', 'true')
    playwright.expect(page.locator('#consent-modal')).to_be_hidden()  # karar hatırlanır
    page.click('#ins-skip')  # her yeni sohbette ön soru tekrar sorulur, geçilebilir
    playwright.expect(page.locator('#ins-modal')).to_be_hidden()

    # Keşfet sayfasında koleksiyon
    page.goto(server['url'] + '/explore')
    playwright.expect(page.locator('#collection-title')).to_have_text('Filiz · Koleksiyon: 1/3')
    playwright.expect(page.locator('[data-entity="agac-001"] .met-stamp')).to_be_visible()
    playwright.expect(page.locator('[data-entity="kedi-001"] .met-stamp')).to_be_hidden()
    shot(page, '03-kesfet')
    assert not own_errors(page), page.errors


def test_chat_without_consent_and_limit(server, page):
    before = server['repo'].persistent.count_totals()[0]
    page.goto(server['url'] + '/chat/kedi-001')
    page.click('#consent-no')
    playwright.expect(page.locator('#consent-chip')).to_have_text('Kayıt kapalı')
    for i in range(3):
        send(page, f'Mesaj {i}')
        playwright.expect(page.locator('#messages-container')).to_contain_text(f'Mesaj {i}')
        playwright.expect(page.locator('#message-input')).to_be_enabled() if i < 2 else None
        page.wait_for_function('() => !document.querySelector("#typing-indicator:not(.hidden)")')
    playwright.expect(page.locator('#limit-text')).to_have_text('Mesaj limiti doldu')
    playwright.expect(page.locator('#message-input')).to_be_disabled()
    assert page.get_by_role('button', name='Beğendim').count() == 0  # rıza yoksa anket yok
    assert server['repo'].persistent.count_totals()[0] == before
    shot(page, '04-limit')
    assert not own_errors(page), page.errors


def test_consent_can_be_changed(server, page):
    page.goto(server['url'] + '/chat/cicek-001')
    page.click('#consent-no')
    playwright.expect(page.locator('#ins-modal')).to_be_hidden()  # rıza yoksa ölçek sorulmaz
    assert page.evaluate("localStorage.getItem('dendrovox-visitor')") is None
    page.click('#consent-chip')
    playwright.expect(page.locator('#consent-modal')).to_be_visible()
    page.click('#consent-yes')
    assert page.evaluate("localStorage.getItem('dendrovox-visitor')")
    send(page, 'Şimdi kaydedilsin')
    playwright.expect(page.get_by_role('button', name='Beğendim')).to_be_visible()
    rows, _ = server['repo'].query_conversations(entity_id='cicek-001')
    assert rows and rows[0]['consent_version']


def test_english_chat(server, page):
    page.goto(server['url'] + '/lang/en?next=/chat/kedi-001')
    playwright.expect(page.locator('#consent-title')).to_have_text('Before we start')
    page.click('#consent-yes')
    playwright.expect(page.locator('#ins-title')).to_have_text('One question before we start')
    page.click('#ins-skip')
    playwright.expect(page.locator('#messages-container')).to_contain_text('coolest cat')
    playwright.expect(page.locator('#consent-chip')).to_have_text('Recording on')


def test_facts_finish_post_survey_and_route(server, page):
    page.goto(server['url'] + '/chat/kedi-001')
    page.click('#consent-yes')
    page.get_by_role('radio', name='2: Doğaya çok uzak').click()
    send(page, 'Merhaba Tekir')

    # "Biliyor muydun?" kartı ve bilgi kartı
    playwright.expect(page.locator('#messages-container')).to_contain_text('Biliyor muydun?')
    page.click('#facts-btn')
    playwright.expect(page.locator('#facts-sheet')).to_be_visible()
    playwright.expect(page.locator('#facts-sheet')).to_contain_text('12-16 saat uyur')
    shot(page, '11-bilgi-karti')
    page.click('#facts-close')
    playwright.expect(page.locator('#facts-sheet')).to_be_hidden()

    # Sohbeti bitir → son soru → park rotası
    page.click('#finish-btn')
    playwright.expect(page.locator('#ins-title')).to_have_text('Son olarak tek bir soru')
    page.get_by_role('radio', name='6: Doğaya çok yakın').click()
    route = page.get_by_role('region', name='Sıradaki durak')
    playwright.expect(route).to_be_visible()
    playwright.expect(route).to_contain_text('Lale Hanım')
    playwright.expect(route).to_contain_text('Başka bir parkta')
    playwright.expect(route.get_by_role('link', name='Yol tarifi').first).to_have_attribute('href', re.compile('openstreetmap.org/directions'))
    playwright.expect(page.locator('#message-input')).to_be_disabled()
    shot(page, '12-park-rotasi')

    rows, _ = server['repo'].query_conversations(entity_id='kedi-001', filters={'ins_post': 6})
    assert rows and rows[0]['ins_pre'] == 2 and rows[0]['visitor_hash'] and rows[0]['visit_number'] == 1
    deadline = 0
    while not (rows[0].get('metrics') or {}).get('ended') and deadline < 20:
        page.wait_for_timeout(100)
        rows, _ = server['repo'].query_conversations(entity_id='kedi-001', filters={'ins_post': 6})
        deadline += 1
    metrics = rows[0]['metrics']
    assert metrics['ended'] == 'finish' and metrics['typed'] == 1 and metrics['facts_opened'] == 1
    assert 'first_message_ms' in metrics and metrics['visible_ms'] > 0
    assert not own_errors(page), page.errors


def test_back_button_asks_post_question_and_support_card(server, page):
    page.goto(server['url'] + '/chat/cicek-001')
    page.click('#consent-yes')
    page.click('#ins-skip')
    send(page, 'Bazen ölmek istiyorum')
    playwright.expect(page.get_by_role('note')).to_contain_text('112')
    page.click('#back-link')
    playwright.expect(page.locator('#ins-title')).to_have_text('Son olarak tek bir soru')
    page.click('#ins-skip')
    page.wait_for_url('**/explore')
    rows, _ = server['repo'].query_conversations(filters={'flagged': True})
    assert any(r['entity_id'] == 'cicek-001' for r in rows)


def test_admin_create_character(server, page):
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.goto(server['url'] + '/admin/')
    page.fill('#password', ADMIN_PASSWORD)
    shot(page, '05-admin-giris')
    page.click('button:has-text("Giriş Yap")')
    playwright.expect(page.locator('h1')).to_contain_text('Hoş geldiniz')
    shot(page, '06-admin-pano')

    page.click('text=Yeni karakter ekle')
    page.click('label:has-text("Park nesnesi")')
    page.fill('#name', 'Yaşlı Bank')
    page.fill('#location', 'Maçka Parkı, İstanbul')
    page.locator('#pick-map').click(position={'x': 300, 'y': 160})
    playwright.expect(page.locator('#pin-status')).to_contain_text('Konum işaretlendi')
    page.fill('#description', 'Parkın en çok oturulan bankıyım.')
    page.fill('#personality', 'Sabırlı, gözlemci, biraz şakacı.')
    page.fill('#backstory', 'Her sabah aynı yaşlı amca gazete okur.\nÇocuklar üstümde dondurma yer.')
    page.click('label:has-text("Sakin ve düşünceli")')
    page.locator('.voice-preview[data-voice="calm"]').click()
    playwright.expect(page.locator('.voice-preview[data-voice="calm"]')).to_contain_text('Dinle', timeout=5000)
    shot(page, '07-admin-form')
    page.click('button:has-text("Kaydet")')
    playwright.expect(page.locator('[role="status"]').first).to_contain_text('“Yaşlı Bank” kaydedildi.')
    shot(page, '08-admin-karakterler')

    entity = server['repo'].get_entity('nesne-001')
    assert entity['name'] == 'Yaşlı Bank' and entity['latitude'] is not None and entity['voice_profile'] == 'calm'

    page.goto(server['url'] + '/admin/sohbetler')
    playwright.expect(page.locator('main')).to_contain_text('sohbet bulundu')
    page.locator('a[href^="/admin/sohbetler/"]:has-text("Ulu Çınar")').first.click()
    playwright.expect(page.locator('main')).to_contain_text('Ziyaretçi bu cevabı beğenmedi')
    shot(page, '09-admin-sohbet')
    page.goto(server['url'] + '/admin/disa-aktar')
    shot(page, '10-admin-disa-aktar')
    with page.expect_download() as download:
        page.click('button[value="csv"]')
    assert download.value.suggested_filename.endswith('.csv')
    assert not own_errors(page), page.errors


def test_admin_validation_is_friendly(server, page):
    page.goto(server['url'] + '/admin/giris')
    page.fill('#password', ADMIN_PASSWORD)
    page.click('button:has-text("Giriş Yap")')
    page.goto(server['url'] + '/admin/karakterler/yeni')
    page.click('button:has-text("Kaydet")')
    playwright.expect(page.locator('main')).to_contain_text('Lütfen karaktere bir isim verin.')
    assert page.evaluate('document.activeElement.id') == 'name'  # ilk hatalı alana odaklanır
