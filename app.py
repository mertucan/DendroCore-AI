"""
DendroVox - Doğanın Sesi
Flask Backend Uygulaması

Parklardaki ağaçlar, bitkiler ve nesnelerle AI destekli sohbet platformu.
QR kod ile erişim, 1. şahıs anlatım, chatbot deneyimi.
"""

from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime

# ─────────────────────────────────────────────
# Flask Uygulama Konfigürasyonu
# ─────────────────────────────────────────────

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# ─────────────────────────────────────────────
# Sayfalar (Routes)
# ─────────────────────────────────────────────

@app.route('/')
def index():
    """Ana sayfa - Landing page"""
    return render_template('index.html')


@app.route('/chat/<entity_id>')
def chat(entity_id):
    """
    Sohbet sayfası - QR kod tarandıktan sonra yönlendirilecek sayfa.
    entity_id: Ağaç, bitki veya nesnenin benzersiz kimliği.
    """
    # TODO: Supabase'den entity bilgilerini çek
    # Şimdilik örnek veri kullanıyoruz
    entity = get_sample_entity(entity_id)
    
    if entity is None:
        return render_template('404.html'), 404
    
    return render_template('chat.html', entity=entity)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    Chat API endpoint - Kullanıcı mesajlarını alır, AI yanıtı döndürür.
    
    Request body:
        - entity_id: str - Konuşulan varlığın ID'si
        - message: str - Kullanıcının mesajı
        - conversation_history: list - Önceki mesajlar (opsiyonel)
    
    Response:
        - reply: str - AI tarafından üretilen yanıt
        - timestamp: str - Yanıt zamanı
    """
    data = request.get_json()
    
    if not data or 'message' not in data or 'entity_id' not in data:
        return jsonify({'error': 'Geçersiz istek. message ve entity_id gerekli.'}), 400
    
    entity_id = data['entity_id']
    user_message = data['message']
    conversation_history = data.get('conversation_history', [])
    
    # TODO: AI entegrasyonu yapılacak (OpenAI / Gemini / vb.)
    # TODO: Supabase'den entity verilerini çek
    # TODO: Konuşma geçmişini Supabase'e kaydet
    
    # Şimdilik placeholder yanıt
    reply = generate_placeholder_reply(entity_id, user_message)
    
    return jsonify({
        'reply': reply,
        'timestamp': datetime.now().isoformat(),
        'entity_id': entity_id
    })


# ─────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────

def get_sample_entity(entity_id):
    """
    Geçici örnek veri döndürür.
    Supabase entegrasyonunda bu fonksiyon veritabanı sorgusuyla değiştirilecek.
    """
    sample_entities = {
        'agac-001': {
            'id': 'agac-001',
            'name': 'Ulu Çınar',
            'type': 'tree',
            'species': 'Platanus orientalis',
            'age_years': 120,
            'location': 'Yıldız Parkı, İstanbul',
            'description': 'Yıldız Parkı\'nın en yaşlı sakini. 120 yıldır burada tanıklık ediyor.',
            'avatar': '/static/images/default-tree-avatar.png',
            'personality': 'Bilge, sıcak, hikaye anlatmayı seven'
        },
        'kedi-001': {
            'id': 'kedi-001',
            'name': 'Tekir',
            'type': 'cat',
            'species': 'Felis catus',
            'age_years': 3,
            'location': 'Göztepe Parkı, İstanbul',
            'description': 'Göztepe Parkı\'nın en sevilen kedisi. Herkesle arkadaş.',
            'avatar': '/static/images/default-cat-avatar.png',
            'personality': 'Meraklı, oyuncu, biraz ukala'
        },
        'cicek-001': {
            'id': 'cicek-001',
            'name': 'Lale Hanım',
            'type': 'flower',
            'species': 'Tulipa',
            'age_years': 1,
            'location': 'Emirgan Korusu, İstanbul',
            'description': 'İstanbul\'un simgesi lalelerin temsilcisi.',
            'avatar': '/static/images/default-flower-avatar.png',
            'personality': 'Zarif, kibar, biraz dramatik'
        }
    }
    
    return sample_entities.get(entity_id)


def generate_placeholder_reply(entity_id, user_message):
    """
    AI entegrasyonu yapılana kadar kullanılacak placeholder yanıt üretici.
    """
    entity = get_sample_entity(entity_id)
    
    if entity is None:
        return "Hmm, beni tanıyamadım. Sanırım bir karışıklık var."
    
    name = entity['name']
    
    # Basit anahtar kelime bazlı yanıtlar (placeholder)
    message_lower = user_message.lower()
    
    if any(word in message_lower for word in ['merhaba', 'selam', 'hey', 'naber']):
        return f"Merhaba gezgin! Ben {name}. Buraya geldiğine çok sevindim! Sana neler anlatayım..."
    
    if any(word in message_lower for word in ['yaş', 'kaç yaşında', 'ne zamandan']):
        return f"Ben tam {entity['age_years']} yaşındayım! {entity['location']} bölgesinde uzun süredir buradayım."
    
    if any(word in message_lower for word in ['acı', 'ağrı', 'canın']):
        return "Sizin gibi konuşmuyoruz ama hissetmiyoruz sanmayın... Rüzgar sert estiğinde dallarım sızlar, birisi kabığıma bir şey kazıdığında ise... neyse, anlatması zor."
    
    if any(word in message_lower for word in ['nerelisin', 'köken', 'nereden']):
        return f"Tür olarak benim köklerim çok eskilere dayanıyor. Ama ben burada, {entity['location']} bölgesinde doğdum ve büyüdüm."
    
    return f"Çok güzel bir soru! AI entegrasyonu tamamlandığında sana çok daha detaylı cevaplar verebileceğim. Şimdilik buradayım, {name} olarak seninleyim."


# ─────────────────────────────────────────────
# Hata Sayfaları
# ─────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    """404 - Sayfa bulunamadı"""
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    """500 - Sunucu hatası"""
    return render_template('500.html'), 500


# ─────────────────────────────────────────────
# Uygulama Başlatma
# ─────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
