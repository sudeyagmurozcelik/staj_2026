Diş hekimliği öğrencileri için Unity tabanlı VR simülasyonuna entegre
  edilmiş, halüsinasyon yapmayan bir AI eğitim asistanı. Sistem, yapay
  zekanın yalnızca Wheeler's Dental Anatomy ders kitabına dayanarak Türkçe
  cevap üretmesini sağlar.

  ---
  Nasıl Çalışır?

  Proje, AI'nın kitap dışı bilgi üretmesini engellemek için RAG
  (Retrieval-Augmented Generation) mimarisi kullanır:

  Öğrenci soru sorar (Türkçe)
          ↓
  Soru İngilizce'ye çevrilir (kitap İngilizce)
          ↓
  Vektör veritabanında en ilgili kitap bölümleri aranır
          ↓
  AI yalnızca o bölümlere dayanarak Türkçe cevap üretir
          ↓
  Cevap + kaynak sayfalar + kitaba dayalılık yüzdesi (%0–100) döndürülür

  ---
  Özellikler

  - Halüsinasyon koruması — AI yalnızca ders kitabındaki bilgiyi kullanır;
  kitapta yoksa "Bu konu ders kitabında yer almıyor." der
  - Kitaba dayalılık yüzdesi — her cevap için %0–100 güvenilirlik skoru
  - Kaynak gösterimi — cevabın hangi sayfadan geldiği gösterilir
  - Türkçe destek — Türkçe soru, Türkçe cevap
  - İki mod: AI Asistan modu + Sınav modu (AI soru üretir, öğrencinin
  cevabını notlandırır)
  - Unity entegrasyonu — tek HTTP isteğiyle bağlanır
