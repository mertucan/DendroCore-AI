"""Gemini sohbet (akışlı) ve seslendirme (TTS) katmanı."""

import hashlib
import io
import logging
import re
import threading
import time
import wave
from collections import OrderedDict

log = logging.getLogger('dendrovox')

QUOTA_CODES = {429}
MODEL_CODES = {400, 403, 404}
TRANSIENT_CODES = {500, 502, 503, 504}


class LLMUnavailable(Exception):
    """Hiçbir model yanıt veremedi."""


class ContentBlocked(Exception):
    """Model güvenlik nedeniyle boş yanıt döndürdü."""


def error_code(error):
    code = getattr(error, 'code', None)
    if isinstance(code, int):
        return code
    match = re.search(r'\b(4\d\d|5\d\d)\b', str(error))
    return int(match.group(1)) if match else None


def pcm_to_wav(pcm, sample_rate=24000):
    """Gemini TTS 16 bit mono ham PCM döndürür; tarayıcıda çalması için WAV başlığı eklenir."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


class GeminiEngine:
    TTS_CACHE_SIZE = 32

    def __init__(self, api_key, models, tts_models, max_retries=2, retry_delay=1.5, sleep=time.sleep):
        from google import genai
        from google.genai import types
        self.types = types
        self.client = genai.Client(api_key=api_key)
        self.models = list(models)
        self.tts_models = list(tts_models)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.sleep = sleep
        self._tts_model = None
        self._tts_cache = OrderedDict()
        self._lock = threading.Lock()

    def _chat_config(self, model, system_prompt):
        kwargs = {'system_instruction': system_prompt, 'temperature': 0.75, 'max_output_tokens': 400}
        if '2.5-flash' in model and 'lite' not in model:
            kwargs['thinking_config'] = self.types.ThinkingConfig(thinking_budget=0)  # sohbet için hız öncelikli
        return self.types.GenerateContentConfig(**kwargs)

    def stream_reply(self, system_prompt, history, message):
        """('delta', metin) parçaları, en sonda ('model', model_adı) üretir.

        Yeniden deneme ve model değiştirme yalnızca ilk parça gelmeden önce yapılabilir.
        """
        types = self.types
        contents = [
            types.Content(role='user' if m['role'] == 'user' else 'model', parts=[types.Part(text=m['content'])])
            for m in history
        ]
        contents.append(types.Content(role='user', parts=[types.Part(text=message)]))

        last_error = None
        for model in self.models:
            for attempt in range(self.max_retries + 1):
                started = False
                try:
                    stream = self.client.models.generate_content_stream(
                        model=model, contents=contents, config=self._chat_config(model, system_prompt))
                    for chunk in stream:
                        text = chunk.text or ''
                        if text:
                            started = True
                            yield ('delta', text)
                    if not started:
                        raise ContentBlocked()
                    yield ('model', model)
                    return
                except ContentBlocked:
                    raise
                except Exception as error:
                    if started:
                        log.warning('Yanıt yarıda kesildi (%s): %s', model, error)
                        yield ('model', model)
                        return
                    last_error = error
                    code = error_code(error)
                    if code in TRANSIENT_CODES and attempt < self.max_retries:
                        log.warning('Geçici hata (%s, %s), %s. deneme...', model, code, attempt + 2)
                        self.sleep(self.retry_delay * (attempt + 1))
                        continue
                    log.warning('Model kullanılamadı (%s, kod=%s): %s', model, code, error)
                    break  # kota / model yok / kalıcı hata: sıradaki modele geç
        raise LLMUnavailable(str(last_error))

    # ── Seslendirme ──
    def synthesize(self, text, voice_name, style, lang='tr'):
        """WAV baytları döndürür; alınamazsa LLMUnavailable."""
        key = hashlib.sha256(f'{voice_name}|{style}|{text}'.encode()).hexdigest()
        with self._lock:
            if key in self._tts_cache:
                self._tts_cache.move_to_end(key)
                return self._tts_cache[key]

        types = self.types
        candidates = list(dict.fromkeys([m for m in [self._tts_model, *self.tts_models] if m]))
        last_error = None
        for model in candidates:
            for with_voice in (True, False):
                config = {'response_modalities': ['AUDIO']}
                if with_voice:
                    config['speech_config'] = types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)))
                try:
                    response = self.client.models.generate_content(
                        model=model, contents=f'{style}: {text}', config=types.GenerateContentConfig(**config))
                    part = next(p for p in response.candidates[0].content.parts if p.inline_data)
                    mime = part.inline_data.mime_type or 'audio/L16;rate=24000'
                    data = part.inline_data.data
                    if 'wav' not in mime:
                        rate = int((re.search(r'rate=(\d+)', mime) or [None, 24000])[1])
                        data = pcm_to_wav(data, rate)
                    self._tts_model = model
                    with self._lock:
                        self._tts_cache[key] = data
                        while len(self._tts_cache) > self.TTS_CACHE_SIZE:
                            self._tts_cache.popitem(last=False)
                    return data
                except Exception as error:
                    last_error = error
                    code = error_code(error)
                    log.warning('TTS başarısız (%s, ses=%s, kod=%s): %s', model, with_voice, code, error)
                    if code in QUOTA_CODES or code == 404:
                        break  # bu model dolu ya da yok: sıradaki modele geç
        raise LLMUnavailable(str(last_error))


class DemoEngine:
    """GEMINI_API_KEY yokken kullanılır; uygulama yine açılır."""

    models = []

    def stream_reply(self, system_prompt, history, message):
        name = re.search(r'Senin adın "([^"]+)"', system_prompt)
        yield ('delta', f'Ben {name.group(1) if name else "bir doğa varlığı"}. Şu an yapay zekâ bağlantım yok. '
                        'Lütfen .env dosyasına geçerli bir GEMINI_API_KEY ekleyin.')
        yield ('model', 'demo')

    def synthesize(self, text, voice_name, style, lang='tr'):
        raise LLMUnavailable('demo')


def build_engine(config):
    if not config.get('GEMINI_API_KEY'):
        log.warning('GEMINI_API_KEY bulunamadı: demo modunda çalışılıyor.')
        return DemoEngine()
    log.info('Gemini hazır. Modeller: %s', ', '.join(config['GEMINI_MODELS']))
    return GeminiEngine(config['GEMINI_API_KEY'], config['GEMINI_MODELS'], config['GEMINI_TTS_MODELS'],
                        config['MAX_RETRIES'], config['RETRY_DELAY'])
