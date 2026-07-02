"""
PDF'i okur, parçalara böler ve ChromaDB'ye indexler.
Bir kez çalıştırılır; sonrasında api.py kullanılır.
"""

import pdfplumber
import chromadb
from openai import OpenAI
import os
import time
from dotenv import load_dotenv

load_dotenv()

PDF_PATH   = "Wheeler8.pdf"
DB_PATH    = "chroma_db"
CHUNK_SIZE    = 200   # kelime
CHUNK_OVERLAP = 30
EMBED_MODEL   = "text-embedding-3-large"   # api.py ile BİREBİR aynı olmalı
BATCH_SIZE    = 100

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ── Çöp chunk filtreleme ─────────────────────────────────────────────────────
# Kesin çöp: bu ifadelerden birini içeren chunk'lar ders içeriği değil.
GARBAGE_PHRASES = [
    "intentionally left blank",
    "all rights reserved",
    "may be reproduced or transmitted",
    "permission in writing from the publisher",
    "permissions may be sought",
    "elsevier",
    "copyright ©",
]

def is_valid_chunk(text: str) -> bool:
    """
    Filtre kuralları:
      1. < 20 kelime → çok kısa, anlamsız (boş sayfa, adanma, tek satır başlık)
      2. Bilinen çöp ifadeler → telif hakkı / yasal metin sayfaları
      3. Büyük harf kısaltma yoğunluğu > %40 → şema etiketi listesi (IR DMR MMR CL...)
    Gerçek ders içeriği genellikle 20+ kelime, küçük harfli cümleler içerir.
    """
    words = text.split()

    if len(words) < 20:
        return False

    lower = text.lower()
    if any(phrase in lower for phrase in GARBAGE_PHRASES):
        return False

    upper_short = sum(1 for w in words if w.isupper() and len(w) <= 4)
    if upper_short / len(words) > 0.4:
        return False

    return True


def extract_text(pdf_path: str) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({"page": i + 1, "text": text.strip()})
    return pages


def chunk_text(pages: list[dict]) -> list[dict]:
    import re
    chunks = []
    chunk_id = 0

    for page in pages:
        sentences = re.split(r'(?<=[.!?])\s+', page["text"].strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        current_words = []
        for sentence in sentences:
            sentence_words = sentence.split()

            if len(current_words) + len(sentence_words) > CHUNK_SIZE and current_words:
                chunks.append({
                    "id":   f"chunk_{chunk_id}",
                    "text": " ".join(current_words),
                    "page": page["page"],
                })
                chunk_id += 1
                current_words = current_words[-CHUNK_OVERLAP:]

            current_words.extend(sentence_words)

        if current_words:
            chunks.append({
                "id":   f"chunk_{chunk_id}",
                "text": " ".join(current_words),
                "page": page["page"],
            })
            chunk_id += 1

    return chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(4):
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
            return [e.embedding for e in sorted(resp.data, key=lambda x: x.index)]
        except Exception as e:
            hata = str(e)
            if "429" in hata or "rate" in hata.lower():
                wait = 30 * (attempt + 1)
                print(f"  Rate limit, {wait}s bekleniyor...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("4 denemede embedding alinamadi")


def index(pdf_path: str = PDF_PATH, db_path: str = DB_PATH):
    print(f"PDF okunuyor: {pdf_path}")
    pages = extract_text(pdf_path)
    print(f"  {len(pages)} sayfa bulundu")

    raw_chunks = chunk_text(pages)
    print(f"  Ham chunk sayisi: {len(raw_chunks)}")

    chunks = [c for c in raw_chunks if is_valid_chunk(c["text"])]
    elenen = len(raw_chunks) - len(chunks)
    print(f"  Filtre sonrasi: {len(chunks)} chunk ({elenen} cop elendi)")

    # Chunk ID'lerini sifirla (filtre sonrasi sirali olsun)
    for i, c in enumerate(chunks):
        c["id"] = f"chunk_{i}"

    db = chromadb.PersistentClient(path=db_path)
    try:
        db.delete_collection("kitap")
    except Exception:
        pass
    collection = db.create_collection("kitap")

    print(f"OpenAI {EMBED_MODEL} ile indexleniyor...")
    for i in range(0, len(chunks), BATCH_SIZE):
        batch     = chunks[i:i + BATCH_SIZE]
        texts     = [c["text"]        for c in batch]
        ids       = [c["id"]          for c in batch]
        metadatas = [{"page": c["page"]} for c in batch]

        embeddings = embed_batch(texts)
        collection.add(documents=texts, embeddings=embeddings, ids=ids, metadatas=metadatas)

        print(f"  {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)} chunk islendi")
        time.sleep(0.5)

    print(f"\nTamamlandi → {db_path}/")
    print(f"  Model       : {EMBED_MODEL}")
    print(f"  Boyut       : 3072 (text-embedding-3-large varsayilan)")
    print(f"  Toplam chunk: {len(chunks)}")


if __name__ == "__main__":
    index()
