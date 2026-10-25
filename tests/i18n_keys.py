"""Çevrilmesi gereken tüm Türkçe metinleri toplar (testler ve çeviri güncellemesi için).

Kullanım: python -m tests.i18n_keys   → eksik İngilizce çevirileri listeler.
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
_CALL = re.compile(r"""_\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*\)""")
_JS_T = re.compile(r"""\bt\(\s*'((?:[^'\\]|\\.)*)'""")

# Admin paneli yalnızca Türkçedir; çeviri gerektirmez.
SKIP_DIRS = {'admin'}


def template_keys():
    keys = []
    for path in sorted((ROOT / 'templates').rglob('*.html')):
        if SKIP_DIRS & set(path.relative_to(ROOT / 'templates').parts):
            continue
        for match in _CALL.finditer(path.read_text(encoding='utf-8')):
            keys.append(match.group(1) if match.group(1) is not None else match.group(2))
    return keys


def js_keys():
    source = (ROOT / 'static' / 'js' / 'chat.js').read_text(encoding='utf-8')
    return [key.replace("\\'", "'") for key in _JS_T.findall(source)]


def code_keys():
    from dendrovox.routes import api
    from dendrovox.routes.common import DEFAULT_QUICK_REPLIES, DEFAULT_WELCOME, TYPE_LABELS
    from dendrovox.routes.pages import CHAT_JS_STRINGS
    source = (ROOT / 'dendrovox' / 'routes' / 'api.py').read_text(encoding='utf-8')
    keys = list(CHAT_JS_STRINGS)
    keys += list(DEFAULT_WELCOME.values())
    keys += [q for items in DEFAULT_QUICK_REPLIES.values() for q in items]
    keys += list(TYPE_LABELS.values())
    keys += [api.FALLBACK_BUSY, api.FALLBACK_BLOCKED, api.LIMIT_REPLY]
    keys += re.findall(r"(?<![.\w])error\('([^']+)'", source)
    keys += ['Çok hızlı mesaj gönderiyorsun. Biraz bekleyip tekrar dener misin?']
    keys += ['Filiz', 'Fidan', 'Ulu Ağaç', 'Orman Bekçisi']
    return keys


def all_keys():
    return list(dict.fromkeys(template_keys() + code_keys()))


def load(lang='en'):
    return json.loads((ROOT / 'translations' / f'{lang}.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    existing = load()
    for key in all_keys():
        if key not in existing:
            print(key)
