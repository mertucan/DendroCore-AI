// Karakter sesi: önce sunucudaki Gemini TTS (karaktere özel ses ve ton), alınamazsa tarayıcının konuşma sentezi.
(function () {
    const cache = new Map(); // anahtar -> ses dosyası (blob URL)
    let audio = null;
    let current = null;       // çalan isteğin kimliği
    let currentState = null;  // çalan isteğin durum geri çağrısı
    let controller = null;
    let resumeTimer = null;

    function stop() {
        const callback = currentState;
        current = null;
        currentState = null;
        if (controller) controller.abort();
        if (audio) {
            audio.pause();
            const done = audio.onended;
            audio = null;
            if (done) done();
        }
        if ('speechSynthesis' in window) speechSynthesis.cancel();
        clearInterval(resumeTimer);
        if (callback) callback(null);
    }

    async function fetchAudio(body, signal) {
        const response = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal,
        });
        if (!response.ok) throw new Error('tts ' + response.status);
        return URL.createObjectURL(await response.blob());
    }

    function playUrl(url) {
        return new Promise((resolve, reject) => {
            audio = new Audio(url);
            audio.onended = () => { audio = null; resolve(); };
            audio.onerror = () => reject(new Error('play'));
            audio.play().catch(reject);
        });
    }

    function pickVoice(locale) {
        const voices = 'speechSynthesis' in window ? speechSynthesis.getVoices() : [];
        const lang = locale.slice(0, 2);
        return voices.find(v => v.lang.replace('_', '-') === locale)
            || voices.find(v => v.lang.toLowerCase().startsWith(lang));
    }

    function speakWithBrowser(text, tone, locale) {
        if (!('speechSynthesis' in window)) return Promise.resolve();
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = locale;
        const voice = pickVoice(locale);
        if (voice) utterance.voice = voice;
        utterance.pitch = (tone && tone.pitch) || 1;
        utterance.rate = (tone && tone.rate) || 0.95;
        return new Promise(resolve => {
            // Chrome uzun metinleri yarıda kesebiliyor; düzenli duraklat/devam et ile önlenir.
            utterance.onstart = () => {
                resumeTimer = setInterval(() => {
                    if (!speechSynthesis.speaking) return clearInterval(resumeTimer);
                    speechSynthesis.pause();
                    speechSynthesis.resume();
                }, 10000);
            };
            utterance.onend = utterance.onerror = () => { clearInterval(resumeTimer); resolve(); };
            speechSynthesis.speak(utterance);
        });
    }

    /**
     * key: önbellek anahtarı, body: /api/tts isteği, text: yedek okuma için metin.
     * onState('loading' | 'playing' | null) düğme durumunu günceller.
     */
    async function play({ key, body, text, tone, locale, onState }) {
        stop();
        const token = {};
        current = token;
        currentState = onState || null;
        controller = new AbortController();
        if (onState) onState('loading');
        try {
            let url = cache.get(key);
            if (!url) {
                url = await fetchAudio(body, controller.signal);
                cache.set(key, url);
            }
            if (current !== token) return;
            if (onState) onState('playing');
            await playUrl(url);
        } catch (error) {
            if (error.name === 'AbortError' || current !== token) return;
            console.warn('Gemini sesi kullanılamadı, tarayıcı sesi kullanılıyor:', error.message);
            if (onState) onState('playing');
            await speakWithBrowser(text, tone, locale);
        } finally {
            if (current === token) {
                current = null;
                currentState = null;
                if (onState) onState(null);
            }
        }
    }

    if ('speechSynthesis' in window) {
        speechSynthesis.getVoices();
        speechSynthesis.addEventListener('voiceschanged', () => speechSynthesis.getVoices());
    }

    window.DendroVoice = { play, stop, speakWithBrowser };
})();
