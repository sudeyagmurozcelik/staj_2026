# CLAUDE.md

Bu dosya, Claude Code'un bu proje dizininde nasıl davranacağını tanımlar.

## Proje Hakkında

Diş hekimliği öğrencileri için VR tabanlı eğitim simülasyonu. Çok kullanıcılı ortamda (birden fazla öğrenci + bir öğretmen) dişin fiziksel yapısını görsel olarak öğretmeyi hedefler.

### Ana Bileşenler

- **VR Ortamı:** Dişin anatomik yapısının 3D görsel sunumu
- **Çok Kullanıcı Desteği:** Aynı anda birden fazla öğrenci ve bir öğretmen
- **AI Avatar:** Sesli komut alıp sesli yanıt veren eğitim asistanı

### Teknik Detaylar

- **Platform:** Unity (VR)
- **Dil:** Türkçe (ses girişi ve çıkışı)
- **Kaynak:** Ders kitabı PDF formatında

### Kritik Hedef: Halüsinasyon Azaltma

Projenin **asıl amacı** AI avatarın halüsinasyon oranını minimuma indirmek ve cevaplarını yalnızca ders kitabı PDF'indeki bilgilerle sınırlı tutmaktır.

- AI **yalnızca** ders kitabından gelen bilgilere dayanarak Türkçe yanıt vermeli
- Kitapta olmayan bilgiyi uydurmamalı; bilmiyorsa "bu konu kitapta yer almıyor" demeli
- **Yaklaşım: RAG (Retrieval-Augmented Generation)**
  1. Ders kitabı PDF'i parçalara bölünür ve vektör veritabanına indexlenir
  2. Öğrenci soru sorar → ilgili kitap bölümleri çekilir (retrieval)
  3. AI yalnızca o bölümlere dayanarak cevap üretir (grounded generation)
- Halüsinasyon testi: üretilen cevaplar kitaptaki kaynak pasajlarla karşılaştırılabilir olmalı

## Geliştirme Komutları

### Kurulum
Bağımlılıkları (kütüphaneleri) kur:
`pip install -r requirements.txt`

Ortam değişkenleri: Proje kök dizininde bir `.env` dosyası bulunmalı ve
içinde `GEMINI_API_KEY` tanımlı olmalıdır. Bu dosya gizlidir, sürüm
kontrolüne (git) eklenmez.

### Kitabı indeksleme (kurulumda bir kez)
Ders kitabı PDF'ini okuyup parçalara böler ve vektör veritabanına
(`chroma_db/`) yazar. Yalnızca kitap değiştiğinde veya indeksleme
mantığı güncellendiğinde yeniden çalıştırılır:
`python indexer.py`

Not: Bu komut mevcut "kitap" koleksiyonunu silip yeniden oluşturur.
Gemini embedding API'sini kullandığı için kota harcar ve birkaç dakika
sürebilir.

### Sunucuyu çalıştırma
FastAPI servisini başlatır (varsayılan: http://localhost:8000):
`uvicorn api:app --reload`

`--reload`, kod değiştiğinde sunucuyu otomatik yeniden başlatır;
geliştirme için kullanışlıdır, canlı ortamda kaldırılmalıdır.

### Arayüzler
- Sınav modu (öğrenci cevaplar, sistem notlar): http://localhost:8000/
- AI Asistan (soru-cevap): http://localhost:8000/asistan
- Sağlık kontrolü (sunucu ayakta mı): http://localhost:8000/saglik

### API Uç Noktaları (Endpoints)
- `POST /sor` → Soruya kitaba dayalı düz metin cevap. (Unity avatarı bunu kullanır.)
- `POST /ai-cevapla` → Cevap + bağımsız hakem tarafından verilen dayanılık yüzdesi + kaynaklar.
- `GET  /soru-getir` → Kitaptan rastgele bölümle sınav sorusu üretir.
- `POST /degerlendir` → Öğrencinin cevabını kitaba göre puanlar ve geri bildirim verir.

## Kurallar ve Tercihler

### Temel İlke: Halüsinasyon Yok
- AI **yalnızca** kendisine verilen BAĞLAM'a (ders kitabından çekilen
  bölümler) dayanarak cevap vermeli. Kitapta olmayan hiçbir bilgiyi
  uydurmamalı veya genel dünya bilgisinden eklememeli.
- Bağlamda cevap yoksa, tahmin etmek yerine açıkça "Bu konu ders
  kitabında yer almıyor." demeli.
- Bu ilke projenin varlık sebebidir; her değişiklik bu hedefi
  güçlendirmeli, zayıflatmamalı.

### Değerlendirme Bağımsız Olmalı
- Bir cevabın "dayanılık" puanı, o cevabı **üreten** modelden
  gelmemeli (self-grading güvenilir değildir). Puan, ayrı bir hakem
  (judge) çağrısıyla, bağımsız olarak verilmeli.
- Değerlendirmenin kalitesi, veritabanındaki kitap içeriğinin
  kalitesine bağlıdır; indeksleme bozuksa puanlar da anlamsız olur.

### Dil
- Tüm kullanıcıya dönük çıktılar **Türkçe** olmalı.
- Kitap İngilizce olduğu için, arama öncesinde soru İngilizce'ye
  çevrilir; bu iç mekanizma kullanıcıya yansımaz.

### Teknik Kurallar
- Gemini'den yapılandırılmış (JSON) çıktı beklenen her yerde
  `json_mode=True` kullanılmalı. Model çıktısını elle string olarak
  ayıklamaya (``` temizleme gibi) geri dönülmemeli.
- Model çağrılarında hata toleransı: kota dolarsa sıradaki modele
  geçilir; JSON ayrıştırılamazsa sistem çökmemeli, makul
  varsayılanlarla devam etmeli (graceful fallback).
- Yeni endpoint'ler de bu iki kurala (json_mode + graceful fallback)
  uymalı.

### Güvenlik
- `GEMINI_API_KEY` yalnızca `.env` dosyasında tutulur. Anahtar **asla**
  kod içine yazılmaz, log'a basılmaz, veya paylaşılmaz.
- `.env` dosyası ve `chroma_db/` klasörü git'e gönderilmemeli
  (`.gitignore` içinde olmalı).

### Mimari Notu
- Sistem RAG (Retrieval-Augmented Generation) yaklaşımı kullanır:
  önce ilgili kitap bölümleri çekilir (retrieval), sonra AI yalnızca o
  bölümlere dayanarak üretir (generation).
- `indexer.py` bir defalık hazırlık aracıdır; `api.py` ise sürekli
  çalışan servistir. İkisi aynı veritabanını (`chroma_db/`) paylaşır.
