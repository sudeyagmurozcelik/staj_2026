"""
API'yi test etmek için çalıştır:
  .\venv\Scripts\python test_api.py
"""

import urllib.request
import json

API = "http://localhost:8000"

sorular = [
    "Üst kesici dişlerin özellikleri nedir?",
    "Mine tabakası neden önemlidir?",
    "Pulpa odasının görevi nedir?",
    "Molar dişler kaç köke sahiptir?",
    "Türkiye'nin başkenti neresidir?",  # kitapta olmayan soru — "yer almıyor" demeli
]

def sor(soru: str) -> dict:
    data = json.dumps({"soru": soru}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/sor",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=" * 60)
for soru in sorular:
    print(f"\nSORU: {soru}")
    print("-" * 40)
    try:
        sonuc = sor(soru)
        print(f"CEVAP: {sonuc['cevap']}")
        sayfalar = [str(k["sayfa"]) for k in sonuc["kaynaklar"]]
        print(f"KAYNAKLAR: Sayfa {', '.join(sayfalar)}")
    except Exception as e:
        print(f"HATA: {e}")
    print("=" * 60)
