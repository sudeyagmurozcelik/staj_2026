"""
FastAPI servisi.
Endpointler:
  GET  /              → Öğrenci sınav arayüzü
  GET  /asistan       → AI asistan arayüzü
  POST /sor           → AI'a soru sor
  GET  /soru-getir    → Kitaptan rastgele soru üret
  POST /degerlendir   → Öğrenci cevabını değerlendir
  POST /ai-cevapla    → AI cevap verir + kitaba dayalılık yüzdesi gösterir
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import chromadb
from google import genai
from google.genai import types
import os
import json
import random
import time
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "chroma_db"
TOP_K = 5
EMBED_MODEL = "gemini-embedding-001"
# Kota dolduğunda sıradaki modele geçilir
GEN_MODELLER = [
    "gemini-3-flash-preview",
    "gemini-2.0-flash-lite",
]

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

app = FastAPI(title="Diş Hekimliği AI Avatar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_collection = None


def get_collection():
    global _collection
    if _collection is None:
        db = chromadb.PersistentClient(path=DB_PATH)
        _collection = db.get_collection("kitap")
    return _collection


def embed(text: str) -> list[float]:
    return client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
    ).embeddings[0].values


def turkce_ingilizce_cevir(metin: str) -> str:
    """Türkçe sorguyu İngilizce'ye çevirir. Hata olursa orijinal metni döndürür."""
    try:
        # Çeviri için hızlı tek deneme — fallback döngüsü gerek yok
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=metin,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Translate the following dental question from Turkish to English. "
                    "Output ONLY the English translation, nothing else."
                )
            ),
        )
        return resp.text.strip()
    except Exception:
        return metin


def retrieve(soru: str, k: int = TOP_K):
    """Sorguyu İngilizce'ye çevirip arama yapar (kitap İngilizce)."""
    collection = get_collection()
    ingilizce_soru = turkce_ingilizce_cevir(soru)
    results = collection.query(query_embeddings=[embed(ingilizce_soru)], n_results=k)
    return results["documents"][0], results["metadatas"][0]


def gemini_uret(contents: str, system: str) -> str:
    """
    Modelleri sırayla dener.
    429/EXHAUSTED → kota doldu, hemen sonraki modele geç (bekleme yok).
    503/UNAVAILABLE → geçici hata, 3sn bekleyip bir kez daha dene.
    """
    for model in GEN_MODELLER:
        for deneme in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system),
                )
                return resp.text.strip()
            except Exception as e:
                hata = str(e)
                if "429" in hata or "EXHAUSTED" in hata or "quota" in hata:
                    break  # kota doldu — bekleme yok, hemen sonraki modele geç
                elif "503" in hata or "UNAVAILABLE" in hata:
                    if deneme == 0:
                        time.sleep(3)  # geçici hata, bir kez bekle
                    else:
                        break
                else:
                    raise  # beklenmedik hata — direkt fırlat

    raise HTTPException(
        status_code=503,
        detail="Tüm modellerin kotası doldu. Gece yarısından sonra (TSİ 10:00) tekrar dene."
    )


def baglam_olustur(documents, metadatas) -> str:
    return "\n\n---\n\n".join(
        f"[Sayfa {m['page']}]\n{doc}" for doc, m in zip(documents, metadatas)
    )


# ─── Sistem Komutları ────────────────────────────────────────────────────────

SISTEM_KOMUTU = """Sen bir diş hekimliği eğitim asistanısın.
Yalnızca sana verilen BAĞLAM bölümündeki bilgilere dayanarak Türkçe cevap ver.
Bağlamda yer almayan hiçbir bilgiyi uydurma veya tahmin etme.
Eğer soru bağlamda cevap bulamıyorsa, şunu söyle: "Bu konu ders kitabında yer almıyor."
Cevapların kısa, net ve öğrenciye yönelik olsun."""

SORU_URETICI_KOMUTU = """Sen bir diş hekimliği sınav hazırlayıcısısın.
Sana verilen ders kitabı bölümünden, öğrencilerin anlayışını ölçecek,
açık uçlu ve Türkçe bir soru oluştur.
Yalnızca soruyu yaz, başka hiçbir şey ekleme."""

DEGERLENDIRME_KOMUTU = """Sen bir diş hekimliği eğitim değerlendirme sistemisin.
Öğrencinin cevabını, verilen BAĞLAM (ders kitabı) ile karşılaştırarak değerlendir.

SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:
{
  "yuzde": <0-100 arası tam sayı>,
  "geri_bildirim": "<öğrenciye Türkçe, yapıcı geri bildirim, 2-3 cümle>",
  "dogru_cevap": "<kitaba göre doğru ve tam cevap, Türkçe>"
}"""


# ─── Veri Modelleri ──────────────────────────────────────────────────────────

class Soru(BaseModel):
    soru: str


class DegerlendirmeGirdisi(BaseModel):
    soru: str
    ogrenci_cevabi: str


class Cevap(BaseModel):
    cevap: str
    kaynaklar: list[dict]


class SoruSonucu(BaseModel):
    soru: str
    kaynak_sayfa: int
    kaynak_metin: str


class DegerlendirmeSonucu(BaseModel):
    yuzde: int
    geri_bildirim: str
    dogru_cevap: str
    kaynaklar: list[dict]


# ─── Endpointler ─────────────────────────────────────────────────────────────

