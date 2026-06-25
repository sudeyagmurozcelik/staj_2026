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

<!-- Sık kullanılan komutları buraya ekle -->

## Kurallar ve Tercihler

<!-- Proje için özel kuralları buraya ekle -->
