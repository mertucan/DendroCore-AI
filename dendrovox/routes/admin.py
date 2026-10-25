"""Yönetim paneli: teknik bilgi gerektirmeyen, sade bir arayüz."""

import logging
import os
import secrets
from datetime import date

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request,
                   session, url_for)

from .. import engine, repo
from ..entities import ENTITY_ID_RE, ENTITY_TYPES, VOICE_PROFILES, lines
from ..llm import LLMUnavailable
from ..moderation import LABELS as FLAG_LABELS
from ..reports import REASON_LABELS, build_export, dashboard_stats, export_csv, export_json, local_day_range, parse_ts
from ..security import admin_required, check_admin_password, check_csrf, csrf_token, is_valid_uuid, limiter, safe_next
from .common import TYPE_LABELS

log = logging.getLogger('dendrovox')
bp = Blueprint('admin', __name__, url_prefix='/admin')

PAGE_SIZE = 20
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}
MAX_QUICK_REPLIES = 6
MAX_FACTS = 8


@bp.app_template_filter('local_time')
def local_time(value, fmt='%d.%m.%Y %H:%M'):
    from zoneinfo import ZoneInfo
    parsed = parse_ts(value)
    return parsed.astimezone(ZoneInfo(current_app.config['TIMEZONE'])).strftime(fmt) if parsed else '—'


@bp.context_processor
def admin_globals():
    return {'db_warning': repo().warning, 'type_labels': TYPE_LABELS}


# ── Giriş ──

@bp.route('/giris', methods=['GET', 'POST'])
@limiter.limit('10/minute', methods=['POST'])
def login():
    enabled = bool(current_app.config.get('ADMIN_PASSWORD'))
    error = None
    if request.method == 'POST' and enabled:
        check_csrf()
        if check_admin_password(request.form.get('password', '')):
            sid = session.get('sid')
            session.clear()  # oturum sabitlemeye karşı
            if sid:
                session['sid'] = sid
            session['is_admin'] = True
            session.permanent = True
            csrf_token()  # temizlenen oturum için yeni CSRF anahtarı
            log.info('Admin girişi yapıldı.')
            return redirect(safe_next(request.args.get('next'), url_for('admin.dashboard')))
        log.warning('Hatalı admin şifresi denemesi.')
        error = 'Şifre yanlış. Lütfen tekrar deneyin.'
    return render_template('admin/login.html', enabled=enabled, error=error)


@bp.route('/cikis', methods=['POST'])
@admin_required
def logout():
    session.pop('is_admin', None)
    flash('Güvenli çıkış yapıldı. Görüşmek üzere!', 'success')
    return redirect(url_for('admin.login'))


# ── Ana sayfa ──

@bp.route('/')
@admin_required
def dashboard():
    entities = repo().list_entities(include_inactive=True)
    stats = dashboard_stats(repo(), entities, current_app.config['TIMEZONE'])
    return render_template('admin/dashboard.html', stats=stats, entity_count=len(entities))


# ── Karakterler ──

@bp.route('/karakterler')
@admin_required
def entities():
    items = repo().list_entities(include_inactive=True)
    stats = dashboard_stats(repo(), items, current_app.config['TIMEZONE'])
    counts = {row['id']: row['count'] for row in stats['by_entity']}
    return render_template('admin/entities.html', entities=items, counts=counts)


def _blank_entity():
    return {'id': None, 'name': '', 'type': 'tree', 'species': '', 'age_years': '', 'location': '',
            'latitude': None, 'longitude': None, 'description': '', 'description_en': '', 'personality': '',
            'backstory': '', 'welcome_message': '', 'welcome_message_en': '', 'quick_replies': [],
            'quick_replies_en': [], 'facts': [], 'facts_en': [], 'voice_profile': 'wise', 'image_url': '',
            'is_active': True}


def _text(form, name, max_len):
    return (form.get(name) or '').strip()[:max_len]


