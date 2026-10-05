# 🏀 EuroLeague Data Pipeline

EuroLeague'in canlı API'sinden her gün **sadece yeni oynanan maçları** çeken, temizleyip doğrulayan,
**SQLite yıldız şemaya** yükleyen, **SQL ile ileri basketbol metrikleri** (Four Factors, Offensive/Defensive Rating, TS%)
hesaplayan ve sonucu **otomatik güncellenen bir panoda** yayınlayan uçtan uca veri mühendisliği projesi.

🔗 **Canlı pano:** https://umutseve4.github.io/euroleague-pipeline/

```
live.euroleague.net/api ──► client.py ──► transform.py ──► load.py ──► data/euroleague.db
   Header + Boxscore        (extract)    (temizle + DQ)    (upsert)     yıldız şema
                                                                              │
                       docs/index.html ◄── report.py ◄── sql/marts.sql ◄──────┘
                       (GitHub Pages)       (pano)        (view'lar)
        ▲
        └──── GitHub Actions: her gün 05:30 UTC · önce testler, sonra pipeline ────
```

## Neden ilginç? (veri mühendisliği açısından)
| Konu | Nasıl çözüldü |
|---|---|
| **Artımlı yükleme** | `ingest_state` tablosu sezon başına son gamecode'u tutar; her çalıştırma oradan devam eder. Boş yanıt = "henüz maç yok" → durur. |
| **İdempotency** | Tüm yazımlar `INSERT OR REPLACE` + birleşik PK; aynı maç 2 kez yüklense de satır çoğalmaz. |
| **Atomiklik** | Her maç tek transaction'da yazılır — yarım maç olmaz. |
| **Canlı maç koruması** | `Live=true` veya box score eksikse maç alınmaz, sonraki çalıştırmada tekrar denenir. |
| **Veri kalitesi (DQ)** | Oyuncu sayıları toplamı = takım toplamı = skor kontrolü. Bozuk maç loglanır ve atlanır, hat durmaz. |
| **Dayanıklılık** | Üstel bekleme ile retry, istekler arası gecikme, kendi User-Agent'ı (varsayılan UA 403 alıyor). |
| **Test edilebilirlik** | HTTP katmanı enjekte edilebilir; testler gerçek şemada sahte JSON ile **ağa çıkmadan** çalışır. |
| **CI/CD** | Testler geçmeden pipeline çalışmaz. |

## Veri modeli (yıldız şema)
```
dim_team(team_code PK, team_name)            dim_player(player_id PK, player_name)
          ▲                                            ▲
fact_game(game_id PK, season_code, gamecode, round, phase, game_date, home/away, skorlar)
          ▲                                            ▲
fact_team_game(game_id, team_code) PK        fact_player_game(game_id, player_id) PK
  pts, fg2m/a, fg3m/a, ftm/a, oreb, dreb,      minutes, +/-, aynı box score kolonları
  ast, stl, tov, blk, pf, pir, won, opp_pts
ingest_state(season_code PK, last_gamecode, updated_at)
```

## SQL marts (`sql/marts.sql`)
| View | İçerik |
|---|---|
| `v_team_game_adv` | Maç başına possession tahmini (FGA + 0.44·FTA − OREB + TOV), rakip istatistikleriyle self-join |
| `v_standings` | G/M, galibiyet %, averaj, son 5 maç formu (`ROW_NUMBER`) |
| `v_team_advanced` | Tempo, OffRtg, DefRtg, NetRtg, **Four Factors**: eFG%, TOV%, OREB%, FT Rate, 3P oranı |
| `v_player_season` | Oyuncu ortalamaları, True Shooting %, PIR sıralaması (`RANK`) |

## Çalıştırma
```bash
# Bağımlılık yok (sadece Python ≥3.10 standart kütüphane)
export PYTHONPATH=src            # Windows PowerShell: $env:PYTHONPATH="src"
python -m elpipe.pipeline                          # 2026-27 sezonu (E2026), sadece yeni maçlar
python -m elpipe.pipeline --season E2025 E2026     # geçen sezonu da doldur
python -m elpipe.pipeline --season U2026           # EuroCup
python -m elpipe.report                            # docs/index.html üret

pip install pytest && pytest -q                    # testler (ağ gerektirmez)
```

## Yol haritası
- [x] Artımlı ETL + yıldız şema + DQ kontrolleri
- [x] SQL marts: Four Factors, ratings, TS%, puan durumu
- [x] GitHub Actions (test → pipeline → commit) + GitHub Pages pano
- [ ] Play-by-play (`/api/PlaybyPlay`) → clutch performans, run'lar
- [ ] Şut haritası (`/api/Points`) → bölgelere göre isabet
- [ ] SQLite → PostgreSQL / DuckDB, dbt ile modelleme, Airflow ile orkestrasyon
- [ ] Maç sonucu tahmin modeli (Net Rating + ev sahibi avantajı)

---
Veri kaynağı: EuroLeague'in herkese açık canlı istatistik API'si. Proje eğitim/portföy amaçlıdır.
