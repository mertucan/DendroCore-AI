"""Ziyaretçi sayfaları."""

from flask import Blueprint, abort, current_app, make_response, redirect, render_template, request, send_from_directory

from .. import repo
from ..entities import ENTITY_ID_RE, public_entity, voice_profile
from ..i18n import LANG_COOKIE, get_locale, js_strings
from ..security import safe_next, session_id
from .common import TYPE_LABELS, facts_for, quick_replies, route_for, welcome_text

bp = Blueprint('pages', __name__)

CHAT_JS_STRINGS = [
    'Hmm, bir sorun oldu. Tekrar dener misin?',
    'Bağlantı hatası oluştu. Lütfen tekrar deneyin.',
    'Sohbet sonlandı.',
    'Mesaj limiti doldu',
    'Bu sohbetin mesaj limitine ulaşıldı. Başka bir karakterle konuşmak için Keşfet sayfasına dönebilirsin.',
    '{n} mesaj hakkın kaldı',
    'Bu cevap nasıldı?',
    'Beğendim',
    'Beğenmedim',
    'Neden beğenmedin?',
    'Karaktere uygun değil',
    'Yanlış bilgi',
    'Anlaşılmadı',
    'Çok uzun',
    'Başka bir sebep',
    'Teşekkürler! Görüşün araştırmaya katkı sağlıyor.',
    'Dinle',
    'Durdur',
    'Ses hazırlanıyor…',
    'Sesli okuma açık',
    'Sesli okuma kapalı',
    'Yeni bir tanışıklık! Koleksiyonuna eklendi.',
    'Koleksiyon: {count}/{total}',
    '{name} yazıyor…',
    '{name} diyor ki:',
    'Sen:',
    'Çok hızlı mesaj gönderiyorsun. Biraz bekleyip tekrar dener misin?',
    'Bu sohbet artık geçerli değil, yeni bir sohbet başlatıldı.',
    'Kayıt açık',
    'Kayıt kapalı',
    'Başlamadan önce tek bir soru',
    'Son olarak tek bir soru',
    'Kendini doğaya ne kadar yakın hissediyorsun? Seni ve doğayı en iyi anlatan resmi seç.',
    'Şimdi, bu sohbetten sonra kendini doğaya ne kadar yakın hissediyorsun?',
    'Biliyor muydun?',
    'Tüm bilgiler',
    'Sıradaki durak',
    'Parkta seni bekleyen başka sakinler de var.',
    'Sohbete başla',
    'Yol tarifi',
    '{distance} uzakta',
    'Başka bir parkta · {distance}',
    'Keşfet sayfasına dön',
    'Yeni karakterlerle tanışmak için Keşfet sayfasına göz at.',
    'Kendini kötü hissediyorsan yalnız değilsin. Güvendiğin bir yetişkinle konuşabilir, acil bir durumda 112\'yi arayabilirsin.',
    'Tanıştın',
]


@bp.before_app_request
def ensure_session():
    if not request.path.startswith('/static/'):
        session_id()


def _entities(lang):
    return [public_entity(e, lang) for e in repo().list_entities()]


@bp.route('/')
def index():
    lang = get_locale()
    entities = _entities(lang)
    parks = {(e.get('location') or '').split(',')[0].strip() for e in entities if e.get('location')}
    return render_template('index.html', entities=entities, park_count=len(parks))


@bp.route('/story')
def story():
    return render_template('story.html')


@bp.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')


@bp.route('/features')
def features():
    return render_template('features.html')


@bp.route('/faq')
def faq():
    return render_template('faq.html')


@bp.route('/explore')
def explore():
    lang = get_locale()
    return render_template('explore.html', entities=_entities(lang), type_labels=TYPE_LABELS,
                           collection_strings=js_strings(['Koleksiyon: {count}/{total}'], lang))


@bp.route('/chat/<entity_id>')
def chat(entity_id):
    if not ENTITY_ID_RE.match(entity_id):
        abort(404)
    entity = repo().get_entity(entity_id)
    if not entity or not entity.get('is_active'):
        abort(404)
    lang = get_locale()
    profile = voice_profile(entity)
    total = len(repo().list_entities())
    page = {
        'entity': public_entity(entity, lang),
        'welcome': welcome_text(entity, lang),
        'quick_replies': quick_replies(entity, lang),
        'voice': profile['browser'],
        'chat_limit': current_app.config['CHAT_LIMIT'],
        'consent_version': current_app.config['CONSENT_VERSION'],
        'entity_total': total,
        'lang': lang,
        'locale': 'tr-TR' if lang == 'tr' else 'en-US',
        'facts': facts_for(entity, lang),
        'route': route_for(entity, lang),
    }
    return render_template('chat.html', entity=page['entity'], page=page,
                           type_label=TYPE_LABELS.get(entity['type'], 'Park nesnesi'),
                           strings=js_strings(CHAT_JS_STRINGS, lang))


@bp.route('/lang/<code>')
def set_language(code):
    target = safe_next(request.args.get('next'))
    response = make_response(redirect(target))
    if code in current_app.config['LANGUAGES']:
        response.set_cookie(LANG_COOKIE, code, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return response


@bp.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, max_age=60 * 60 * 24 * 7)