def parse_entity_form(form, base):
    """Formu doğrular. (kayıt, hatalar) döndürür; hata mesajları sade Türkçedir."""
    entity = dict(base)
    errors = {}

    entity['name'] = _text(form, 'name', 60)
    if not entity['name']:
        errors['name'] = 'Lütfen karaktere bir isim verin.'
    entity['type'] = form.get('type') if form.get('type') in ENTITY_TYPES else None
    if not entity['type']:
        errors['type'] = 'Lütfen karakterin ne olduğunu seçin.'
    entity['species'] = _text(form, 'species', 80)
    entity['location'] = _text(form, 'location', 120)
    if not entity['location']:
        errors['location'] = 'Lütfen karakterin bulunduğu yeri yazın (ör. Yıldız Parkı, İstanbul).'

    age = (form.get('age_years') or '').strip()
    if age:
        if age.isdigit() and int(age) <= 5000:
            entity['age_years'] = int(age)
        else:
            errors['age_years'] = 'Yaşı sadece rakamla yazın (ör. 120). Bilmiyorsanız boş bırakın.'
    else:
        entity['age_years'] = None

    lat, lng = (form.get('latitude') or '').strip(), (form.get('longitude') or '').strip()
    if lat and lng:
        try:
            entity['latitude'], entity['longitude'] = float(lat), float(lng)
            if not (-90 <= entity['latitude'] <= 90 and -180 <= entity['longitude'] <= 180):
                raise ValueError
        except ValueError:
            errors['location_pin'] = 'Haritadaki konum okunamadı. Lütfen haritaya tekrar tıklayın.'
    else:
        entity['latitude'] = entity['longitude'] = None

    entity['description'] = _text(form, 'description', 400)
    if not entity['description']:
        errors['description'] = 'Lütfen ziyaretçilerin göreceği kısa bir tanıtım yazın.'
    entity['description_en'] = _text(form, 'description_en', 400)
    entity['personality'] = _text(form, 'personality', 600)
    if not entity['personality']:
        errors['personality'] = 'Lütfen karakterin nasıl biri olduğunu birkaç kelimeyle anlatın.'
    entity['backstory'] = '\n'.join(lines(_text(form, 'backstory', 3000)))
    entity['welcome_message'] = _text(form, 'welcome_message', 400)
    entity['welcome_message_en'] = _text(form, 'welcome_message_en', 400)

    for field in ('quick_replies', 'quick_replies_en'):
        items = [item[:80] for item in lines(form.get(field, ''))]
        if len(items) > MAX_QUICK_REPLIES:
            errors[field] = f'En fazla {MAX_QUICK_REPLIES} soru yazabilirsiniz.'
        entity[field] = items[:MAX_QUICK_REPLIES]

    for field in ('facts', 'facts_en'):
        items = [item[:300] for item in lines(form.get(field, ''))]
        if len(items) > MAX_FACTS:
            errors[field] = f'En fazla {MAX_FACTS} bilgi yazabilirsiniz.'
        entity[field] = items[:MAX_FACTS]

    entity['voice_profile'] = form.get('voice_profile') if form.get('voice_profile') in VOICE_PROFILES else 'friendly'
    entity['is_active'] = form.get('is_active') == 'on'
    if form.get('remove_photo') == 'on':
        entity['image_url'] = ''
    return entity, errors


