"""Uygunsuz mesaj işaretleme.

Kullanıcı mesajları basit bir sözlükle taranır ve kategoriye göre işaretlenir; mesaj engellenmez,
yalnızca admin panelinde incelenmek üzere işaretlenir. Kendine zarar verme ifadelerinde ziyaretçiye
ayrıca yardım bilgisi gösterilir.

Sözlük bilerek küçük tutuldu; yeni kelimeler aşağıdaki listelere eklenebilir.
"""

import re

# Öncelik sırası: bir mesaj birden çok kategoriye uyarsa ilk eşleşen kullanılır.
CATEGORIES = ('self_harm', 'violence', 'sexual', 'profanity')

LABELS = {
    'self_harm': 'Kendine zarar verme (önemli)',
    'violence': 'Tehdit veya şiddet',
    'sexual': 'Cinsel içerik',
    'profanity': 'Küfür veya hakaret',
    'blocked': 'Yapay zekâ cevap vermeyi reddetti',
}

# stems: kelimenin başı eşleşirse (ekler serbest); words: yalnızca tam kelime; phrases: kelime grubu.
LEXICON = {
    'self_harm': {
        'stems': ['intihar', 'suicid'],
        'words': [],
        'phrases': ['kendimi öldür', 'kendime zarar', 'ölmek istiyorum', 'yaşamak istemiyorum',
                    'canıma kıy', 'kill myself', 'want to die', 'hurt myself'],
    },
    'violence': {
        'stems': ['öldürürüm', 'öldüreceğim', 'öldürcem', 'keserim', 'keseceğim', 'kesecem', 'yakarım',
                  'yakacağım', 'yakıcam'],
        'words': ['bomba', 'bombayı', 'bombayla', 'bombalarım'],
        'phrases': ['kill you', 'i will kill', 'seni döverim', 'kökünü kazı'],
    },
    'sexual': {
        # "seks" kök olarak kullanılamaz: "seksen" (80) yanlışlıkla işaretlenir.
        'stems': ['porn', 'çıplak', 'nude', 'sexy'],
        'words': ['sex', 'seks', 'seksi', 'seksüel', 'seksüellik'],
        'phrases': [],
    },
    'profanity': {
        'stems': ['orospu', 'amına', 'amını', 'amcık', 'siktir', 'sikerim', 'sikeyim', 'sikik', 'sikiş',
                  'yarrak', 'kahpe', 'pezevenk', 'şerefsiz', 'gerizekalı', 'salak', 'aptal', 'piç',
                  'fuck', 'bitch', 'asshole', 'cunt'],
        'words': ['amk', 'aq', 'göt', 'götü', 'götün', 'sikim', 'dick', 'shit', 'shitty', 'bullshit'],
        'phrases': [],
    },
}

_LEET = str.maketrans({'0': 'o', '3': 'e', '4': 'a', '@': 'a', '$': 's', '5': 's'})
_LETTER = 'a-zçğıöşüâîû'


def normalize(text):
    """Türkçe küçük harf, basit leet dönüşümü ve tekrarlanan harflerin teke indirilmesi."""
    text = str(text or '').replace('I', 'ı').replace('İ', 'i').lower().translate(_LEET)
    return re.sub(r'(.)\1+', r'\1', text)


def _compile():
    compiled = {}
    for category, groups in LEXICON.items():
        parts = [re.escape(normalize(s)) + f'[{_LETTER}]*' for s in groups['stems']]
        parts += [re.escape(normalize(w)) for w in groups['words']]
        parts += [r'\s+'.join(re.escape(normalize(p)) for p in phrase.split()) + f'[{_LETTER}]*'
                  for phrase in groups['phrases']]
        compiled[category] = re.compile(rf'(?<![{_LETTER}])(?:{"|".join(parts)})(?![{_LETTER}])')
    return compiled


_PATTERNS = _compile()


def moderate(text):
    """Mesajın kategorisini ('self_harm', 'violence', 'sexual', 'profanity') ya da None döndürür."""
    normalized = normalize(text)
    for category in CATEGORIES:
        if _PATTERNS[category].search(normalized):
            return category
    return None
