# DendroVox - Proje Görev Listesi

> Son güncelleme: 6 Mart 2026

---

## Faz 1: Proje Temeli (MVP)

### Backend Kurulumu
- [x] Flask uygulama yapısını oluştur (`app.py`)
- [x] Proje klasör yapısını oluştur (templates, static, vb.)
- [x] `requirements.txt` hazırla
- [x] `.gitignore` ve `.env.example` oluştur
- [x] `.env` dosyasıyla API key yönetimi
- [x] Hata yönetimi (try/except, retry mekanizması)
- [x] Flask-CORS entegrasyonu yap
- [x] Loglama sistemi kur (dosyaya kayıt)

### Frontend Kurulumu
- [x] Landing page (index.html) - Tailwind CSS ile
- [x] Chat sayfası (chat.html) - Mobil uyumlu
- [x] 404 ve 500 hata sayfaları
- [x] Sayfa ayrımı (story, how_it_works, features, explore)
- [x] Dinamik navbar (scroll efekti, hero sayfası desteği)
- [x] Chat sayfasında mesaj animasyonları (typewriter, slide-in)
- [x] Keşfet sayfası (3 karakter kartı ile)
- [x] Dark mode toggle (localStorage ile kalıcı)
- [x] Mobil responsive son kontroller (hamburger menü)

### QR Kod Sistemi
- [ ] QR kod üretme scripti (her entity için benzersiz QR)
- [ ] QR kod -> Chat sayfası yönlendirme mantığı
- [ ] QR kod tasarımı (DendroVox branding ile)
- [ ] QR kodların fiziksel etiket tasarımı

---

## Faz 2: Veritabanı Entegrasyonu (Supabase)

### Supabase Kurulumu
- [x] Supabase projesi oluştur
- [x] Supabase Python client entegrasyonu
- [x] Ortam değişkenlerini ayarla
- [x] Row Level Security (RLS) politikaları

### Veritabanı Tabloları
- [x] `entities` tablosu (ağaçlar, kediler, bitkiler vb.)
  - id, name, type, species, age_years, location
  - description, personality, backstory
  - latitude, longitude
  - avatar_url, created_at
- [x] `conversations` tablosu (konuşma kayıtları)
  - id, entity_id, session_id
  - started_at, ended_at, is_completed
- [x] `conversation_messages` tablosu (detaylı mesaj kaydı)
  - id, conversation_id, role, content, created_at

### CRUD İşlemleri
- [x] Entity API endpoint (`/api/entities`)
- [x] Konuşma geçmişi kaydetme
- [x] Konuşma istatistikleri sorgulama (`/api/stats`)

---

## Faz 3: AI / Chatbot Entegrasyonu

### LLM Entegrasyonu
- [x] AI provider seçimi: **Google Gemini (gemini-2.0-flash)**
- [x] API entegrasyonu (`google-genai` SDK)
- [x] System prompt tasarımı (1. şahıs anlatım)
- [x] Entity bazlı dinamik prompt oluşturma
- [x] Konuşma geçmişi ile context yönetimi
- [x] Kota aşımı durumunda retry mekanizması

### Prompt Mühendisliği
- [x] Ağaç karakteri prompt şablonu
- [x] Kedi karakteri prompt şablonu
- [x] Bitki/çiçek karakteri prompt şablonu
- [x] Rol sabitleyici (ROLE_ANCHOR) mekanizması
- [x] Genel nesne prompt şablonu (heykel, bank vb.)

### Konuşma Kalitesi
- [x] Rate limiting (25 mesaj sohbet limiti)
- [x] Yanıt uzunluğu optimizasyonu (max 500 token)
- [x] Uygunsuz içerik filtreleme (ROLE_ANCHOR'da)
- [x] Türkçe dil kalitesi kontrolleri (ROLE_ANCHOR'da)

---

## Faz 4: Kullanıcı Deneyimi İyileştirmeleri

### Chat Sayfası
- [x] "Yazıyor..." animasyonu (bounce dots)
- [x] Mesaj balonlarında giriş animasyonları
- [x] Typewriter (harf harf yazma) efekti
- [x] Hoşgeldin mesajı animasyonlu gösterim
- [x] Kalan mesaj sayacı (son 10 mesajda)
- [x] Mesaj balonlarında zaman damgası
- [x] Önerilen sorular butonu (quick replies)
- [x] Sesli mesaj desteği (text-to-speech)

### Landing Page
- [x] Harita entegrasyonu (entity konumları - Leaflet.js)
- [x] Galeri bölümü (doğa fotoğrafları)
- [x] İstatistik gösterimi (toplam konuşma, mesaj sayısı)
- [x] SSS (Sıkça Sorulan Sorular) bölümü

### Genel UX
- [x] Loading/skeleton ekranları (CSS animasyonu)
- [x] Offline durumu bildirimi
- [x] PWA desteği (Progressive Web App)
- [x] SEO optimizasyonu (meta tags, Open Graph)

---

## Faz 5: Admin Panel

- [ ] Admin giriş sayfası (basit auth)
- [ ] Entity yönetimi (CRUD)
- [ ] QR kod üretim arayüzü
- [ ] Konuşma geçmişi görüntüleme
- [ ] Basit analitik dashboard
  - Toplam konuşma sayısı
  - En çok konuşulan entity
  - Günlük/haftalık kullanım grafikleri

---

## Faz 6: Akademik & Yasal

- [x] Akademik kullanım bildirimi (chat sayfasında banner)
- [ ] KVKK uyumu detaylandırması
- [ ] Konuşma kayıt onay mekanizması (açık rıza)
- [ ] Veri anonimleştirme
- [ ] Akademik rapor için veri dışa aktarımı
- [ ] Proje dokümantasyonu (akademik format)

---

## Faz 7: Test & Yayınlama

- [ ] Backend unit testleri
- [ ] Frontend tarayıcı testleri
- [ ] Mobil cihaz testleri (iOS Safari, Android Chrome)
- [ ] QR kod okuma testleri (farklı cihazlar)
- [ ] Performans optimizasyonu
- [ ] Deployment (Render / Railway / vb.)
- [ ] Domain ve SSL ayarları
- [ ] Son kullanıcı testi (gerçek parkta)

---

## Notlar

- **Site adı:** Şimdilik "DendroVox" kullanılıyor, müşteri tarafından değiştirilebilir
- **Kayıt sistemi yok:** Kullanıcılar üye olmadan direkt kullanabilecek
- **Renk teması:** Yeşil doğa temalı (Tailwind CSS ile)
- **Hedef:** Akademik proje olarak kullanılacak, konuşmalar kayıt altına alınacak
- **Veritabanı:** Supabase (entegre edildi)
- **AI Model:** Google Gemini 2.5 Flash Lite (google-genai SDK)
