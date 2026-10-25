"""Herkese açık JSON API'leri: sohbet (akışlı), geri bildirim, seslendirme."""

import json
import logging

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from .. import engine, repo
from ..entities import ENTITY_ID_RE, public_entity, voice_profile
from ..i18n import get_locale, translate
from ..llm import ContentBlocked, LLMUnavailable
from ..moderation import moderate
from ..privacy import hash_session, mask_pii
from ..security import is_valid_uuid, limiter, require_json, session_hash, session_rate_key
from .common import entity_context, system_prompt_for, welcome_text

log = logging.getLogger('dendrovox')
bp = Blueprint('api', __name__, url_prefix='/api')

FEEDBACK_REASONS = {'off_character', 'wrong_info', 'unclear', 'too_long', 'other'}
TTS_MAX_CHARS = 1200

FALLBACK_BUSY = 'Çok fazla ziyaretçim oldu bugün, biraz yoruldum. Birkaç saniye sonra tekrar yazar mısın?'
FALLBACK_BLOCKED = 'Bu konuda konuşmak istemiyorum, başka bir şey sorar mısın?'
LIMIT_REPLY = 'Bu sohbetin sonuna geldik gezgin. Enerjimi toplamak için biraz dinlenmem gerekiyor. Başka zaman tekrar gel!'


def error(message, code, status):
    return jsonify({'error': translate(message), 'code': code}), status


def _sse(payload):
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def _owned_conversation(conversation_id):
    """Sohbet yalnızca onu başlatan tarayıcı oturumu tarafından kullanılabilir."""
    if not is_valid_uuid(conversation_id):
        return None
    conv = repo().get_conversation(conversation_id)
    if not conv or conv.get('session_id') != session_hash():
        return None
    return conv


def chat_limit():
    return current_app.config['CHAT_RATE_LIMIT']


def chat_ip_limit():
    return current_app.config['CHAT_IP_RATE_LIMIT']


def tts_limit():
    return current_app.config['TTS_RATE_LIMIT']