def save_photo(file_storage, entity_id):
    """Fotoğrafı doğrular, küçültür ve konum (EXIF) bilgilerini silerek kaydeder."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        image = Image.open(file_storage.stream)
        if image.format not in ALLOWED_IMAGE_FORMATS:
            return None, 'Bu dosya türü desteklenmiyor. Lütfen JPG veya PNG fotoğraf seçin.'
        image = ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((1200, 1200))
    except (UnidentifiedImageError, OSError, ValueError):
        return None, 'Bu dosya bir fotoğraf olarak açılamadı. Lütfen başka bir fotoğraf seçin.'
    folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    filename = f'{entity_id}-{secrets.token_hex(4)}.jpg'
    image.save(os.path.join(folder, filename), 'JPEG', quality=85, optimize=True)
    return url_for('pages.uploads', filename=filename), None


def _entity_form(entity, is_new):
    errors = {}
    if request.method == 'POST':
        entity, errors = parse_entity_form(request.form, entity)
        photo = request.files.get('photo')
        if not errors:
            if is_new:
                entity['id'] = repo().next_entity_id(entity['type'])
            if photo and photo.filename:
                url, photo_error = save_photo(photo, entity['id'])
                if photo_error:
                    errors['photo'] = photo_error
                else:
                    entity['image_url'] = url
        if not errors:
            saved = repo().save_entity(entity)
            log.info('Karakter kaydedildi: %s', saved['id'])
            flash(f'“{saved["name"]}” kaydedildi.', 'success')
            return redirect(url_for('admin.entities'))
        if is_new:
            entity['id'] = None
        flash('Bazı alanlarda eksik var. Kırmızı ile işaretli yerlere bakar mısınız?', 'error')
    return render_template('admin/entity_form.html', entity=entity, errors=errors, is_new=is_new,
                           voice_profiles=VOICE_PROFILES, entity_types=ENTITY_TYPES), 400 if errors else 200


@bp.route('/karakterler/yeni', methods=['GET', 'POST'])
@admin_required
def entity_new():
    return _entity_form(_blank_entity(), is_new=True)


@bp.route('/karakterler/<entity_id>', methods=['GET', 'POST'])
@admin_required
def entity_edit(entity_id):
    entity = repo().get_entity(entity_id) if ENTITY_ID_RE.match(entity_id) else None
    if not entity:
        abort(404)
    return _entity_form(entity, is_new=False)


@bp.route('/karakterler/<entity_id>/durum', methods=['POST'])
@admin_required
def entity_toggle(entity_id):
    entity = repo().get_entity(entity_id) if ENTITY_ID_RE.match(entity_id) else None
    if not entity:
        abort(404)
    entity['is_active'] = not entity.get('is_active')
    repo().save_entity(entity)
    if entity['is_active']:
        flash(f'“{entity["name"]}” artık ziyaretçilere görünüyor.', 'success')
    else:
        flash(f'“{entity["name"]}” gizlendi. Ziyaretçiler artık onu görmeyecek.', 'success')
    return redirect(url_for('admin.entities'))


@bp.route('/api/ses-onizleme', methods=['POST'])
@admin_required
@limiter.limit('20/minute')
def voice_preview():
    data = request.get_json(silent=True) or {}
    profile = VOICE_PROFILES.get(data.get('voice_profile'))
    if not profile:
        return jsonify({'error': 'Ses bulunamadı.'}), 400
    name = str(data.get('name') or '').strip()[:60] or 'bir park sakini'
    text = f'Merhaba! Ben {name}. Sesim böyle duyuluyor. Benimle sohbet etmeye ne dersin?'
    try:
        audio = engine().synthesize(text, profile['voice'], profile['style']['tr'], 'tr')
    except LLMUnavailable:
        return jsonify({'error': 'Ses şu an hazırlanamıyor.', 'browser': profile['browser'], 'text': text}), 503
    return Response(audio, mimetype='audio/wav')


# ── Sohbetler ──

def _date_arg(name):
    try:
        return date.fromisoformat(request.args.get(name, ''))
    except ValueError:
        return None


@bp.route('/sohbetler')
@admin_required
def conversations():
    entity_id = request.args.get('karakter') or None
    start, end = _date_arg('baslangic'), _date_arg('bitis')
    review = request.args.get('incelenecek') == 'on'
    page = max(1, request.args.get('sayfa', 1, type=int))
    since, until = local_day_range(start, end, current_app.config['TIMEZONE'])
    rows, total = repo().query_conversations(entity_id=entity_id, since=since, until=until,
                                             limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
                                             filters={'flagged': True, 'flag_reviewed': False} if review else None)
    feedback = repo().feedback_for([r['id'] for r in rows]) if rows else []
    likes = {}
    for item in feedback:
        counter = likes.setdefault(item['conversation_id'], {'up': 0, 'down': 0})
        counter['up' if item['rating'] == 1 else 'down'] += 1
    entities = repo().list_entities(include_inactive=True)
    return render_template('admin/conversations.html', rows=rows, total=total, page=page,
                           pages=max(1, -(-total // PAGE_SIZE)), likes=likes, entities=entities,
                           names={e['id']: e['name'] for e in entities},
                           filters={'karakter': entity_id or '', 'baslangic': start or '', 'bitis': end or '',
                                    'incelenecek': 'on' if review else ''})


@bp.route('/sohbetler/<conversation_id>')
@admin_required
def conversation_detail(conversation_id):
    conv = repo().persistent.get_conversation(conversation_id) if is_valid_uuid(conversation_id) else None
    if not conv:
        abort(404)
    messages = repo().persistent.get_messages(conversation_id)
    feedback = {f['message_id']: f for f in repo().feedback_for([conversation_id])}
    entity = repo().get_entity(conv['entity_id'])
    return render_template('admin/conversation_detail.html', conv=conv, messages=messages, feedback=feedback,
                           entity=entity, reason_labels=REASON_LABELS, flag_labels=FLAG_LABELS,
                           metrics=conv.get('metrics') if isinstance(conv.get('metrics'), dict) else {})


@bp.route('/sohbetler/<conversation_id>/incelendi', methods=['POST'])
@admin_required
def conversation_reviewed(conversation_id):
    conv = repo().persistent.get_conversation(conversation_id) if is_valid_uuid(conversation_id) else None
    if not conv:
        abort(404)
    repo().persistent.update_conversation(conversation_id, {'flag_reviewed': True})
    flash('Teşekkürler, sohbet incelendi olarak işaretlendi.', 'success')
    return redirect(url_for('admin.conversations', incelenecek='on'))


@bp.route('/sohbetler/<conversation_id>/sil', methods=['POST'])
@admin_required
def conversation_delete(conversation_id):
    if is_valid_uuid(conversation_id) and repo().delete_conversation(conversation_id):
        log.info('Sohbet silindi: %s', conversation_id)
        flash('Sohbet kalıcı olarak silindi.', 'success')
    else:
        flash('Sohbet bulunamadı.', 'error')
    return redirect(url_for('admin.conversations'))


# ── Dışa aktarım ──

@bp.route('/disa-aktar')
@admin_required
def export_page():
    return render_template('admin/export.html', entities=repo().list_entities(include_inactive=True))


@bp.route('/disa-aktar/indir')
@admin_required
def export_download():
    fmt = request.args.get('bicim', 'csv')
    entity_id = request.args.get('karakter') or None
    start, end = _date_arg('baslangic'), _date_arg('bitis')
    include_legacy = request.args.get('eski') == 'on'
    since, until = local_day_range(start, end, current_app.config['TIMEZONE'])
    entities = repo().list_entities(include_inactive=True)
    data = build_export(repo(), entities, current_app.config['TIMEZONE'], since, until, entity_id, include_legacy)
    stamp = date.today().isoformat()
    log.info('Dışa aktarım: biçim=%s sohbet=%d', fmt, len(data))
    if fmt == 'json':
        filters = {'karakter': entity_id, 'baslangic': str(start or ''), 'bitis': str(end or ''),
                   'eski_sohbetler': include_legacy}
        return Response(export_json(data, filters), mimetype='application/json',
                        headers={'Content-Disposition': f'attachment; filename=dendrovox-veri-{stamp}.json'})
    return Response(export_csv(data), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=dendrovox-veri-{stamp}.csv'})
