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
| **AI/LLM** | Google Gemini (akışlı sohbet + Gemini TTS ile karakter sesleri) |
| **QR Kod** | Planlanıyor |

---

## Özellikler

- **Akışlı sohbet:** Cevaplar Gemini'den parça parça gelir; ilk kelimeler ~1 sn'de görünür.
- **Bağlama duyarlı karakterler:** Karakterler mevsimi, günün saatini ve bulundukları yerin anlık havasını (Open-Meteo) bilir.
- **Karakter sesleri:** Her cevabın altında "Dinle" düğmesi; karakterin türüne göre seçilmiş Gemini sesi ve ton yönergesi. Gemini sesi alınamazsa tarayıcı sesi devreye girer. Görme engelliler için otomatik sesli okuma ve ekran okuyucu duyuruları.
- **Açık rıza:** Sohbetten önce onay ekranı. Rıza vermeyenler kayıt olmadan sohbet eder (veriler yalnızca geçici bellekte, 2 saat sonra silinir).
- **Cevap başına mini anket:** 👍 / 👎 ve beğenmeme sebebi.
- **Keşif koleksiyonu:** Tanışılan karakterler ve rozetler (tarayıcıda saklanır).
- **Doğaya yakınlık ölçümü:** Sohbet öncesi ve sonrası tek soruluk "Inclusion of Nature in Self" ölçeği (1-7, iç içe geçen daireler).
- **İsimsiz etkileşim ölçümleri:** Sohbet süresi, ilk mesaja kadar geçen süre, hazır soru / yazılan mesaj, "Dinle" ve bilgi kartı kullanımı, sohbetin nasıl bittiği.
- **Tekrar gelen ziyaretçi:** Rıza verilirse tarayıcıya rastgele bir kod kaydedilir; veritabanında yalnızca tuzlanmış özeti tutulur. (`SECRET_KEY` değişirse eşleşme kopar.)
- **Park rotası:** Sohbet sonunda en yakın (önce tanışılmamış) karakterler, uzaklık ve yürüme yol tarifiyle önerilir; 2 km içindeki komşular karakterin konuşmasına da girer.
- **Doğrulanmış bilgi kartı:** Admin'in girdiği kesin bilgiler "Bilgi kartı" ve "Biliyor muydun?" olarak gösterilir; model rakam verirken bunlara dayanır.
- **Uygunsuz mesaj işaretleme:** Küfür, tehdit, cinsel içerik ve kendine zarar verme ifadeleri işaretlenir, admin panelinde "İncelenecek" olarak görünür. Kendine zarar verme ifadelerinde ziyaretçiye yardım bilgisi (112) gösterilir. Sözlük: `dendrovox/moderation.py`.
- **Çoklu dil:** Türkçe / İngilizce (`translations/en.json`).
- **Yönetim paneli (`/admin`):** Teknik bilgi gerektirmeyen arayüz. Karakter ekleme/düzenleme (haritadan konum, fotoğraf, ses önizleme), sohbetleri okuma/silme, istatistikler, anonim veri indirme (Excel/CSV ve JSON).
- **Gizlilik:** Telefon, e-posta, T.C. kimlik, IBAN ve kart numaraları kaydedilmeden önce maskelenir; dışa aktarımda kimlikler takma kodlarla (K001, S0001) değiştirilir.

---

## Proje Yapısı

```
DendroCore-AI/
├── app.py                    # Geliştirme sunucusu giriş noktası
├── dendrovox/
│   ├── __init__.py           # Uygulama fabrikası (create_app)
│   ├── config.py             # .env ayarları
│   ├── entities.py           # Karakter tohumları, ses profilleri, sistem promptu
│   ├── context.py            # Mevsim / saat / hava durumu
│   ├── llm.py                # Gemini sohbet (akışlı) + TTS, model zinciri ve yeniden deneme
│   ├── storage.py            # Supabase ve bellek depoları
│   ├── privacy.py            # Kişisel veri maskeleme
│   ├── reports.py            # Admin istatistikleri ve anonim dışa aktarım
│   ├── security.py           # Oturum, CSRF, istek sınırı, güvenlik başlıkları
│   ├── i18n.py               # Çoklu dil
│   └── routes/               # pages.py, api.py, admin.py
├── templates/                # Ziyaretçi sayfaları + admin/
├── static/js/                # chat.js, voice.js, collection.js
├── translations/en.json      # İngilizce metinler
├── tests/                    # pytest testleri (+ isteğe bağlı tarayıcı testleri)
└── supabase_setup.sql        # Veritabanı kurulumu / güncellemesi
```

