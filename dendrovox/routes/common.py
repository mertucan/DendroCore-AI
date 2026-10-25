"""Sayfalar ve API'nin ortak kullandığı karakter sunum yardımcıları."""

from flask import current_app

from ..context import context_prompt, get_context
from ..entities import build_system_prompt, localized, neighbors, neighbors_prompt, public_entity
from ..i18n import translate

DEFAULT_WELCOME = {
    'tree': 'Merhaba gezgin! Ben {name}. Yıllardır burada dimdik duruyorum ve anlatacak çok hikâyem var. Yapraklarımda hissettiğim rüzgârın hikâyesini duymak ister misin?',
    'cat': 'Hey, sen yeni misin buralarda? Ben {name}, bu parkın en havalı kedisi. Bana bir şeyler sormak ister misin?',
    'flower': 'Merhaba! Ben {name}. En güzel renklerimle seni karşılıyorum. Rengârenk dünyamı merak ediyor musun?',
    'object': 'Merhaba! Ben {name}. Her gün buradan geçen yüzlerce insanı izliyorum. Benimle biraz sohbet etmek ister misin?',
}
DEFAULT_QUICK_REPLIES = {
    'tree': ['Kaç yaşındasın?', 'En eski anın ne?', 'Yapraklarını ne zaman dökersin?'],
    'cat': ['Günün nasıl geçiyor?', 'En sevdiğin yer neresi?', 'Köpekler hakkında ne düşünüyorsun?'],
    'flower': ['Ne zaman çiçek açarsın?', 'En sevdiğin mevsim hangisi?', 'Kokun nasıl?'],
    'object': ['Bana kendini anlat', 'Burada ne kadar süredir varsın?', 'Bugün neler gördün?'],
}

TYPE_LABELS = {'tree': 'Ağaç', 'cat': 'Kedi', 'flower': 'Çiçek', 'object': 'Park nesnesi'}


def welcome_text(entity, lang):
    custom = localized(entity, 'welcome_message', lang)
    if custom and (lang == 'tr' or entity.get(f'welcome_message_{lang}')):
        return custom
    template = DEFAULT_WELCOME.get(entity['type'], DEFAULT_WELCOME['object'])
    return translate(template, lang, name=entity['name'])


def quick_replies(entity, lang):
    if lang == 'tr' and entity.get('quick_replies'):
        return entity['quick_replies']
    if lang != 'tr' and entity.get(f'quick_replies_{lang}'):
        return entity[f'quick_replies_{lang}']
    return [translate(q, lang) for q in DEFAULT_QUICK_REPLIES.get(entity['type'], DEFAULT_QUICK_REPLIES['object'])]


def entity_context(entity, lang):
    return get_context(entity, lang, tz=current_app.config['TIMEZONE'],
                       weather_enabled=current_app.config['WEATHER_ENABLED'])


def nearby_entities(entity, limit=3):
    from .. import repo
    return neighbors(entity, repo().list_entities(), limit)


def system_prompt_for(entity, lang):
    return build_system_prompt(entity, lang, context_prompt(entity_context(entity, lang)),
                               neighbors_prompt(nearby_entities(entity)))


def facts_for(entity, lang):
    """Bilgi kartı: İngilizce karşılık yoksa Türkçe bilgiler gösterilir."""
    if lang != 'tr' and entity.get(f'facts_{lang}'):
        return entity[f'facts_{lang}']
    return entity.get('facts') or []


def route_for(entity, lang):
    """Park rotası: sohbet sonunda önerilecek sıradaki duraklar."""
    route = []
    for other in nearby_entities(entity):
        item = public_entity(other, lang)
        item['distance_m'] = other['distance_m']
        route.append(item)
    return route
