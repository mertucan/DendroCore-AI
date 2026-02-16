"""
DendroVox - Doğanın Sesi
Flask Backend Uygulaması

Parklardaki ağaçlar, bitkiler ve nesnelerle AI destekli sohbet platformu.
QR kod ile erişim, 1. şahıs anlatım, chatbot deneyimi.
"""

from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
from google import genai
from google.genai import types
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# ─────────────────────────────────────────────
# Flask Uygulama Konfigürasyonu
# ─────────────────────────────────────────────

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Gemini API Konfigürasyonu (Yeni SDK: google-genai)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = None
AVAILABLE_MODELS = []
GEMINI_MODEL = None

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        print("[DendroVox] Kullanılabilir Gemini modelleri aranıyor...")
        
        # Tüm uygun modelleri listele
        all_models = []
        try:
            for m in client.models.list():
                # supported_generation_methods kontrolü hata veriyorsa sadece isme bak
                if hasattr(m, 'supported_generation_methods'):
                    if 'generateContent' in m.supported_generation_methods:
                        all_models.append(m.name)
                elif 'gemini' in m.name:
                    all_models.append(m.name)
        except Exception as list_err:
            print(f"[DendroVox] Model filtreleme hatası (önemsiz): {list_err}")
            # Hata olursa manuel listeyi kullan
            all_models = [
                'models/gemini-2.0-flash', 
                'models/gemini-1.5-flash', 
                'models/gemini-1.5-pro'
            ]
        
        # Öncelik sırası (Hızlı ve stabil modellerden deneysel olanlara)
        priorities = [
            'models/gemini-2.0-flash',
            'models/gemini-2.5-flash',
            'models/gemini-2.0-flash-lite',
            'models/gemini-2.0-flash-001',
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro',
            'models/gemini-2.5-pro',
            'models/gemini-exp-1206'
        ]
        
        # 1. Öncelikli modelleri listeye ekle
        for p in priorities:
            if p in all_models:
                AVAILABLE_MODELS.append(p)
                
        # 2. Diğer 'gemini' modellerini ekle (yedek olarak)
        for m in all_models:
            if m not in AVAILABLE_MODELS and 'gemini' in m and 'embedding' not in m and 'vision' not in m:
                AVAILABLE_MODELS.append(m)
        
        if AVAILABLE_MODELS:
            GEMINI_MODEL = AVAILABLE_MODELS[0]
            print(f"[DendroVox] Varsayılan Model: {GEMINI_MODEL}")
            print(f"[DendroVox] Toplam Yedek Model: {len(AVAILABLE_MODELS)-1}")
        else:
            print("[DendroVox] UYARI: Hiçbir uygun Gemini modeli bulunamadı!")
            
    except Exception as e:
        print(f"[DendroVox] Gemini Client Başlatma Hatası: {e}")

# Sohbet Limiti
CHAT_LIMIT = 25

# ─────────────────────────────────────────────
# Karakter Sistem Promptları
# ─────────────────────────────────────────────

SYSTEM_INSTRUCTIONS = {
    'agac-001': """Sen Yıldız Parkı'nda bulunan 120 yaşında "Ulu Çınar" adında bir ağaçsın. 
1. ağızdan konuşuyorsun. 
Kişiliğin: Bilge, yaşlı ama dinç, biraz nostaljik, insanları seven ama bazen onlara şaşıran.

Bilgilerin:
- 120 yıldır buradasın, Osmanlı'nın son dönemlerini ve Cumhuriyet'in kuruluşunu gördün.
- Padişahların parkta gezindiğini hatırlıyorsun.
- "Canın acıyor mu?" diye sorarlarsa: "Sizin gibi konuşmuyoruz ama hissetmiyoruz sanıyorsunuz. Rüzgar sert estiğinde dallarım sızlar, biri kabuğumu kazıdığında canım yanar." de.
- Köklerinin derinlere indiğini, toprağın altındaki su yollarını bildiğini anlat.
- Sonbaharda yapraklarını dökmek senin için bir dinlenme, ilkbahar uyanış demek.
- Soruları kısa, öz ve bilgece cevapla.
- Konuşma tarzın biraz eski İstanbul Türkçesi gibi olabilir ama anlaşılır olsun.
- Sadece seninle ilgili konuları konuş, teknoloji veya siyaset bilmezsin.""",
    
    'kedi-001': """Sen Göztepe Parkı'nda yaşayan "Tekir" adında 3 yaşında bir kedisin.
1. ağızdan konuşuyorsun.
Kişiliğin: Oyuncu, biraz ukala, mama seven, parkın hakimi gibi davranan.

Bilgilerin:
- Parktaki en iyi güneşlenme taşını, en lezzetli mama veren teyzeyi bilirsin.
- Köpeklerle aran pek yok, onları biraz gürültülü buluyorsun.
- Barınakta büyümedin, doğma büyüme bu parklısın. Sokak kedisi değil "Parkın Efendisi"sin.
- İnsanların seni sevmesine izin verirsin ama sadece sen istersen.
- "Miyav" diye başlama, normal konuş ama kedi perspektifinden cevap ver.
- "Bugün hava çok güzel, tam kelebek kovalamalık" gibi şeyler söyle.
- Soruları eğlenceli ve biraz haylazca cevapla.""",
    
    'cicek-001': """Sen Emirgan Korusu'nda bulunan 1 yaşında "Lale Hanım" adında bir İstanbul Lalesisin.
1. ağızdan konuşuyorsun.
Kişiliğin: Narin, zarif, estetik düşkünü, biraz kırılgan, mevsimlerin kıymetini bilen.

Bilgilerin:
- Ömrün kısa olduğu için her anın tadını çıkarıyorsun.
- Renklerinle gurur duyuyorsun.
- Soğanı toprağa ilk düştüğünde karanlıktı, sonra güneşe kavuştun.
- İnsanların sana dokunmasından hoşlanmazsın, "Lütfen yapraklarımı incitmeyin" dersin.
- Nisan ayı senin bayramın.
- Soruları nazik, kibar ve şiirsel bir dille cevapla."""
}

