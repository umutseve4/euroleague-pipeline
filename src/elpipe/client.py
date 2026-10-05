"""
EXTRACT — EuroLeague'in herkese açık canlı API'sinden (live.euroleague.net) maç verisi çeker.

Uç noktalar (kimlik doğrulama yok):
  /api/Header?gamecode=N&seasoncode=E2026    -> takımlar, skor, tur, faz, tarih, salon
  /api/Boxscore?gamecode=N&seasoncode=E2026  -> oyuncu + takım box score
Notlar:
  * Henüz oluşturulmamış bir gamecode HTTP 200 + BOŞ gövde döndürür -> "durma" sinyali.
  * urllib'in varsayılan User-Agent'ı 403 alır, bu yüzden kendi UA'mızı gönderiyoruz.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

BASE_URL = "https://live.euroleague.net/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; euroleague-pipeline; github.com/umutseve4)"}
REQUEST_DELAY = 0.4  # saniye, API'ye nazik ol

Fetcher = Callable[[str, dict[str, Any]], "dict[str, Any] | None"]


def http_get_json(endpoint: str, params: dict[str, Any], retries: int = 3) -> dict[str, Any] | None:
    """JSON döndürür; gövde boşsa None (oyun henüz yok). Ağ hatalarında üstel bekleme ile tekrar dener."""
    url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(params)}"
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8").strip()
            time.sleep(REQUEST_DELAY)
            return json.loads(body) if body else None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url} alınamadı: {last_err}")


class EuroLeagueClient:
    """Test edilebilirlik için HTTP fonksiyonu dışarıdan verilebilir (fixture ile sahte istemci)."""

    def __init__(self, fetch: Fetcher = http_get_json):
        self._fetch = fetch

    def header(self, season_code: str, gamecode: int) -> dict[str, Any] | None:
        return self._fetch("Header", {"gamecode": gamecode, "seasoncode": season_code})

    def boxscore(self, season_code: str, gamecode: int) -> dict[str, Any] | None:
        return self._fetch("Boxscore", {"gamecode": gamecode, "seasoncode": season_code})
