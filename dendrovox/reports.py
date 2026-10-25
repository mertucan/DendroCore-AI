"""Admin paneli istatistikleri ve anonim araştırma verisi dışa aktarımı."""

import csv
import io
import json
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .privacy import mask_pii

REASON_LABELS = {
    'off_character': 'Karaktere uygun değil',
    'wrong_info': 'Yanlış bilgi',
    'unclear': 'Anlaşılmadı',
    'too_long': 'Çok uzun',
    'other': 'Başka bir sebep',
}


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace('Z', '+00:00')
    # Postgres bazen 5 haneli mikro saniye döndürür; fromisoformat 6 hane ister.
    match = re.match(r'^(.*?)\.(\d+)(.*)$', text)
    if match:
        head, digits, rest = match.groups()
        text = f'{head}.{digits[:6].ljust(6, "0")}{rest}'
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def local_day_range(start_date, end_date, tz):
    """'YYYY-MM-DD' tarih aralığını (yerel saat) UTC ISO sınırlarına çevirir; bitiş günü dahildir."""
    zone = ZoneInfo(tz)
    since = until = None
    if start_date:
        since = datetime.combine(start_date, time.min, zone).astimezone(timezone.utc).isoformat()
    if end_date:
        until = datetime.combine(end_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc).isoformat()
    return since, until


def dashboard_stats(store, entities, tz, days=14, now=None):
    zone = ZoneInfo(tz)
    now = (now or datetime.now(timezone.utc)).astimezone(zone)
    today = now.date()
    since_30, _ = local_day_range(today - timedelta(days=29), None, tz)
    convs, _ = store.query_conversations(since=since_30)

    per_day = Counter()
    per_entity = Counter()
    for conv in convs:
        started = parse_ts(conv['started_at'])
        if started:
            per_day[started.astimezone(zone).date()] += 1
        per_entity[conv['entity_id']] += 1

    feedback = store.feedback_for([c['id'] for c in convs]) if convs else []
    likes = sum(1 for f in feedback if f['rating'] == 1)
    dislikes = sum(1 for f in feedback if f['rating'] == -1)
    reasons = Counter(f['reason'] for f in feedback if f.get('reason'))

    names = {e['id']: e['name'] for e in entities}
    research = research_summary(convs)
    day_series =[{'date': today - timedelta(days=i), 'count': per_day.get(today - timedelta(days=i), 0)}
                  for i in reversed(range(days))]
    top = [{'id': eid, 'name': names.get(eid, eid), 'count': count} for eid, count in per_entity.most_common()]
    total_conversations, total_messages = store.count_totals()
    return {
        'total_conversations': total_conversations,
        'total_messages': total_messages,
        'today': per_day.get(today, 0),
        'week': sum(per_day.get(today - timedelta(days=i), 0) for i in range(7)),
        'month': len(convs),
        'days': day_series,
        'max_day': max([d['count'] for d in day_series] + [1]),
        'by_entity': top,
        'max_entity': max([t['count'] for t in top] + [1]),
        'likes': likes,
        'dislikes': dislikes,
        'like_ratio': round(100 * likes / (likes + dislikes)) if likes + dislikes else None,
        'reasons': [{'label': REASON_LABELS.get(r, r), 'count': c} for r, c in reasons.most_common()],
        'research': research,
        'needs_review': store.query_conversations(limit=1, filters={'flagged': True, 'flag_reviewed': False})[1],
    }


def _mean(values):
    return round(sum(values) / len(values), 1) if values else None


def research_summary(convs):
    """Doğaya yakınlık (öncesi/sonrası), tekrar gelen ziyaretçiler ve etkileşim ölçümlerinin özeti."""
    pre = [c['ins_pre'] for c in convs if c.get('ins_pre')]
    post = [c['ins_post'] for c in convs if c.get('ins_post')]
    pairs = [c['ins_post'] - c['ins_pre'] for c in convs if c.get('ins_pre') and c.get('ins_post')]
    visitors = {}
    for conv in convs:
        if conv.get('visitor_hash'):
            visitors.setdefault(conv['visitor_hash'], set()).add(str(conv['started_at'])[:10])
    metrics = [c['metrics'] for c in convs if isinstance(c.get('metrics'), dict)]
    durations = [m['visible_ms'] / 60000 for m in metrics if m.get('visible_ms')]
    return {
        'pre_avg': _mean(pre),
        'post_avg': _mean(post),
        'change_avg': _mean(pairs),
        'pairs': len(pairs),
        'improved': sum(1 for p in pairs if p > 0),
        'visitors': len(visitors),
        'returning': sum(1 for days in visitors.values() if len(days) > 1),
        'avg_minutes': _mean(durations),
        'listen_share': round(100 * sum(1 for m in metrics if m.get('listens')) / len(metrics)) if metrics else None,
        'measured': len(metrics),
    }


