"""Oturum kimliği, CSRF koruması, istek sınırlama anahtarları ve güvenlik başlıkları."""

import hmac
import secrets
import uuid
from functools import wraps

from flask import abort, current_app, jsonify, redirect, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .privacy import hash_session

limiter = Limiter(key_func=get_remote_address)


def session_id():
    """Ziyaretçi kimliği sunucuda üretilir ve imzalı çerezde tutulur; istemci değiştiremez."""
    if 'sid' not in session:
        session['sid'] = str(uuid.uuid4())
        session.permanent = True
    return session['sid']


def session_hash():
    return hash_session(session_id(), current_app.config['SECRET_KEY'])


def session_rate_key():
    return f'sid:{session_id()}'


def is_valid_uuid(value):
    try:
        return str(uuid.UUID(str(value))) == str(value).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    return session['_csrf']


def check_csrf():
    sent = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token') or ''
    expected = session.get('_csrf')
    # Oturumda anahtar yoksa boş gönderilen değer "eşleşmiş" sayılmamalı.
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description='csrf')


def require_json(view):
    """Herkese açık API'ler yalnızca JSON kabul eder; başka sitelerden form ile istek atılamaz."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not request.is_json:
            return jsonify({'error': 'JSON gerekli.', 'code': 'bad_request'}), 415
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get('is_admin'):
            if request.path.startswith('/admin/api/'):
                return jsonify({'error': 'Giriş gerekli.'}), 401
            return redirect(url_for('admin.login', next=request.full_path))
        if request.method == 'POST':
            check_csrf()
        return view(*args, **kwargs)
    return wrapper


def check_admin_password(password):
    expected = current_app.config.get('ADMIN_PASSWORD') or ''
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def apply_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if request.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def safe_next(target, fallback='/'):
    """Açık yönlendirmeyi önler: yalnızca site içi yollar kabul edilir."""
    if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return fallback
