// Sohbet sayfası: açık rıza, akışlı cevaplar, sesli okuma, mini anket ve keşif koleksiyonu.
(function () {
    const C = window.CHAT;
    const $ = id => document.getElementById(id);

    function t(text, vars) {
        let result = C.strings[text] || text;
        if (vars) Object.keys(vars).forEach(k => { result = result.replace('{' + k + '}', vars[k]); });
        return result;
    }

    const store = {
        get(key) { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } },
        set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* özel gezinme */ } },
    };

    const messages = $('messages-container');
    const form = $('chat-form');
    const input = $('message-input');
    const sendBtn = form.querySelector('button[type="submit"]');
    const typing = $('typing-indicator');
    const quick = $('quick-replies');
    const limitText = $('limit-text');
    const announcer = $('sr-announcer');

    const CONSENT_KEY = 'dendrovox-consent';
    const AUTOREAD_KEY = 'dendrovox-autoread';
    const VISITOR_KEY = 'dendrovox-visitor';

    let conversationId = null;
    let consent = null;
    let waiting = false;
    let ended = false;
    let started = false;
    let finished = false;
    let postAsked = false;
    let factShown = false;
    let exchanged = false;
    let insPre = null;
    let autoRead = store.get(AUTOREAD_KEY) === true;

    // İsimsiz etkileşim ölçümleri (yalnızca rıza varsa gönderilir)
    const openedAt = Date.now();
    const metrics = { quick_replies: 0, typed: 0, listens: 0, facts_opened: 0, route_clicks: 0, visible_ms: 0 };
    let visibleSince = document.visibilityState === 'visible' ? Date.now() : null;

    function uuid() {
        if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    // Tekrar gelen ziyaretçi: rastgele kod yalnızca rıza verilirse oluşturulur, rıza geri çekilirse silinir.
    function visitorId() {
        let id = store.get(VISITOR_KEY);
        if (typeof id !== 'string') {
            id = uuid();
            store.set(VISITOR_KEY, id);
        }
        return id;
    }

    const timeStr = () => new Date().toLocaleTimeString(C.locale, { hour: '2-digit', minute: '2-digit' });
    const scrollToBottom = () => { messages.scrollTop = messages.scrollHeight; };
    const showTyping = () => { typing.classList.remove('hidden'); scrollToBottom(); };
    const hideTyping = () => typing.classList.add('hidden');

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function icon(name, extra) {
        const node = el('span', 'material-icons ' + (extra || 'text-base'), name);
        node.setAttribute('aria-hidden', 'true');
        return node;
    }

    let toastTimer = null;
    function showToast(text, iconName) {
        const toast = $('toast');
        toast.replaceChildren();
        if (iconName) toast.append(icon(iconName, 'text-primary text-lg'));
        toast.append(el('span', '', text));
        toast.classList.remove('hidden');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.add('hidden'), 4000);
    }

    function announce(text) {
        announcer.textContent = '';
        setTimeout(() => { announcer.textContent = text; }, 50);
    }

    // ─── Açık rıza ───
    const modal = $('consent-modal');
    const chip = $('consent-chip');

    function updateChip() {
        chip.classList.remove('hidden');
        chip.textContent = consent ? t('Kayıt açık') : t('Kayıt kapalı');
        chip.className = 'text-[11px] font-semibold px-2 py-1 rounded-full border transition-colors ' + (consent
            ? 'border-primary/40 text-primary-dark dark:text-primary bg-primary/10'
            : 'border-slate-300 text-slate-500 dark:border-white/20 dark:text-slate-300');
    }

    function openConsent() {
        modal.classList.remove('hidden');
        $('consent-yes').focus();
    }

    function choose(value) {
        const changed = consent !== null && consent !== value;
        consent = value;
        store.set(CONSENT_KEY, { version: C.consentVersion, value, at: new Date().toISOString() });
        if (value) visitorId();
        else { try { localStorage.removeItem(VISITOR_KEY); } catch (e) { /* yok say */ } }
        modal.classList.add('hidden');
        updateChip();
        if (changed) conversationId = null; // yeni karar yeni sohbetle geçerli olur
        if (!started) begin();
        else input.focus();
    }

    $('consent-yes').addEventListener('click', () => choose(true));
    $('consent-no').addEventListener('click', () => choose(false));
    chip.addEventListener('click', openConsent);
    modal.addEventListener('keydown', event => {
        // Odak pencere içinde kalır (klavye ve ekran okuyucu kullanıcıları için)
        if (event.key !== 'Tab') return;
        const focusable = modal.querySelectorAll('button, summary, a[href]');
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });

    // ─── Sesli okuma ───
    const autoBtn = $('auto-read-toggle');
    function renderAutoRead() {
        const label = autoRead ? t('Sesli okuma açık') : t('Sesli okuma kapalı');
        autoBtn.setAttribute('aria-pressed', String(autoRead));
        autoBtn.setAttribute('aria-label', label);
        autoBtn.title = label;
        autoBtn.querySelector('.material-icons').textContent = autoRead ? 'volume_up' : 'volume_off';
        autoBtn.classList.toggle('text-primary', autoRead);
        autoBtn.classList.toggle('text-slate-400', !autoRead);
    }
    autoBtn.addEventListener('click', () => {
        autoRead = !autoRead;
        store.set(AUTOREAD_KEY, autoRead);
        if (!autoRead) DendroVoice.stop();
        renderAutoRead();
        showToast(autoRead ? t('Sesli okuma açık') : t('Sesli okuma kapalı'), autoRead ? 'volume_up' : 'volume_off');
    });

    function listenButton(text, key, body) {
        const button = el('button', 'msg-action inline-flex items-center gap-1 text-[11px] font-semibold text-slate-500 dark:text-slate-300 hover:text-primary px-2 py-1 rounded-full hover:bg-primary/10');
        button.type = 'button';
        let state = null;
        const render = () => {
            button.replaceChildren();
            if (state === 'loading') {
                button.append(el('span', 'spinner'), el('span', '', t('Ses hazırlanıyor…')));
            } else if (state === 'playing') {
                button.append(icon('stop_circle'), el('span', '', t('Durdur')));
            } else {
                button.append(icon('volume_up'), el('span', '', t('Dinle')));
            }
            button.setAttribute('aria-pressed', String(state === 'playing'));
        };
        const play = () => DendroVoice.play({
            key, body, text, tone: C.voice, locale: C.locale,
            onState: s => { state = s; render(); },
        });
        button.addEventListener('click', () => {
            if (state) return DendroVoice.stop();
            metrics.listens += 1;
            play();
        });
        render();
        return { button, play };
    }

    // ─── Mini anket (cevap başına) ───
    const REASONS = [
        ['off_character', 'Karaktere uygun değil'],
        ['wrong_info', 'Yanlış bilgi'],
        ['unclear', 'Anlaşılmadı'],
        ['too_long', 'Çok uzun'],
        ['other', 'Başka bir sebep'],
    ];

    function sendFeedback(messageId, rating, reason) {
        return fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId, rating, reason: reason || null }),
        }).catch(() => {});
    }

    function feedbackBlock(messageId) {
        const box = el('div', 'flex flex-wrap items-center gap-1 text-[11px] text-slate-400');
        const thanks = () => {
            box.replaceChildren(icon('favorite', 'text-primary text-sm'), el('span', '', t('Teşekkürler! Görüşün araştırmaya katkı sağlıyor.')));
        };
        const rateButton = (name, label, onClick) => {
            const button = el('button', 'msg-action p-1 rounded-full hover:bg-primary/10 hover:text-primary');
            button.type = 'button';
            button.setAttribute('aria-label', label);
            button.title = label;
            button.append(icon(name, 'text-[16px]'));
            button.addEventListener('click', onClick);
            return button;
        };
        const askReason = () => {
            box.replaceChildren(el('span', 'w-full mb-1', t('Neden beğenmedin?')));
            REASONS.forEach(([code, label]) => {
                const option = el('button', 'msg-action px-2.5 py-1 rounded-full border border-slate-200 dark:border-white/15 hover:border-primary hover:text-primary', t(label));
                option.type = 'button';
                option.addEventListener('click', () => { sendFeedback(messageId, -1, code); thanks(); });
                box.append(option);
            });
            box.querySelector('button').focus();
        };
        box.append(
            el('span', 'mr-1', t('Bu cevap nasıldı?')),
            rateButton('thumb_up', t('Beğendim'), () => { sendFeedback(messageId, 1); thanks(); }),
            rateButton('thumb_down', t('Beğenmedim'), () => { sendFeedback(messageId, -1); askReason(); }),
        );
        return box;
    }

    // ─── Mesajlar ───
    function addUserMessage(text) {
        const row = el('div', 'flex items-end gap-2 justify-end');
        row.style.opacity = '0';
        const wrap = el('div', 'max-w-[80%]');
        const bubble = el('div', 'bg-primary p-3 rounded-2xl rounded-br-none shadow-md');
        bubble.append(el('p', 'text-sm text-background-dark font-medium whitespace-pre-wrap break-words', text));
        const sr = el('span', 'sr-only', t('Sen:') + ' ');
        bubble.prepend(sr);
        wrap.append(bubble, el('p', 'text-[10px] text-slate-400 text-right mt-1 mr-1', timeStr()));
        row.append(wrap);
        messages.append(row);
        requestAnimationFrame(() => row.classList.add('user-enter'));
        scrollToBottom();
    }

    function createBotMessage() {
        const row = el('div', 'flex items-start gap-2');
        row.style.opacity = '0';
        const wrap = el('div', 'max-w-[85%]');
        const bubble = el('div', 'bg-white dark:bg-[#1a382a] p-3 rounded-2xl rounded-bl-none shadow-sm border border-gray-100 dark:border-white/5');
        const textEl = el('p', 'text-sm text-slate-700 dark:text-slate-200 leading-relaxed whitespace-pre-wrap break-words');
        bubble.append(textEl);
        const meta = el('div', 'flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 ml-1');
        meta.append(el('span', 'text-[10px] text-slate-400', timeStr()));
        wrap.append(bubble, meta);
        row.append(wrap);
        messages.append(row);
        requestAnimationFrame(() => row.classList.add('bot-enter'));
        scrollToBottom();
        return { textEl, meta };
    }

    function finishBotMessage(bot, text, { key, body, feedbackId } = {}) {
        announce(t('{name} diyor ki:', { name: C.entity.name }) + ' ' + text);
        let listener = null;
        if (key) {
            listener = listenButton(text, key, body);
            bot.meta.append(listener.button);
        }
        if (feedbackId) bot.meta.append(feedbackBlock(feedbackId));
        scrollToBottom();
        if (autoRead && listener) listener.play();
    }

    function addPlainBotMessage(text) {
        const bot = createBotMessage();
        bot.textEl.textContent = text;
        announce(text);
        return bot;
    }

    function showQuickReplies() {
        const container = quick.querySelector('div');
        container.replaceChildren();
        C.quickReplies.forEach(reply => {
            const button = el('button', 'quick-reply-btn whitespace-nowrap px-3 py-1.5 rounded-full border border-primary/30 bg-primary/5 dark:bg-primary/10 text-primary-dark dark:text-primary text-xs font-medium hover:bg-primary/20', reply);
            button.type = 'button';
            button.addEventListener('click', () => submit(reply, 'quick'));
            container.append(button);
        });
        quick.classList.toggle('hidden', !C.quickReplies.length);
    }

    function updateLimit(remaining) {
        if (remaining > 0 && remaining <= 5) {
            limitText.classList.remove('hidden');
            limitText.textContent = t('{n} mesaj hakkın kaldı', { n: remaining });
        }
    }

    function endConversation() {
        ended = true;
        input.disabled = true;
        input.placeholder = t('Sohbet sonlandı.');
        sendBtn.disabled = true;
        form.classList.add('chat-disabled');
        quick.classList.add('hidden');
        limitText.classList.remove('hidden');
        limitText.textContent = t('Mesaj limiti doldu');
        setTimeout(() => {
            addPlainBotMessage(t('Bu sohbetin mesaj limitine ulaşıldı. Başka bir karakterle konuşmak için Keşfet sayfasına dönebilirsin.'));
            finish('limit');
        }, 500);
    }

    // ─── Doğaya yakınlık ölçeği (öncesi / sonrası) ───
    const insModal = $('ins-modal');
    let insDone = null;

    function openIns(phase, onDone) {
        $('ins-title').textContent = phase === 'pre' ? t('Başlamadan önce tek bir soru') : t('Son olarak tek bir soru');
        $('ins-question').textContent = phase === 'pre'
            ? t('Kendini doğaya ne kadar yakın hissediyorsun? Seni ve doğayı en iyi anlatan resmi seç.')
            : t('Şimdi, bu sohbetten sonra kendini doğaya ne kadar yakın hissediyorsun?');
        insModal.querySelectorAll('.ins-option').forEach(b => b.setAttribute('aria-checked', 'false'));
        insDone = onDone;
        insModal.classList.remove('hidden');
        insModal.querySelector('.ins-option').focus();
    }

    function closeIns(value) {
        insModal.classList.add('hidden');
        const done = insDone;
        insDone = null;
        if (done) done(value);
    }

    insModal.querySelectorAll('.ins-option').forEach(button => {
        button.addEventListener('click', () => {
            button.setAttribute('aria-checked', 'true');
            closeIns(Number(button.dataset.value));
        });
    });
    $('ins-skip').addEventListener('click', () => closeIns(null));
    insModal.addEventListener('keydown', event => {
        // Ok tuşlarıyla seçenekler arasında gezinme
        if (!['ArrowRight', 'ArrowLeft'].includes(event.key)) return;
        const options = [...insModal.querySelectorAll('.ins-option')];
        const index = options.indexOf(document.activeElement);
        if (index < 0) return;
        event.preventDefault();
        options[(index + (event.key === 'ArrowRight' ? 1 : options.length - 1)) % options.length].focus();
    });

    // ─── Bilgi kartı ───
    const factsSheet = $('facts-sheet');
    function openFacts() {
        if (!factsSheet) return;
        metrics.facts_opened += 1;
        factsSheet.classList.remove('hidden');
        $('facts-close').focus();
    }
    if (factsSheet) {
        $('facts-btn').addEventListener('click', openFacts);
        $('facts-close').addEventListener('click', () => { factsSheet.classList.add('hidden'); $('facts-btn').focus(); });
        factsSheet.addEventListener('click', event => { if (event.target === factsSheet) factsSheet.classList.add('hidden'); });
        factsSheet.addEventListener('keydown', event => { if (event.key === 'Escape') factsSheet.classList.add('hidden'); });
    }

    function showFactCard() {
        if (factShown || !C.facts.length) return;
        factShown = true;
        const card = el('div', 'fade-up mx-auto max-w-[90%] rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 p-3 text-sm');
        const title = el('p', 'font-bold text-amber-800 dark:text-amber-300 flex items-center gap-1.5');
        title.append(icon('lightbulb', 'text-lg'), el('span', '', t('Biliyor muydun?')));
        const more = el('button', 'mt-1 text-xs font-semibold text-amber-800 dark:text-amber-300 underline', t('Tüm bilgiler'));
        more.type = 'button';
        more.addEventListener('click', openFacts);
        card.append(title, el('p', 'text-slate-700 dark:text-slate-200 mt-1', C.facts[Math.floor(Math.random() * C.facts.length)]), more);
        messages.append(card);
        scrollToBottom();
    }

    function showSupportCard() {
        const card = el('div', 'fade-up mx-auto max-w-[90%] rounded-2xl border border-sky-200 dark:border-sky-500/30 bg-sky-50 dark:bg-sky-500/10 p-3 text-sm text-slate-700 dark:text-slate-200 flex gap-2');
        card.setAttribute('role', 'note');
        card.append(icon('favorite', 'text-sky-600 text-lg shrink-0'), el('p', '', t('Kendini kötü hissediyorsan yalnız değilsin. Güvendiğin bir yetişkinle konuşabilir, acil bir durumda 112\'yi arayabilirsin.')));
        messages.append(card);
        announce(card.textContent);
        scrollToBottom();
    }

    // ─── Park rotası ───
    function formatDistance(meters) {
        const format = new Intl.NumberFormat(C.locale, { maximumFractionDigits: 1 });
        return meters < 1000 ? `${Math.round(meters / 10) * 10} m` : `${format.format(meters / 1000)} km`;
    }

    function showRoute() {
        const card = el('section', 'fade-up rounded-2xl border border-primary/30 bg-white dark:bg-[#1a382a] p-4 shadow-sm');
        card.setAttribute('aria-label', t('Sıradaki durak'));
        const title = el('p', 'font-bold text-slate-900 dark:text-white flex items-center gap-1.5');
        title.append(icon('route', 'text-primary text-xl'), el('span', '', t('Sıradaki durak')));
        card.append(title);
        // Henüz tanışılmamış karakterler öne alınır.
        const met = id => window.DendroCollection && DendroCollection.has(id);
        const stops = [...C.route].sort((a, b) => met(a.id) - met(b.id)).slice(0, 2);
        if (!stops.length) {
            card.append(el('p', 'text-sm text-slate-600 dark:text-slate-300 mt-1', t('Yeni karakterlerle tanışmak için Keşfet sayfasına göz at.')));
            const link = el('a', 'inline-flex mt-3 px-4 py-2 rounded-full bg-primary text-background-dark text-sm font-bold', t('Keşfet sayfasına dön'));
            link.href = '/explore';
            card.append(link);
        } else {
            card.append(el('p', 'text-sm text-slate-600 dark:text-slate-300 mt-0.5 mb-3', t('Parkta seni bekleyen başka sakinler de var.')));
        }
        stops.forEach(stop => {
            const row = el('div', 'flex items-center gap-3 py-2 border-t border-slate-100 dark:border-white/10');
            const thumb = el('div', 'w-12 h-12 rounded-xl overflow-hidden bg-primary/15 flex items-center justify-center shrink-0');
            if (stop.image_url) {
                const img = el('img', 'w-full h-full object-cover');
                img.src = stop.image_url;
                img.alt = '';
                thumb.append(img);
            } else {
                thumb.append(icon(stop.icon, 'text-primary text-2xl'));
            }
            const info = el('div', 'flex-1 min-w-0');
            const name = el('p', 'font-semibold text-sm text-slate-900 dark:text-white truncate', stop.name);
            if (met(stop.id)) name.append(el('span', 'ml-1 text-[10px] text-primary-dark dark:text-primary', '✓ ' + t('Tanıştın')));
            const distance = stop.distance_m > 2000
                ? t('Başka bir parkta · {distance}', { distance: formatDistance(stop.distance_m) })
                : t('{distance} uzakta', { distance: formatDistance(stop.distance_m) });
            info.append(name, el('p', 'text-xs text-slate-500 dark:text-slate-400 truncate', distance));
            const actions = el('div', 'flex flex-col gap-1 shrink-0');
            const go = el('a', 'px-3 py-1.5 rounded-full bg-primary text-background-dark text-xs font-bold text-center', t('Sohbete başla'));
            go.href = '/chat/' + encodeURIComponent(stop.id);
            const directions = el('a', 'px-3 py-1.5 rounded-full border border-slate-200 dark:border-white/15 text-xs font-semibold text-center', t('Yol tarifi'));
            directions.href = `https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&route=${C.entity.latitude}%2C${C.entity.longitude}%3B${stop.latitude}%2C${stop.longitude}`;
            directions.target = '_blank';
            directions.rel = 'noopener';
            [go, directions].forEach(a => a.addEventListener('click', () => { metrics.route_clicks += 1; sendMetrics(); }));
            actions.append(go, directions);
            row.append(thumb, info, actions);
            card.append(row);
        });
        messages.append(card);
        scrollToBottom();
    }

    // ─── Sohbeti bitirme ───
    function finish(reason, after) {
        if (finished) { if (after) after(); return; }
        finished = true;
        metrics.ended = reason;
        if (!ended) {
            ended = true;
            input.disabled = true;
            input.placeholder = t('Sohbet sonlandı.');
            sendBtn.disabled = true;
            form.classList.add('chat-disabled');
            quick.classList.add('hidden');
        }
        $('finish-btn').classList.add('hidden');
        DendroVoice.stop();
        const wrapUp = () => { showRoute(); sendMetrics(); if (after) after(); };
        if (consent && conversationId && !postAsked) {
            postAsked = true;
            openIns('post', value => {
                if (value) {
                    fetch('/api/survey', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ conversation_id: conversationId, value }),
                    }).catch(() => {});
                }
                wrapUp();
            });
        } else {
            wrapUp();
        }
    }

    $('finish-btn').addEventListener('click', () => finish('finish'));
    $('back-link').addEventListener('click', event => {
        // Sohbet edildiyse çıkmadan önce son soru sorulur.
        if (!exchanged || finished || !consent) return;
        event.preventDefault();
        const target = event.currentTarget.href;
        finish('left', () => { setTimeout(() => { window.location.href = target; }, 300); });
    });

    // ─── Ölçümlerin gönderilmesi ───
    function sendMetrics() {
        if (!consent || !conversationId) return;
        if (visibleSince) { metrics.visible_ms += Date.now() - visibleSince; visibleSince = Date.now(); }
        const payload = { conversation_id: conversationId, metrics: { ...metrics, auto_read: autoRead, ended: metrics.ended || 'left' } };
        const body = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        if (!(navigator.sendBeacon && navigator.sendBeacon('/api/metrics', body))) {
            fetch('/api/metrics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), keepalive: true }).catch(() => {});
        }
    }

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            sendMetrics();
            visibleSince = null;
        } else {
            visibleSince = Date.now();
        }
    });
    window.addEventListener('pagehide', sendMetrics);

    function rememberMeeting() {
        if (!window.DendroCollection || !DendroCollection.add(C.entity.id)) return;
        const total = Math.max(C.entityTotal, DendroCollection.count());
        showToast(t('Yeni bir tanışıklık! Koleksiyonuna eklendi.') + ' ' +
            t('Koleksiyon: {count}/{total}', { count: DendroCollection.count(), total }), 'verified');
    }

    // ─── Akışlı cevap (Server-Sent Events) ───
    async function readStream(response, onEvent) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let index;
            while ((index = buffer.indexOf('\n\n')) >= 0) {
                const raw = buffer.slice(0, index);
                buffer = buffer.slice(index + 2);
                const line = raw.split('\n').find(l => l.startsWith('data: '));
                if (line) onEvent(JSON.parse(line.slice(6)));
            }
        }
    }

    async function send(message, retried) {
        waiting = true;
        sendBtn.disabled = true;
        showTyping();
        try {
            const body = { entity_id: C.entity.id, message, conversation_id: conversationId, consent: consent === true };
            if (!conversationId && consent) {
                body.ins_pre = insPre;
                body.visitor_id = visitorId();
            }
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const type = response.headers.get('Content-Type') || '';
            if (!type.includes('text/event-stream')) {
                const data = await response.json().catch(() => ({}));
                hideTyping();
                if (data.code === 'conversation_not_found' && !retried) {
                    conversationId = null;
                    showToast(t('Bu sohbet artık geçerli değil, yeni bir sohbet başlatıldı.'), 'refresh');
                    return send(message, true);
                }
                if (data.limit_reached) {
                    addPlainBotMessage(data.reply);
                    endConversation();
                    return;
                }
                addPlainBotMessage(data.error || t('Hmm, bir sorun oldu. Tekrar dener misin?'));
                return;
            }

            let bot = null;
            let text = '';
            let final = null;
            await readStream(response, event => {
                if (event.type === 'meta') {
                    conversationId = event.conversation_id;
                } else if (event.type === 'delta') {
                    if (!bot) { hideTyping(); bot = createBotMessage(); }
                    text += event.text;
                    text = text.replace(/\*\*|__/g, ''); // model bazen Markdown kalın yazı kullanır
                    bot.textEl.textContent = text;
                    scrollToBottom();
                } else if (event.type === 'done') {
                    final = event;
                }
            });
            hideTyping();
            if (!bot || !final) {
                addPlainBotMessage(t('Hmm, bir sorun oldu. Tekrar dener misin?'));
                return;
            }
            finishBotMessage(bot, text, final.message_id ? {
                key: 'm:' + final.message_id,
                body: { message_id: final.message_id },
                feedbackId: consent && !final.fallback ? final.message_id : null,
            } : {});
            if (final.support) showSupportCard();
            if (!final.fallback) {
                rememberMeeting();
                exchanged = true;
                showFactCard();
            }
            if (exchanged && !final.limit_reached) $('finish-btn').classList.remove('hidden');
            updateLimit(final.remaining);
            if (final.limit_reached) endConversation();
        } catch (error) {
            hideTyping();
            addPlainBotMessage(t('Bağlantı hatası oluştu. Lütfen tekrar deneyin.'));
            console.error('Chat API error:', error);
        } finally {
            waiting = false;
            if (!ended) sendBtn.disabled = false;
        }
    }

    function submit(text, source) {
        const message = (text || '').trim();
        if (!message || waiting || ended || consent === null) return;
        if (metrics.first_message_ms === undefined) metrics.first_message_ms = Date.now() - openedAt;
        metrics[source === 'quick' ? 'quick_replies' : 'typed'] += 1;
        DendroVoice.stop();
        addUserMessage(message);
        input.value = '';
        quick.classList.add('hidden');
        send(message);
    }

    form.addEventListener('submit', event => {
        event.preventDefault();
        submit(input.value, 'typed');
    });

    // ─── Bağlam şeridi ───
    function loadContext() {
        fetch('/api/context/' + encodeURIComponent(C.entity.id)).then(r => (r.ok ? r.json() : null)).then(ctx => {
            if (!ctx) return;
            const strip = $('context-strip');
            const cap = s => s.charAt(0).toLocaleUpperCase(C.locale) + s.slice(1);
            const item = (iconName, text) => {
                const span = el('span', 'inline-flex items-center gap-1');
                span.append(icon(iconName, 'text-sm text-primary-dark dark:text-primary'), el('span', '', text));
                return span;
            };
            strip.append(item(ctx.season_icon, cap(ctx.season_label)), item('schedule', cap(ctx.time_label)));
            if (ctx.weather) strip.append(item(ctx.weather.icon, `${ctx.weather.temperature}°C · ${ctx.weather.label}`));
            strip.classList.remove('hidden');
            strip.classList.add('flex');
        }).catch(() => {});
    }

    // ─── Başlangıç ───
    // Rıza varsa sohbetten önce doğaya yakınlık sorulur (geçilebilir).
    function begin() {
        started = true;
        if (!consent) return start();
        openIns('pre', value => { insPre = value; start(); });
    }

    function start() {
        started = true;
        // Karşılama gelene kadar mesaj gönderilemez (aksi halde karşılama cevabın arkasına düşer).
        waiting = true;
        sendBtn.disabled = true;
        setTimeout(() => {
            showTyping();
            setTimeout(() => {
                hideTyping();
                waiting = false;
                if (!ended) sendBtn.disabled = false;
                const bot = createBotMessage();
                bot.textEl.textContent = C.welcome;
                finishBotMessage(bot, C.welcome, { key: 'welcome:' + C.entity.id + ':' + C.lang, body: { kind: 'welcome', entity_id: C.entity.id } });
                showQuickReplies();
            }, 700 + Math.random() * 500);
        }, 300);
    }

    renderAutoRead();
    loadContext();
    const saved = store.get(CONSENT_KEY);
    if (saved && saved.version === C.consentVersion && typeof saved.value === 'boolean') {
        consent = saved.value;
        updateChip();
        begin();
    } else {
        openConsent();
    }

    const offlineBanner = $('offline-banner');
    window.addEventListener('offline', () => offlineBanner.classList.remove('hidden'));
    window.addEventListener('online', () => offlineBanner.classList.add('hidden'));

    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js').catch(() => {});
    }
})();