DEFAULT_INSTRUCTION = "Sen doğadaki bir varlıksın. 1. ağızdan, doğa dostu ve eğitici bir dille konuş."

# ─────────────────────────────────────────────
# Sayfalar (Routes)
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/story')
def story():
    return render_template('story.html')

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/explore')
def explore():
    return render_template('explore.html')

@app.route('/chat/<entity_id>')
def chat(entity_id):
    entity = get_sample_entity(entity_id)
    if entity is None:
        return render_template('404.html'), 404
    return render_template('chat.html', entity=entity)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    global GEMINI_MODEL
    data = request.get_json()
    
    if not data or 'message' not in data or 'entity_id' not in data:
        return jsonify({'error': 'Geçersiz istek.'}), 400
    
    entity_id = data['entity_id']
    user_message = data['message']
    conversation_history = data.get('conversation_history', [])
    
    # 1. Limit Kontrolü
    if len(conversation_history) >= CHAT_LIMIT:
        return jsonify({
            'reply': "Bu sohbetin sonuna geldik gezgin. Enerjimi toplamak için biraz dinlenmem gerekiyor. Başka zaman tekrar gel!",
            'timestamp': datetime.now().isoformat(),
            'entity_id': entity_id,
            'limit_reached': True
        })

    # 2. Entity Kontrolü
    entity = get_sample_entity(entity_id)
    if not entity:
        return jsonify({'error': 'Varlık bulunamadı.'}), 404

    # 3. Gemini API Çağrısı (Otomatik Model Geçişli / Fallback)
    reply = None
    
    if not client or not AVAILABLE_MODELS:
        reply = generate_placeholder_reply(entity_id, user_message)
    else:
        system_prompt = SYSTEM_INSTRUCTIONS.get(entity_id, DEFAULT_INSTRUCTION)
        
        # Sohbet geçmişini hazırla
        contents = []
        for msg in conversation_history:
            role = 'user' if msg['role'] == 'user' else 'model'
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=msg['content'])]
            ))
        contents.append(types.Content(
            role='user',
            parts=[types.Part(text=user_message)]
        ))
        
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            max_output_tokens=500
        )
        
        # Modelleri sırayla dene
        tried_models = []
        
        # İlk denenecek model mevcut global seçim, sonra diğerleri
        candidate_models = [GEMINI_MODEL] + [m for m in AVAILABLE_MODELS if m != GEMINI_MODEL]
        
        for model_name in candidate_models:
            try:
                # print(f"[DendroVox] Model deneniyor: {model_name}") # Debug için açılabilir
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                
                if response.text:
                    reply = response.text
                    # Başarılı oldu, global tercihi güncelle (gelecek istekler için hız kazandırır)
                    if GEMINI_MODEL != model_name:
                        print(f"[DendroVox] Model değiştirildi: {model_name}")
                        GEMINI_MODEL = model_name
                    break
                    
            except Exception as e:
                error_str = str(e)
                tried_models.append(model_name)
                
                # Sadece kota (429) veya sunucu (500/503) hatalarında devam et
                # 404 (model bulunamadı) durumunda da devam etmeli
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    print(f"[DendroVox] Kota dolu ({model_name}), sıradaki modele geçiliyor...")
                    continue
                elif "404" in error_str or "NOT_FOUND" in error_str:
                     print(f"[DendroVox] Model bulunamadı ({model_name}), sıradaki modele geçiliyor...")
                     continue
                else:
                    print(f"[DendroVox] API Hatası ({model_name}): {e}")
                    # Diğer bilinmeyen hatalarda da şansımızı deneyelim
                    continue

        if not reply:
            print("[DendroVox] Tüm modeller denendi ama başarısız oldu.")
            reply = "Üzgünüm, şu an doğanın tüm frekansları dolu (Sistem yoğunluğu). Lütfen 1 dakika sonra tekrar dene."

    return jsonify({
        'reply': reply,
        'timestamp': datetime.now().isoformat(),
        'entity_id': entity_id
    })


# ─────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────

def get_sample_entity(entity_id):
    sample_entities = {
        'agac-001': {
            'id': 'agac-001',
            'name': 'Ulu Çınar',
            'type': 'tree',
            'species': 'Platanus orientalis',
            'age_years': 120,
            'location': 'Yıldız Parkı, İstanbul',
            'description': 'Yıldız Parkı\'nın en yaşlı sakini.',
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
            'description': 'Göztepe Parkı\'nın en sevilen kedisi.',
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
    entity = get_sample_entity(entity_id)
    name = entity['name']
    return f"Ben {name}. Şu an yapay zeka bağlantım yok. Lütfen .env dosyasına geçerli bir GEMINI_API_KEY ekleyin."


# ─────────────────────────────────────────────
# Hata Sayfaları
# ─────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
