"""DendroVox - Doğanın Sesi.

Parklardaki ağaçlar, bitkiler ve nesnelerle yapay zekâ destekli sohbet platformu.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request

from . import i18n
from .config import Config
from .llm import build_engine
from .security import apply_security_headers, csrf_token, limiter
from .storage import build_repository

log = logging.getLogger('dendrovox')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setup_logging(app):
    if log.handlers:
        return
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    log.addHandler(console)
    if not app.testing:
        os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
        file_handler = RotatingFileHandler(os.path.join(ROOT, 'logs', 'dendrovox.log'),
                                           maxBytes=1024 * 1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    log.setLevel(logging.INFO)


def create_app(overrides=None, repository=None, engine=None):
    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'), static_folder=os.path.join(ROOT, 'static'))
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    if not os.path.isabs(app.config['UPLOAD_FOLDER']):
        app.config['UPLOAD_FOLDER'] = os.path.join(ROOT, app.config['UPLOAD_FOLDER'])

    _setup_logging(app)
    if app.config.get('SECRET_KEY_IS_RANDOM') and not app.testing:
        log.warning('SECRET_KEY tanımlı değil: geçici anahtar üretildi, oturumlar yeniden başlatmada sıfırlanır.')

    i18n.load_translations(ROOT)
    app.extensions['repository'] = repository or build_repository(app.config)
    app.extensions['engine'] = engine or build_engine(app.config)

    app.config.setdefault('RATELIMIT_HEADERS_ENABLED', True)
    limiter.init_app(app)

    from .routes.admin import bp as admin_bp
    from .routes.api import bp as api_bp
    from .routes.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)

    app.after_request(apply_security_headers)

    @app.context_processor
    def inject_globals():
        return {
            '_': i18n.translate,
            'current_lang': i18n.get_locale(),
            'language_labels': i18n.LANGUAGE_LABELS,
            'csrf_token': csrf_token,
        }

    def wants_json():
        return request.path.startswith('/api/') or request.path.startswith('/admin/api/')

    @app.errorhandler(404)
    def not_found(error):
        if wants_json():
            return jsonify({'error': 'Bulunamadı.', 'code': 'not_found'}), 404
        return render_template('404.html'), 404

    @app.errorhandler(429)
    def too_many(error):
        message = i18n.translate('Çok hızlı mesaj gönderiyorsun. Biraz bekleyip tekrar dener misin?')
        if wants_json():
            return jsonify({'error': message, 'code': 'rate_limited'}), 429
        return render_template('500.html', message=message), 429

    @app.errorhandler(500)
    def server_error(error):
        log.exception('Sunucu hatası: %s', error)
        if wants_json():
            return jsonify({'error': 'Sunucu hatası.', 'code': 'server_error'}), 500
        return render_template('500.html'), 500

    return app


def repo():
    from flask import current_app
    return current_app.extensions['repository']


def engine():
    from flask import current_app
    return current_app.extensions['engine']