def build_export(store, entities, tz, since=None, until=None, entity_id=None, include_legacy=False):
    """Kişisel bilgilerden arındırılmış, takma kodlu sohbet verisi."""
    zone = ZoneInfo(tz)
    convs, _ = store.query_conversations(entity_id=entity_id, since=since, until=until)
    if not include_legacy:
        convs = [c for c in convs if c.get('consent_version')]
    convs.sort(key=lambda c: c['started_at'])

    # Ziyaretçi kodu varsa (tekrar gelenler) o, yoksa tarayıcı oturumu katılımcıyı belirler.
    def person(conv):
        return conv.get('visitor_hash') or conv['session_id']

    participants = {}
    for conv in convs:
        participants.setdefault(person(conv), f'K{len(participants) + 1:03d}')

    ids = [c['id'] for c in convs]
    messages = store.messages_for(ids) if ids else []
    feedback = {f['message_id']: f for f in (store.feedback_for(ids) if ids else [])}
    by_conv = {}
    for msg in messages:
        by_conv.setdefault(msg['conversation_id'], []).append(msg)

    names = {e['id']: e['name'] for e in entities}
    result = []
    for number, conv in enumerate(convs, start=1):
        started = parse_ts(conv['started_at'])
        msgs = sorted(by_conv.get(conv['id'], []),
                      key=lambda m: (m.get('position') if m.get('position') is not None else 10 ** 6, m.get('created_at') or ''))
        metrics = conv.get('metrics') if isinstance(conv.get('metrics'), dict) else {}
        result.append({
            'participant': participants[person(conv)],
            'visit_number': conv.get('visit_number'),
            'ins_pre': conv.get('ins_pre'),
            'ins_post': conv.get('ins_post'),
            'metrics': metrics,
            'flagged': bool(conv.get('flagged')),
            'conversation': f'S{number:04d}',
            'entity_id': conv['entity_id'],
            'entity_name': names.get(conv['entity_id'], conv['entity_id']),
            'lang': conv.get('lang') or 'tr',
            'consent_version': conv.get('consent_version') or 'eski-bilgilendirme',
            'started_at': started.astimezone(zone).strftime('%Y-%m-%d %H:%M') if started else '',
            'completed': bool(conv.get('is_completed')),
            'messages': [
                {
                    'order': index,
                    'role': 'kullanici' if msg['role'] == 'user' else 'karakter',
                    'text': mask_pii(msg['content']),
                    'rating': feedback.get(msg['id'], {}).get('rating'),
                    'reason': feedback.get(msg['id'], {}).get('reason'),
                    'model': msg.get('model'),
                    'flag': msg.get('flag'),
                }
                for index, msg in enumerate(msgs, start=1)
            ],
        })
    return result


CSV_COLUMNS = ['katilimci_kodu', 'ziyaret_sirasi', 'sohbet_kodu', 'karakter_id', 'karakter_adi', 'dil',
               'riza_surumu', 'sohbet_baslangic', 'sohbet_tamamlandi', 'doga_yakinlik_once', 'doga_yakinlik_sonra',
               'sure_sn', 'hazir_soru', 'yazilan_mesaj', 'dinleme', 'bilgi_karti', 'bitis_sekli',
               'mesaj_sirasi', 'rol', 'mesaj', 'begeni', 'begenmeme_nedeni', 'isaret', 'model']

ENDING_LABELS = {'limit': 'mesaj limiti', 'finish': 'kendisi bitirdi', 'left': 'sayfadan ayrildi'}


def _cell(value):
    """Excel formül enjeksiyonunu önler: =, +, -, @ ile başlayan metinler düz metin olarak yazılır."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def export_csv(conversations):
    """Excel'in Türkçe ayarlarıyla doğrudan açılabilmesi için ';' ayraçlı ve BOM'lu UTF-8."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow(CSV_COLUMNS)
    blank = lambda value: '' if value is None else value  # noqa: E731
    for conv in conversations:
        m = conv['metrics']
        for msg in conv['messages']:
            writer.writerow([_cell(value) for value in [
                conv['participant'], blank(conv['visit_number']), conv['conversation'], conv['entity_id'],
                conv['entity_name'], conv['lang'], conv['consent_version'], conv['started_at'],
                'evet' if conv['completed'] else 'hayir', blank(conv['ins_pre']), blank(conv['ins_post']),
                round(m['visible_ms'] / 1000) if m.get('visible_ms') is not None else '',
                blank(m.get('quick_replies')), blank(m.get('typed')), blank(m.get('listens')),
                blank(m.get('facts_opened')), ENDING_LABELS.get(m.get('ended'), ''),
                msg['order'], msg['role'], msg['text'],
                blank(msg['rating']), REASON_LABELS.get(msg['reason'], msg['reason'] or ''),
                msg['flag'] or '', msg['model'] or '',
            ]])
    return '﻿' + buffer.getvalue()


def export_json(conversations, filters):
    return json.dumps({
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'filters': filters,
        'notes': 'Katılımcı ve sohbet kimlikleri takma kodlarla değiştirilmiştir. Telefon, e-posta, '
                 'kimlik no, IBAN ve kart numaraları maskelenmiştir.',
        'conversations': conversations,
    }, ensure_ascii=False, indent=2)
