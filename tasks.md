# DendroVox - Proje Görev Listesi

> Son güncelleme: 12 Şubat 2026

---

## Faz 1: Proje Temeli (MVP)

### Backend Kurulumu
- [x] Flask uygulama yapısını oluştur (`app.py`)
- [x] Proje klasör yapısını oluştur (templates, static, vb.)
- [x] `requirements.txt` hazırla
- [x] `.gitignore` ve `.env.example` oluştur
- [ ] Flask-CORS entegrasyonu yap
- [ ] Hata yönetimi ve loglama sistemi kur

### Frontend Kurulumu
- [x] Landing page (index.html) - Tailwind CSS ile
- [x] Chat sayfası (chat.html) - Mobil uyumlu
- [x] 404 ve 500 hata sayfaları
- [ ] Dark mode toggle (şu an sadece dark mode)
- [ ] Mobil responsive son kontroller
- [ ] Chat sayfasında mesaj animasyonları iyileştir

### QR Kod Sistemi
- [ ] QR kod üretme scripti (her entity için benzersiz QR)
- [ ] QR kod -> Chat sayfası yönlendirme mantığı
- [ ] QR kod tasarımı (DendroVox branding ile)
- [ ] QR kodların fiziksel etiket tasarımı

---

## Faz 2: Veritabanı Entegrasyonu (Supabase)

### Supabase Kurulumu
- [ ] Supabase projesi oluştur
- [ ] Supabase Python client entegrasyonu
- [ ] Ortam değişkenlerini ayarla

### Veritabanı Tabloları
- [ ] `entities` tablosu (ağaçlar, kediler, bitkiler vb.)
  - id, name, type, species, age_years, location
  - description, personality, backstory
  - latitude, longitude
  - avatar_url, created_at
- [ ] `conversations` tablosu (konuşma kayıtları)
  - id, entity_id, session_id
  - messages (JSON), started_at, ended_at
- [ ] `conversation_messages` tablosu (detaylı mesaj kaydı)
  - id, conversation_id, role, content, timestamp

### CRUD İşlemleri
- [ ] Entity ekleme/düzenleme/silme (admin panel için)
- [ ] Konuşma geçmişi kaydetme
- [ ] Konuşma istatistikleri sorgulama

---

## Faz 3: AI / Chatbot Entegrasyonu

### LLM Entegrasyonu
- [ ] AI provider seçimi (OpenAI / Gemini / Anthropic)
- [ ] API entegrasyonu
- [ ] System prompt tasarımı (1. şahıs anlatım)
- [ ] Entity bazlı dinamik prompt oluşturma
- [ ] Konuşma geçmişi ile context yönetimi

### Prompt Mühendisliği
- [ ] Ağaç karakteri prompt şablonu
  - Tarihsel bilgi anlatımı (padişahlar, olaylar)
  - Mevsimsel farkındalık (yaprak dökümü, çiçek açma)
  - Duygusal tepkiler ("canın acıyor mu?" -> "hissetmiyoruz sanıyorsunuz")
  - Köken bilgisi ("kökenim Arjantin'e dayalı")
  - Yaş ve deneyim bilgisi
- [ ] Kedi karakteri prompt şablonu
  - 1. ağızdan kedi dili (barınakla değil, kedinin ağzından)
  - Günlük maceralar, park yaşamı
  - Meraklı ve oyuncu kişilik
- [ ] Bitki/çiçek karakteri prompt şablonu
  - Lale, nilüfer vb. tipik bitkiler
  - Mevsimsel döngü bilgisi
  - Zarif ve kibar kişilik
- [ ] Genel nesne prompt şablonu (heykel, bank vb.)

### Konuşma Kalitesi
- [ ] Rate limiting (aşırı kullanım önleme)
- [ ] Uygunsuz içerik filtreleme
- [ ] Yanıt uzunluğu optimizasyonu
- [ ] Türkçe dil kalitesi kontrolleri

---

## Faz 4: Kullanıcı Deneyimi İyileştirmeleri

### Chat Sayfası
- [ ] Mesaj balonlarında zaman damgası
- [ ] "Yazıyor..." animasyonu iyileştirmesi
- [ ] Mesaj geçmişi (scroll-up ile eski mesajlar)
- [ ] Önerilen sorular butonu (quick replies)
- [ ] Sesli mesaj desteği (text-to-speech)
- [ ] Emoji desteği

### Landing Page
- [ ] Harita entegrasyonu (entity konumları)
- [ ] Galeri bölümü (QR taranmış entity örnekleri)
- [ ] İstatistik gösterimi (toplam konuşma sayısı vb.)
- [ ] SSS (Sıkça Sorulan Sorular) bölümü

### Genel UX
- [ ] Loading/skeleton ekranları
- [ ] Offline durumu bildirimi
- [ ] PWA desteği (Progressive Web App)
- [ ] SEO optimizasyonu

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

- [ ] Akademik kullanım bildirimi (KVKK uyumu)
- [ ] Konuşma kayıt onay mekanizması
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
- **Renk teması:** Mavi-yeşil, doğa temalı (Tailwind CSS ile)
- **Hedef:** Akademik proje olarak kullanılacak, konuşmalar kayıt altına alınacak
- **Veritabanı:** Supabase (sonradan entegre edilecek)