@bp.route('/chat', methods=['POST'])
@limiter.limit(chat_limit, key_func=session_rate_key)
@limiter.limit(chat_ip_limit)
@require_json
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error('Geçersiz istek.', 'bad_request', 400)

    entity_id = data.get('entity_id')
    message = data.get('message')
    conversation_id = data.get('conversation_id')
    if not isinstance(entity_id, str) or not ENTITY_ID_RE.match(entity_id):
        return error('Geçersiz varlık kimliği.', 'bad_entity', 400)
    if not isinstance(message, str) or not message.strip():
        return error('Mesaj boş olamaz.', 'empty_message', 400)
    message = message.strip()[:current_app.config['MAX_MESSAGE_LENGTH']]

    entity = repo().get_entity(entity_id)
    if not entity or not entity.get('is_active'):
        return error('Varlık bulunamadı.', 'entity_not_found', 404)

    limit = current_app.config['CHAT_LIMIT']
    lang = get_locale()
    if conversation_id is not None:
        conv = _owned_conversation(conversation_id)
        if not conv or conv['entity_id'] != entity_id:
            return error('Sohbet bulunamadı.', 'conversation_not_found', 404)
        history = repo().get_messages(conv)
    else:
        consent = data.get('consent') is True
        extra = None
        if consent:
            extra = {'ins_pre': _scale_value(data.get('ins_pre'))}
            if is_valid_uuid(data.get('visitor_id')):
                visitor = hash_session('visitor:' + data['visitor_id'], current_app.config['SECRET_KEY'])
                extra['visitor_hash'] = visitor
                extra['visit_number'] = repo().count_visitor_conversations(visitor) + 1
        conv = repo().create_conversation(entity_id, session_hash(), lang, consent,
                                          current_app.config['CONSENT_VERSION'], extra)
        history = []

    used = sum(1 for m in history if m['role'] == 'user')
    if used >= limit:
        repo().complete_conversation(conv)
        return jsonify({'limit_reached': True, 'reply': translate(LIMIT_REPLY, lang), 'conversation_id': conv['id']})

    system_prompt = system_prompt_for(entity, lang)
    llm = engine()
    store = repo()
    flag = moderate(message)

    def generate():
        nonlocal flag
        yield _sse({'type': 'meta', 'conversation_id': conv['id'], 'consent': conv['consent']})
        parts, model, fallback = [], None, False
        try:
            for kind, value in llm.stream_reply(system_prompt, history, message):
                if kind == 'delta':
                    parts.append(value)
                    yield _sse({'type': 'delta', 'text': value})
                else:
                    model = value
        except ContentBlocked:
            parts, model, fallback = [translate(FALLBACK_BLOCKED, lang)], 'blocked', True
            flag = flag or 'blocked'
        except LLMUnavailable as exc:
            log.error('Yanıt üretilemedi (%s): %s', entity_id, exc)
            parts, model, fallback = [translate(FALLBACK_BUSY, lang)], 'unavailable', True
        if fallback:
            yield _sse({'type': 'delta', 'text': parts[0]})

        reply = ''.join(parts).strip()
        try:
            saved = store.add_messages(conv, [('user', mask_pii(message), None, flag), ('assistant', reply, model)])
            message_id = saved[1]['id']
            if flag and conv['consent']:
                store.update_conversation(conv, {'flagged': True, 'flag_reviewed': False})
        except Exception as exc:
            log.error('Mesaj kaydedilemedi (%s): %s', conv['id'], exc)
            message_id = None
        if flag:
            log.warning('İşaretli mesaj: varlık=%s kategori=%s', entity_id, flag)
        remaining = limit - used - 1
        if remaining <= 0:
            store.complete_conversation(conv)
        log.info('Sohbet: varlık=%s kayıt=%s model=%s uzunluk=%d', entity_id, conv['consent'], model, len(message))
        yield _sse({'type': 'done', 'message_id': message_id, 'remaining': remaining,
                    'limit_reached': remaining <= 0, 'fallback': fallback, 'support': flag == 'self_harm'})

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _scale_value(value):
    """Doğaya yakınlık ölçeği 1-7; geçersizse None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 7 else None


METRIC_LIMITS = {
    'first_message_ms': 3_600_000, 'visible_ms': 86_400_000, 'quick_replies': 100, 'typed': 100,
    'listens': 500, 'facts_opened': 100, 'route_clicks': 100,
}
METRIC_FLAGS = ('auto_read',)
METRIC_ENDINGS = ('limit', 'finish', 'left')


def clean_metrics(raw):
    """Yalnızca bilinen, sayısal ve sınırlı ölçümler saklanır (metin ya da kişisel veri kabul edilmez)."""
    metrics = {}
    for key, limit in METRIC_LIMITS.items():
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = int(min(max(value, 0), limit))
    for key in METRIC_FLAGS:
        if isinstance(raw.get(key), bool):
            metrics[key] = raw[key]
    if raw.get('ended') in METRIC_ENDINGS:
        metrics['ended'] = raw['ended']
    return metrics


@bp.route('/survey', methods=['POST'])
@limiter.limit('30/minute', key_func=session_rate_key)
@require_json
def survey():
    """Sohbet sonrası doğaya yakınlık ölçümü (öncesi sohbetin ilk mesajıyla gelir)."""
    data = request.get_json(silent=True) or {}
    value = _scale_value(data.get('value'))
    conv = _owned_conversation(data.get('conversation_id'))
    if value is None:
        return error('Geçersiz istek.', 'bad_request', 400)
    if not conv:
        return error('Sohbet bulunamadı.', 'conversation_not_found', 404)
    if not conv['consent']:
        return error('Kayıt izni olmadan geri bildirim saklanmaz.', 'no_consent', 400)
    repo().update_conversation(conv, {'ins_post': value})
    return jsonify({'ok': True})


@bp.route('/metrics', methods=['POST'])
@limiter.limit('60/minute', key_func=session_rate_key)
@require_json
def metrics():
    """Sayfadan ayrılırken gönderilen isimsiz etkileşim özeti (son gelen geçerlidir)."""
    data = request.get_json(silent=True) or {}
    conv = _owned_conversation(data.get('conversation_id'))
    if not conv or not isinstance(data.get('metrics'), dict):
        return error('Geçersiz istek.', 'bad_request', 400)
    if conv['consent']:
        repo().update_conversation(conv, {'metrics': clean_metrics(data['metrics'])})
    return jsonify({'ok': True})


@bp.route('/feedback', methods=['POST'])
@limiter.limit('60/minute', key_func=session_rate_key)
@require_json
def feedback():
    data = request.get_json(silent=True) or {}
    message_id = data.get('message_id')
    rating = data.get('rating')
    reason = data.get('reason')
    if not is_valid_uuid(message_id) or rating not in (1, -1):
        return error('Geçersiz istek.', 'bad_request', 400)
    if reason is not None and (rating != -1 or reason not in FEEDBACK_REASONS):
        return error('Geçersiz istek.', 'bad_request', 400)

    msg = repo().get_message(message_id)
    conv = _owned_conversation(msg['conversation_id']) if msg else None
    if not conv or msg['role'] != 'assistant':
        return error('Mesaj bulunamadı.', 'not_found', 404)
    if not conv['consent']:
        return error('Kayıt izni olmadan geri bildirim saklanmaz.', 'no_consent', 400)
    repo().save_feedback(message_id, conv['id'], rating, reason)
    return jsonify({'ok': True})


@bp.route('/tts', methods=['POST'])
@limiter.limit(tts_limit, key_func=session_rate_key)
@require_json
def tts():
    """Yalnızca karakterin gerçekten söylediği metinler seslendirilir (keyfi metin kabul edilmez)."""
    data = request.get_json(silent=True) or {}
    lang = get_locale()
    if data.get('message_id'):
        msg = repo().get_message(data['message_id']) if is_valid_uuid(data['message_id']) else None
        conv = _owned_conversation(msg['conversation_id']) if msg else None
        if not conv or msg['role'] != 'assistant':
            return error('Mesaj bulunamadı.', 'not_found', 404)
        entity = repo().get_entity(conv['entity_id'])
        text = msg['content']
        lang = conv.get('lang') or lang
    elif data.get('kind') == 'welcome' and isinstance(data.get('entity_id'), str):
        entity = repo().get_entity(data['entity_id']) if ENTITY_ID_RE.match(data['entity_id']) else None
        text = welcome_text(entity, lang) if entity else None
    else:
        return error('Geçersiz istek.', 'bad_request', 400)
    if not entity or not text:
        return error('Bulunamadı.', 'not_found', 404)

    profile = voice_profile(entity)
    style = profile['style'].get(lang, profile['style']['tr'])
    try:
        audio = engine().synthesize(text[:TTS_MAX_CHARS], profile['voice'], style, lang)
    except LLMUnavailable:
        return error('Ses şu an hazırlanamıyor.', 'tts_unavailable', 503)
    return Response(audio, mimetype='audio/wav', headers={'Cache-Control': 'private, max-age=3600'})


@bp.route('/entities')
def entities():
    lang = get_locale()
    return jsonify([public_entity(e, lang) for e in repo().list_entities()])


@bp.route('/context/<entity_id>')
def context(entity_id):
    entity = repo().get_entity(entity_id) if ENTITY_ID_RE.match(entity_id) else None
    if not entity:
        return error('Bulunamadı.', 'not_found', 404)
    return jsonify(entity_context(entity, get_locale()))


@bp.route('/stats')
def stats():
    try:
        conversations, messages = repo().count_totals()
    except Exception as exc:
        log.error('İstatistik hatası: %s', exc)
        conversations = messages = 0
    return jsonify({'total_conversations': conversations, 'total_messages': messages})
