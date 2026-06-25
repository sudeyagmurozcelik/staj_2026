"""
PDF'i okur, parçalara böler ve ChromaDB'ye indexler.
Bir kez çalıştırılır; sonrasında api.py kullanılır.
"""

import pdfplumber
import chromadb
from google import genai
import os
import time
from dotenv import load_dotenv

load_dotenv()

PDF_PATH = "Wheeler8.pdf"
DB_PATH = "chroma_db"
CHUNK_SIZE = 200   # kelime (eskisi 500'dü, küçük chunk = daha hassas eşleşme)
CHUNK_OVERLAP = 30
EMBED_MODEL = "gemini-embedding-001"
BATCH_SIZE = 20

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def extract_text(pdf_path: str) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({"page": i + 1, "text": text.strip()})
    return pages


def chunk_text(pages: list[dict]) -> list[dict]:
    """
    Metni önce cümlelere böler, sonra cümleleri birleştirerek
    CHUNK_SIZE kelimelik parçalar oluşturur.
    Cümle ortasında kesme yapmaz — anlam bütünlüğü korunur.
    """
    import re
    chunks = []
    chunk_id = 0

    for page in pages:
        # Cümlelere böl (nokta/ünlem/soru sonrası büyük harf veya satır sonu)
        sentences = re.split(r'(?<=[.!?])\s+', page["text"].strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        current_words = []
        for sentence in sentences:
            sentence_words = sentence.split()

            # Mevcut parça doluysa kaydet, örtüşmeli yeni parça başlat
            if len(current_words) + len(sentence_words) > CHUNK_SIZE and current_words:
                chunks.append({
                    "id": f"chunk_{chunk_id}",
                    "text": " ".join(current_words),
                    "page": page["page"],
                })
                chunk_id += 1
                # Son CHUNK_OVERLAP kelimeyi bir sonraki parçaya taşı
                current_words = current_words[-CHUNK_OVERLAP:]

            current_words.extend(sentence_words)

        # Sayfanın kalan kısmını kaydet
        if current_words:
            chunks.append({
                "id": f"chunk_{chunk_id}",
                "text": " ".join(current_words),
                "page": page["page"],
            })
            chunk_id += 1

    return chunks


def embed_batch(texts: list[str]) -> list[list[float]]:
    for attempt in range(5):
        try:
            result = client.models.embed_content(
                model=EMBED_MODEL,
                contents=texts,
            )
            return [e.values for e in result.embeddings]
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60 * (attempt + 1)
                print(f"  Rate limit, {wait}s bekleniyor...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("5 denemede embedding alinamadi")


def index(pdf_path: str = PDF_PATH, db_path: str = DB_PATH):
    print(f"PDF okunuyor: {pdf_path}")
    pages = extract_text(pdf_path)
    print(f"  {len(pages)} sayfa bulundu")

    chunks = chunk_text(pages)
    print(f"  {len(chunks)} parcaya bolundu")

    db = chromadb.PersistentClient(path=db_path)
    try:
        db.delete_collection("kitap")
    except Exception:
        pass
    collection = db.create_collection("kitap")

    print("Gemini embedding ile indexleniyor...")
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metadatas = [{"page": c["page"]} for c in batch]

        embeddings = embed_batch(texts)
        collection.add(documents=texts, embeddings=embeddings, ids=ids, metadatas=metadatas)

        print(f"  {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)} parca islendi")
        time.sleep(2)

    print(f"Tamamlandi -> {db_path}/")


if __name__ == "__main__":
    index()
