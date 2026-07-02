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
from openai import OpenAI
import os
import json
import random
import time
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "chroma_db"
TOP_K = 5
EMBED_MODEL = "text-embedding-3-large"   # indexer.py ile BİREBİR aynı — değiştirme
# Kota dolduğunda sıradaki Gemini modeline, hepsi dolunca OpenAI'ye geçilir
GEN_MODELLER = [
    "gemini-3-flash-preview",
    "gemini-2.0-flash-lite",
]
OPENAI_MODEL = "gpt-4o-mini"

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

_openai_client = None
_oai_key = os.environ.get("OPENAI_API_KEY", "")
if _oai_key:
    _openai_client = OpenAI(api_key=_oai_key)

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
    resp = _openai_client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def turkce_ingilizce_cevir(metin: str) -> str:
    """Türkçe sorguyu OpenAI ile İngilizce'ye çevirir."""
    try:
        resp = _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional dental translator. "
                        "Translate the Turkish dentistry question into English for searching "
                        "in Wheeler's Dental Anatomy. "
                        "Use correct dental terminology. "
                        "Important terms: mine/mine tabakası = enamel, dentin = dentin, "
                        "pulpa = pulp, pulpa odası = pulp chamber, sement = cementum, "
                        "periodontal ligament = periodontal ligament. "
                        "Only output the translated English question. "
                        "Do not answer the question."
                    ),
                },
                {"role": "user", "content": metin},
            ],
        )

        ceviri = resp.choices[0].message.content.strip()
        print("OPENAI TRANSLATED QUERY:", ceviri)
        return ceviri

    except Exception as e:
        print("OPENAI TRANSLATION ERROR:", e)
        return metin


def retrieve(soru: str, k: int = TOP_K):
    """Sorguyu İngilizce'ye çevirip arama yapar (kitap İngilizce)."""
    collection = get_collection()

    ingilizce_soru = turkce_ingilizce_cevir(soru)

    print("\n" + "-" * 60)
    print("RETRIEVAL QUERY :", ingilizce_soru)
    print("-" * 60)

    results = collection.query(
        query_embeddings=[embed(ingilizce_soru)],
        n_results=k
    )

    print("FOUND PAGES :", [m["page"] for m in results["metadatas"][0]])
    print("-" * 60 + "\n")

    return results["documents"][0], results["metadatas"][0]


def gemini_uret(contents: str, system: str, json_mode: bool = False) -> str:
    """
    Modelleri sırayla dener.
    429/EXHAUSTED → kota doldu, hemen sonraki modele geç (bekleme yok).
    503/UNAVAILABLE → geçici hata, 3sn bekleyip bir kez daha dene.
    json_mode=True → model her zaman geçerli JSON döndürür.
    """
    cfg = types.GenerateContentConfig(system_instruction=system)
    if json_mode:
        cfg.response_mime_type = "application/json"

    for model in GEN_MODELLER:
        for deneme in range(2):
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=cfg,
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

    # Tüm Gemini modelleri doldu → OpenAI'ye geç
    if _openai_client:
        try:
            msgs = [
                {"role": "system", "content": system},
                {"role": "user",   "content": contents},
            ]
            kwargs = {"model": OPENAI_MODEL, "messages": msgs}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = _openai_client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"OpenAI de başarısız: {e}")

    raise HTTPException(
        status_code=503,
        detail="Tüm Gemini kotaları doldu ve OPENAI_API_KEY tanımlı değil."
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
    soru: system_instruction
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
Sana verilen BAĞLAM (ders kitabı bölümleri) ve SORU'ya göre Türkçe yanıt ver.

Kurallar:
- Yalnızca BAĞLAM içindeki bilgileri kullan.
- Bağlamda açıkça geçmeyen genel diş hekimliği bilgisini EKLEME.
- Kendi ön bilginle açıklama yapma veya çıkarım yürütme.
- Cevabı kısa tut (2-4 cümle).
- Yalnızca bağlamdan desteklenebilen ifadeler kur.

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{"cevap": "<Türkçe, kısa ve bağlama sadık cevap>"}

Bağlamda cevap yoksa:
{"cevap": "Bu konu ders kitabında yer almıyor."}"""

HAKEM_KOMUTU = """Sen bağımsız bir diş hekimliği eğitim değerlendiricisindir.
Sana bir BAĞLAM (ders kitabı bölümleri) ve bir ÜRETİLEN CEVAP verilecek.
Görevin: cevabın içeriğinin ne kadarı doğrudan bağlamdan kaynaklanıyor, 0-100 arası puan ver.
Cevabı yeniden üretme; yalnızca puanla ve 1 cümle gerekçe yaz.

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{"dayanilik": <0-100 tam sayı>, "aciklama": "<1 kısa Türkçe cümle>"}"""


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

    # 1. Adım: cevabı üret
    raw_cevap = gemini_uret(
        contents=f"BAĞLAM:\n{baglam}\n\nSORU: {body.soru}",
        system=AI_CEVAPLAMA_KOMUTU,
        json_mode=True,
    )
    try:
        cevap_data = json.loads(raw_cevap)
        uretilen_cevap = cevap_data.get("cevap", raw_cevap)
    except json.JSONDecodeError:
        uretilen_cevap = raw_cevap if raw_cevap else "Cevap üretilemedi."

    # 2. Adım: bağımsız hakem cevabı puanlar
    raw_hakem = gemini_uret(
        contents=f"BAĞLAM:\n{baglam}\n\nÜRETİLEN CEVAP:\n{uretilen_cevap}",
        system=HAKEM_KOMUTU,
        json_mode=True,
    )
    try:
        hakem_data = json.loads(raw_hakem)
        dayanilik = max(0, min(100, int(hakem_data.get("dayanilik", 0))))
        aciklama  = hakem_data.get("aciklama", "")
    except (json.JSONDecodeError, ValueError):
        dayanilik = 0
        aciklama  = "Hakem değerlendirmesi ayrıştırılamadı."

    kaynaklar = [
        {"sayfa": m["page"], "metin": doc[:250] + "..."}
        for doc, m in zip(documents, metadatas)
    ]

    return AICevap(
    cevap=uretilen_cevap,
    dayanilik=dayanilik,
    aciklama=aciklama,
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

    raw = gemini_uret(contents=prompt, system=DEGERLENDIRME_KOMUTU, json_mode=True)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {
            "yuzde": 0,
            "geri_bildirim": "Yanıt formatı beklenenden farklıydı, değerlendirme yapılamadı.",
            "dogru_cevap": "Yanıt formatı beklenenden farklıydı, değerlendirme yapılamadı.",
        }

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
