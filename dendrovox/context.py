"""Bağlama duyarlı karakterler: mevsim, günün saati ve anlık hava durumu.

Hava durumu Open-Meteo'dan (ücretsiz, anahtarsız) alınır ve konum başına 20 dk önbelleklenir.
Hava servisine ulaşılamazsa yalnızca mevsim ve saat bilgisi kullanılır.
"""

import logging
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger('dendrovox')

WEATHER_TTL = 20 * 60
WEATHER_TIMEOUT = 2.5
_cache = {}
_lock = threading.Lock()

MONTHS = {
    'tr': ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'],
    'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
}
SEASONS = {
    'winter': {'tr': 'kış', 'en': 'winter', 'icon': 'ac_unit'},
    'spring': {'tr': 'ilkbahar', 'en': 'spring', 'icon': 'local_florist'},
    'summer': {'tr': 'yaz', 'en': 'summer', 'icon': 'wb_sunny'},
    'autumn': {'tr': 'sonbahar', 'en': 'autumn', 'icon': 'eco'},
}
TIMES_OF_DAY = {
    'night': {'tr': 'gece', 'en': 'night'},
    'morning': {'tr': 'sabah', 'en': 'morning'},
    'noon': {'tr': 'öğle', 'en': 'midday'},
    'afternoon': {'tr': 'öğleden sonra', 'en': 'afternoon'},
    'evening': {'tr': 'akşam', 'en': 'evening'},
}

# WMO hava kodu → (Türkçe, İngilizce, ikon)
WEATHER_CODES = {
    0: ('açık', 'clear', 'wb_sunny'),
    1: ('çoğunlukla açık', 'mostly clear', 'wb_sunny'),
    2: ('parçalı bulutlu', 'partly cloudy', 'wb_cloudy'),
    3: ('kapalı', 'overcast', 'cloud'),
    45: ('sisli', 'foggy', 'foggy'),
    48: ('kırağılı sis', 'freezing fog', 'foggy'),
    51: ('hafif çiseleme', 'light drizzle', 'grain'),
    53: ('çiseleme', 'drizzle', 'grain'),
    55: ('yoğun çiseleme', 'heavy drizzle', 'grain'),
    61: ('hafif yağmurlu', 'light rain', 'water_drop'),
    63: ('yağmurlu', 'rainy', 'water_drop'),
    65: ('sağanak yağmurlu', 'heavy rain', 'water_drop'),
    66: ('dondurucu yağmur', 'freezing rain', 'water_drop'),
    67: ('yoğun dondurucu yağmur', 'heavy freezing rain', 'water_drop'),
    71: ('hafif karlı', 'light snow', 'ac_unit'),
    73: ('karlı', 'snowy', 'ac_unit'),
    75: ('yoğun kar yağışlı', 'heavy snow', 'ac_unit'),
    77: ('kar taneli', 'snow grains', 'ac_unit'),
    80: ('hafif sağanak', 'light showers', 'umbrella'),
    81: ('sağanak', 'showers', 'umbrella'),
    82: ('şiddetli sağanak', 'violent showers', 'umbrella'),
    85: ('kar sağanağı', 'snow showers', 'ac_unit'),
    86: ('yoğun kar sağanağı', 'heavy snow showers', 'ac_unit'),
    95: ('gök gürültülü fırtına', 'thunderstorm', 'thunderstorm'),
    96: ('dolulu fırtına', 'thunderstorm with hail', 'thunderstorm'),
    99: ('şiddetli dolulu fırtına', 'severe thunderstorm with hail', 'thunderstorm'),
}


def season_of(month):
    return {12: 'winter', 1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
            6: 'summer', 7: 'summer', 8: 'summer'}.get(month, 'autumn')


def time_of_day(hour):
    if hour < 5 or hour >= 22:
        return 'night'
    if hour < 11:
        return 'morning'
    if hour < 14:
        return 'noon'
    if hour < 18:
        return 'afternoon'
    return 'evening'


def fetch_weather(lat, lng):
    """Open-Meteo'dan anlık hava; hata olursa None. Testlerde değiştirilebilir."""
    key = (round(float(lat), 2), round(float(lng), 2))
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < WEATHER_TTL:
            return cached[1]
    try:
        response = httpx.get('https://api.open-meteo.com/v1/forecast', timeout=WEATHER_TIMEOUT, params={
            'latitude': key[0], 'longitude': key[1],
            'current': 'temperature_2m,weather_code,wind_speed_10m,is_day',
        })
        response.raise_for_status()
        current = response.json()['current']
        weather = {
            'temperature': round(current['temperature_2m']),
            'code': int(current['weather_code']),
            'wind': round(current.get('wind_speed_10m') or 0),
        }
    except Exception as error:
        log.warning('Hava durumu alınamadı: %s', error)
        weather = None
    with _lock:
        _cache[key] = (time.monotonic(), weather)
    return weather


def get_context(entity, lang='tr', tz='Europe/Istanbul', weather_enabled=True, now=None):
    now = now or datetime.now(ZoneInfo(tz))
    season = season_of(now.month)
    tod = time_of_day(now.hour)
    lang = lang if lang in ('tr', 'en') else 'tr'
    ctx = {
        'season': season,
        'season_label': SEASONS[season][lang],
        'season_icon': SEASONS[season]['icon'],
        'time_of_day': tod,
        'time_label': TIMES_OF_DAY[tod][lang],
        'month_label': MONTHS[lang][now.month - 1],
        'clock': now.strftime('%H:%M'),
        'weather': None,
    }
    if weather_enabled and entity.get('latitude') is not None and entity.get('longitude') is not None:
        weather = fetch_weather(entity['latitude'], entity['longitude'])
        if weather:
            tr_label, en_label, icon = WEATHER_CODES.get(weather['code'], ('değişken', 'changeable', 'wb_cloudy'))
            ctx['weather'] = dict(weather, label=tr_label if lang == 'tr' else en_label, label_tr=tr_label, icon=icon)
    return ctx


def context_prompt(ctx):
    """Sistem promptuna eklenen bağlam bölümü (her zaman Türkçe yönerge; cevap dili ayrıca belirtilir)."""
    tr_season = SEASONS[ctx['season']]['tr']
    tr_time = TIMES_OF_DAY[ctx['time_of_day']]['tr']
    tr_month = MONTHS['tr'][MONTHS['en'].index(ctx['month_label'])] if ctx['month_label'] in MONTHS['en'] else ctx['month_label']
    lines = [
        'ŞU ANKİ ORTAM (bunu yaşıyormuş gibi davran; uygun düştüğünde doğal şekilde değin, her cevapta tekrarlama):',
        f'- Mevsim: {tr_season} ({tr_month} ayı).',
        f'- Günün saati: {tr_time} (saat {ctx["clock"]}).',
    ]
    weather = ctx.get('weather')
    if weather:
        lines.append(f'- Hava: {weather["temperature"]}°C, {weather["label_tr"]}, rüzgâr {weather["wind"]} km/s.')
    lines.append('- Mevsimin ve havanın sana (yapraklarına, çiçeklerine, tüylerine, yüzeyine) etkisini kendi bakış açınla anlatabilirsin.')
    return '\n'.join(lines)