---

## Kurulum

### Gereksinimler

- Python 3.11 veya üzeri

### Adımlar (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # sonra .env dosyasını doldurun
python app.py
```

Tarayıcıda: http://localhost:5000 · Yönetim paneli: http://localhost:5000/admin

### `.env` ayarları

| Değişken | Gerekli | Açıklama |
|----------|---------|----------|
| `SECRET_KEY` | Evet | Uzun rastgele değer: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GEMINI_API_KEY` | Evet | https://aistudio.google.com/apikey (yoksa demo modu) |
| `SUPABASE_URL` | Kayıt için | Supabase proje adresi |
| `SUPABASE_SERVICE_KEY` | Kayıt için | **service_role** (gizli) anahtar. Anon anahtar artık yetmez. |
| `ADMIN_PASSWORD` | Panel için | `/admin` şifresi; boşsa panel kapalı |
| `FLASK_DEBUG` | Hayır | Geliştirirken `1`, gerçek kullanımda `0` |

### Supabase

Supabase panelinde **SQL Editor**'ü açıp `supabase_setup.sql` dosyasının içeriğini çalıştırın. Dosya tekrar çalıştırılabilir ve mevcut verileri silmez; yeni sütunları/tabloları ekler ve herkese açık (anon) erişimi kapatır.

Veritabanı yoksa ya da anahtar yanlışsa uygulama yine çalışır, ancak veriler yalnızca bellekte tutulur ve admin panelinde bir uyarı görünür.

---

## Testler

```powershell
pip install -r requirements-dev.txt
python -m pytest                                   # birim + API + admin testleri

# Gerçek tarayıcıda uçtan uca testler (yüklü Edge kullanılır)
$env:RUN_BROWSER_TESTS = "1"; python -m pytest tests/test_browser.py
```

Yeni bir metin eklediğinizde eksik İngilizce çevirileri görmek için: `python -m tests.i18n_keys`

---

## API

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `POST` | `/api/chat` | `{entity_id, message, conversation_id?, consent, ins_pre?, visitor_id?}` → Server-Sent Events (`meta`, `delta`, `done`) |
| `POST` | `/api/feedback` | `{message_id, rating: 1\|-1, reason?}` (yalnızca rızalı sohbetlerde) |
| `POST` | `/api/survey` | `{conversation_id, value: 1-7}` sohbet sonrası doğaya yakınlık |
| `POST` | `/api/metrics` | `{conversation_id, metrics}` isimsiz etkileşim özeti |
| `POST` | `/api/tts` | `{message_id}` veya `{kind: "welcome", entity_id}` → `audio/wav` |
| `GET` | `/api/entities` | Aktif karakterler |
| `GET` | `/api/context/<entity_id>` | Mevsim / saat / hava |
| `GET` | `/api/stats` | Toplam sohbet ve mesaj sayısı |

Sohbet geçmişi sunucuda tutulur; istemci geçmiş göndermez. Sohbetler yalnızca onları başlatan tarayıcı oturumu tarafından sürdürülebilir.

---

## Akademik Bildirim

Bu proje, insan-bilgisayar etkileşimi ve kentsel ekoloji farkındalığı üzerine deneysel bir araştırma projesidir. Konuşmalar yalnızca katılımcının açık rızasıyla, isimsiz olarak ve akademik araştırma amacıyla kaydedilir.

---

## Lisans

Bu proje akademik kullanım amaçlıdır. Tüm hakları saklıdır.

© 2026 DendroVox Project
