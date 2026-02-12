# DendroVox - Doğanın Sesi

> Parklardaki ağaçlara, bitkilere ve nesnelere yapay zeka ile ses veren interaktif sohbet platformu.

---

## Proje Hakkında

**DendroVox**, parklardaki doğal ve yapay nesnelere (ağaçlar, bitkiler, kedi evleri vb.) QR kod aracılığıyla erişilebilen, yapay zeka destekli bir sohbet platformudur. Kullanıcılar QR kodu taratarak ilgili nesneyle 1. şahıs ağzından sohbet edebilir.

Proje, **insan-bilgisayar etkileşimi** ve **kentsel ekoloji farkındalığı** üzerine bir akademik araştırma çalışmasıdır.

### Temel Konsept

- Parktaki bir ağacın üzerindeki QR kodu taratıyorsunuz
- Ağaç kendini 1. şahıs olarak tanıtıyor: *"Merhaba! Ben bu parkın en yaşlısıyım. 120 yıldır buradayım..."*
- Sohbet edebiliyorsunuz: tarihsel bilgiler, mevsimsel değişimler, duygusal tepkiler
- Kayıt/üyelik gerektirmiyor, tamamen web tabanlı

### Desteklenen Varlık Türleri

| Tür | Açıklama | Örnek |
|-----|----------|-------|
| Ağaçlar | Yüzlerce yıllık tanıklıklar, tarihsel anlatım | Çınar, Meşe, Kavak |
| Bitkiler | Mevsimsel döngüler, biyolojik bilgiler | Lale, Nilüfer, Gül |
| Kedi Evleri | Park kedilerinin günlük macerları (kedinin ağzından) | Tekir, Sarman |
| Diğer | Heykeller, banklar, çeşmeler vb. | Park heykeli |

---

## Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| **Backend** | Python 3.11+ / Flask |
| **Frontend** | HTML5, Tailwind CSS, Vanilla JS |
| **Veritabanı** | Supabase (PostgreSQL) |
| **AI/LLM** | Henüz belirlenmedi (OpenAI / Gemini / Anthropic) |
| **QR Kod** | Dinamik QR kod sistemi |

---

## Proje Yapısı

```
DendroCore-AI/
├── app.py                  # Ana Flask uygulaması
├── requirements.txt        # Python bağımlılıkları
├── .env.example            # Ortam değişkenleri şablonu
├── .gitignore
├── README.md               # Bu dosya
├── tasks.md                # Proje görev takibi
│
├── templates/              # HTML şablonları (Jinja2)
│   ├── index.html          # Landing page
│   ├── chat.html           # Sohbet sayfası
│   ├── 404.html            # Sayfa bulunamadı
│   └── 500.html            # Sunucu hatası
│
└── static/                 # Statik dosyalar
    ├── css/                # Ek stil dosyaları
    ├── js/                 # JavaScript dosyaları
    └── images/             # Görseller, avatarlar
```

---

## Kurulum

### Gereksinimler

- Python 3.11 veya üzeri
- pip (Python paket yöneticisi)

### Adımlar

1. **Repoyu klonlayın:**
   ```bash
   git clone https://github.com/kullanici/DendroCore-AI.git
   cd DendroCore-AI
   ```

2. **Sanal ortam oluşturun:**
   ```bash
   python -m venv venv

   # Windows
   venv\Scripts\activate

   # macOS / Linux
   source venv/bin/activate
   ```

3. **Bağımlılıkları yükleyin:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Ortam değişkenlerini ayarlayın:**
   ```bash
   copy .env.example .env
   # .env dosyasını düzenleyip değişkenleri doldurun
   ```

5. **Uygulamayı başlatın:**
   ```bash
   python app.py
   ```

6. **Tarayıcıda açın:**
   ```
   http://localhost:5000
   ```

---

## Kullanım Akışı

```
QR Kod Tarat  →  Chat Sayfası Açılır  →  Entity Kendini Tanıtır  →  Sohbet Başlar
                                                                         ↓
                                                              Konuşma Kaydedilir
                                                              (Akademik Araştırma)
```

### Örnek Sohbet

> **Ulu Çınar:** Merhaba gezgin! Ben bu parkın en yaşlısıyım. Tam 120 yıldır buradayım. Yapraklarımda hissettiğim rüzgarın hikayesini duymak ister misin?
>
> **Kullanıcı:** Buraya ilk dikildiğinde etraf nasıldı?
>
> **Ulu Çınar:** O zamanlar buralar hep tarlaydı... Hemen yanımdaki şu beton yolun olduğu yerden küçük bir dere akardı. Sincap dostlarım o dereden su içerdi.

---

## API Endpoints

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/` | Ana sayfa (landing page) |
| `GET` | `/chat/<entity_id>` | Entity ile sohbet sayfası |
| `POST` | `/api/chat` | Chat API (mesaj gönder/al) |

### POST `/api/chat`

**Request:**
```json
{
    "entity_id": "agac-001",
    "message": "Merhaba, kaç yaşındasın?",
    "conversation_history": []
}
```

**Response:**
```json
{
    "reply": "Ben tam 120 yaşındayım! Yıldız Parkı bölgesinde uzun süredir buradayım.",
    "timestamp": "2026-02-12T14:30:00",
    "entity_id": "agac-001"
}
```

---

## Akademik Bildirim

Bu proje, insan-bilgisayar etkileşimi ve kentsel ekoloji farkındalığı üzerine deneysel bir araştırma projesidir. Platform üzerinden gerçekleştirilen konuşmalar, akademik araştırma amacıyla anonim olarak kayıt altına alınmaktadır. Kullanıcılar platforma erişerek bu durumu kabul etmiş sayılırlar.

---

## Lisans

Bu proje akademik kullanım amaçlıdır. Tüm hakları saklıdır.

© 2026 DendroVox Project
