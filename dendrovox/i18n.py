"""Basit çoklu dil desteği.

Şablonlarda Türkçe metin anahtar olarak kullanılır: {{ _('Keşfet') }}.
Diğer dillerin karşılıkları translations/<dil>.json dosyasındadır; karşılık yoksa Türkçe gösterilir.
"""

import json
import os

from flask import current_app, g, request

LANG_COOKIE = 'dendrovox-lang'
_translations = {}

LANGUAGE_LABELS = {'tr': 'Türkçe', 'en': 'English'}


def load_translations(root):
    folder = os.path.join(root, 'translations')
    for lang in ('en',):
        path = os.path.join(folder, f'{lang}.json')
        with open(path, encoding='utf-8') as handle:
            _translations[lang] = json.load(handle)


def get_locale():
    if 'lang' in g:
        return g.lang
    supported = current_app.config['LANGUAGES']
    lang = request.args.get('lang') or request.cookies.get(LANG_COOKIE)
    if lang not in supported:
        lang = request.accept_languages.best_match(supported) or current_app.config['DEFAULT_LANGUAGE']
    g.lang = lang
    return lang


def translate(text, lang=None, **kwargs):
    lang = lang or get_locale()
    result = text if lang == 'tr' else _translations.get(lang, {}).get(text, text)
    return result.format(**kwargs) if kwargs else result


def js_strings(keys, lang=None):
    """JavaScript tarafında kullanılacak metinler için {türkçe: çeviri} sözlüğü."""
    lang = lang or get_locale()
    return {key: translate(key, lang) for key in keys}
