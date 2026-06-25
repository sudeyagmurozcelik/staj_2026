using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

// Bir GameObject'e ekle. SoruSor() metodunu mikrofon/STT sisteminden çağır.
public class AvatarAI : MonoBehaviour
{
    [SerializeField] private string apiUrl = "http://localhost:8000/sor";

    public void SoruSor(string soru)
    {
        StartCoroutine(GonderVeCevapAl(soru));
    }

    private IEnumerator GonderVeCevapAl(string soru)
    {
        string json = $"{{\"soru\": \"{soru}\"}}";
        byte[] body = System.Text.Encoding.UTF8.GetBytes(json);

        using var req = new UnityWebRequest(apiUrl, "POST");
        req.uploadHandler = new UploadHandlerRaw(body);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError($"API hatası: {req.error}");
            yield break;
        }

        var yanit = JsonUtility.FromJson<ApiYanit>(req.downloadHandler.text);
        Debug.Log($"Cevap: {yanit.cevap}");

        // Buraya TTS (metinden ses) veya avatar animasyon kodunu ekle
        AvatarKonussur(yanit.cevap);
    }

    private void AvatarKonussur(string metin)
    {
        // TTS sisteminle entegre et (örn. Azure TTS, Google TTS)
        Debug.Log($"Avatar söylüyor: {metin}");
    }

    [System.Serializable]
    private class ApiYanit
    {
        public string cevap;
    }
}
