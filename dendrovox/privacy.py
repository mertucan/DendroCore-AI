"""Kişisel verileri metinden ayıklama (KVKK - veri minimizasyonu).

Kullanıcı mesajları kaydedilmeden önce ve dışa aktarımda bu filtreden geçer.
"""

import hashlib
import re

# Sıra önemli: daha uzun/özel kalıplar (IBAN, kart) önce maskelenir.
_PATTERNS = [
    ('[IBAN]', re.compile(r'\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b', re.IGNORECASE)),
    ('[E-POSTA]', re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')),
    ('[KART_NO]', re.compile(r'\b(?:\d{4}[\s-]?){3}\d{4}\b')),
    ('[KIMLIK_NO]', re.compile(r'\b[1-9]\d{10}\b')),
    ('[TELEFON]', re.compile(
        r'(?<![\d(])(?:\+?90[\s-]?)?\(?0?[2-5]\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)')),
]


def mask_pii(text):
    if not text:
        return text
    for placeholder, pattern in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def hash_session(session_id, secret):
    """Oturum kimliği veritabanına açık haliyle değil, gizli anahtarla tuzlanmış özet olarak yazılır."""
    return hashlib.sha256(f'{secret}:{session_id}'.encode()).hexdigest()[:32]
