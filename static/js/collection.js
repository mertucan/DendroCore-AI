// Keşif koleksiyonu: ziyaretçinin tanıştığı karakterler bu tarayıcıda saklanır (üyelik gerekmez).
(function () {
    const KEY = 'dendrovox-collection';

    function read() {
        try {
            const data = JSON.parse(localStorage.getItem(KEY) || '{}');
            return data && typeof data === 'object' ? data : {};
        } catch (e) {
            return {};
        }
    }

    // Rozet seviyeleri: tanışılan karakter sayısına göre.
    const BADGES = [
        { min: 1, icon: 'spa', key: 'Filiz' },
        { min: 3, icon: 'grass', key: 'Fidan' },
        { min: 5, icon: 'park', key: 'Ulu Ağaç' },
    ];

    window.DendroCollection = {
        all: read,
        has(id) { return Boolean(read()[id]); },
        // Yeni eklendiyse true döner.
        add(id) {
            const data = read();
            if (data[id]) return false;
            data[id] = new Date().toISOString();
            try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (e) { return false; }
            return true;
        },
        count(validIds) {
            const data = read();
            return validIds ? validIds.filter(id => data[id]).length : Object.keys(data).length;
        },
        badge(count, total) {
            if (total > 0 && count >= total) return { icon: 'forest', key: 'Orman Bekçisi' };
            let current = null;
            BADGES.forEach(b => { if (count >= b.min) current = b; });
            return current;
        },
    };
})();