AI_CEVAPLAMA_KOMUTU = """Sen bir diş hekimliği eğitim asistanısın.
Sana verilen BAĞLAM (ders kitabı bölümleri) ve SORU'ya göre yanıt ver.

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{
  "cevap": "<Türkçe, net ve açıklayıcı cevap>",
  "dayanilik": <0-100 arası tam sayı — cevabın yüzde kaçı doğrudan bağlamdan geliyor>,
  "aciklama": "<neden bu oranı verdin, 1 kısa cümle>"
}

Bağlamda olmayan hiçbir bilgiyi ekleme.
Bağlamda cevap yoksa cevap alanına "Bu konu ders kitabında yer almıyor." yaz ve dayanilik 0 ver."""


class AICevap(BaseModel):
    cevap: str
    dayanilik: int
    aciklama: str
    kaynaklar: list[dict]


@app.post("/ai-cevapla", response_model=AICevap)
def ai_cevapla(body: Soru):
    if not body.soru.strip():
        raise HTTPException(status_code=400, detail="Soru boş olamaz.")

    documents, metadatas = retrieve(body.soru, k=5)
    if not documents:
        return AICevap(cevap="Bu konu ders kitabında yer almıyor.", dayanilik=0,
                       aciklama="Kitapta ilgili bölüm bulunamadı.", kaynaklar=[])

    baglam = baglam_olustur(documents, metadatas)

    raw = gemini_uret(
        contents=f"BAĞLAM:\n{baglam}\n\nSORU: {body.soru}",
        system=AI_CEVAPLAMA_KOMUTU,
    )
    # ```json ... ``` bloğunu temizle
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # JSON parse başarısız — cevabı ham metin olarak kullan
        data = {
            "cevap": raw if raw else "Cevap üretilemedi.",
            "dayanilik": 50,
            "aciklama": "Yanıt formatı beklenenden farklıydı.",
        }

    kaynaklar = [
        {"sayfa": m["page"], "metin": doc[:250] + "..."}
        for doc, m in zip(documents, metadatas)
    ]

    return AICevap(
        cevap=data.get("cevap", ""),
        dayanilik=max(0, min(100, int(data.get("dayanilik", 0)))),
        aciklama=data.get("aciklama", ""),
        kaynaklar=kaynaklar,
    )


@app.get("/")
def anasayfa():
    return FileResponse("arayuz.html")


@app.get("/asistan")
def asistan():
    return FileResponse("asistan.html")


@app.get("/saglik")
def saglik():
    return {"durum": "calisiyor"}


@app.get("/favicon.ico")
def favicon():
    raise HTTPException(status_code=204)


@app.post("/sor", response_model=Cevap)
def sor(body: Soru):
    if not body.soru.strip():
        raise HTTPException(status_code=400, detail="Soru boş olamaz.")

    documents, metadatas = retrieve(body.soru)
    if not documents:
        return Cevap(cevap="Bu konu ders kitabında yer almıyor.", kaynaklar=[])

    baglam = baglam_olustur(documents, metadatas)
    cevap_metni = gemini_uret(
        contents=f"BAĞLAM:\n{baglam}\n\nSORU: {body.soru}",
        system=SISTEM_KOMUTU,
    )
    kaynaklar = [
        {"sayfa": m["page"], "metin": doc[:200] + "..."}
        for doc, m in zip(documents, metadatas)
    ]
    return Cevap(cevap=cevap_metni, kaynaklar=kaynaklar)


@app.get("/soru-getir", response_model=SoruSonucu)
def soru_getir():
    """Kitaptan rastgele bir bölüm seçip soru üretir."""
    collection = get_collection()
    count = collection.count()
    rastgele_id = f"chunk_{random.randint(0, count - 1)}"

    sonuc = collection.get(ids=[rastgele_id], include=["documents", "metadatas"])
    metin = sonuc["documents"][0]
    sayfa = sonuc["metadatas"][0]["page"]

    uretilen_soru = gemini_uret(contents=f"BAĞLAM:\n{metin}", system=SORU_URETICI_KOMUTU)

    return SoruSonucu(
        soru=uretilen_soru,
        kaynak_sayfa=sayfa,
        kaynak_metin=metin[:300] + "...",
    )


@app.post("/degerlendir", response_model=DegerlendirmeSonucu)
def degerlendir(body: DegerlendirmeGirdisi):
    """Öğrencinin cevabını kitaba göre değerlendirir."""
    if not body.ogrenci_cevabi.strip():
        raise HTTPException(status_code=400, detail="Cevap boş olamaz.")

    documents, metadatas = retrieve(body.soru, k=3)
    baglam = baglam_olustur(documents, metadatas)

    prompt = (
        f"BAĞLAM (Ders Kitabı):\n{baglam}\n\n"
        f"SORU: {body.soru}\n\n"
        f"ÖĞRENCİNİN CEVABI: {body.ogrenci_cevabi}"
    )

    raw = gemini_uret(contents=prompt, system=DEGERLENDIRME_KOMUTU)
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Değerlendirme ayrıştırılamadı.")

    kaynaklar = [
        {"sayfa": m["page"], "metin": doc[:250] + "..."}
        for doc, m in zip(documents, metadatas)
    ]

    return DegerlendirmeSonucu(
        yuzde=int(data.get("yuzde", 0)),
        geri_bildirim=data.get("geri_bildirim", ""),
        dogru_cevap=data.get("dogru_cevap", ""),
        kaynaklar=kaynaklar,
    )
