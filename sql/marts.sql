-- marts.sql — Analitik katman (SQLite view'ları). report.py bunları okuyup panoya döker.
-- Possession (topa sahip olma) tahmini: FGA + 0.44*FTA - OREB + TOV  (Dean Oliver)

DROP VIEW IF EXISTS v_team_game_adv;
CREATE VIEW v_team_game_adv AS
SELECT t.*,
       g.season_code, g.round, g.game_date,
       (t.fg2a + t.fg3a)                                         AS fga,
       (t.fg2a + t.fg3a) + 0.44 * t.fta - t.oreb + t.tov         AS poss,
       o.dreb                                                    AS opp_dreb,
       (o.fg2a + o.fg3a) + 0.44 * o.fta - o.oreb + o.tov         AS opp_poss
FROM fact_team_game t
JOIN fact_game g      ON g.game_id = t.game_id
JOIN fact_team_game o ON o.game_id = t.game_id AND o.team_code = t.opp_code;

-- Puan durumu: galibiyet, mağlubiyet, averaj + son 5 maç formu (window function)
DROP VIEW IF EXISTS v_standings;
CREATE VIEW v_standings AS
WITH ordered AS (
    SELECT season_code, team_code, won, pts, opp_pts,
           ROW_NUMBER() OVER (PARTITION BY season_code, team_code ORDER BY round DESC, game_id DESC) AS rn
    FROM v_team_game_adv
)
SELECT o.season_code,
       o.team_code,
       d.team_name,
       COUNT(*)                         AS gp,
       SUM(won)                         AS w,
       COUNT(*) - SUM(won)              AS l,
       ROUND(100.0 * SUM(won) / COUNT(*), 1) AS win_pct,
       SUM(pts) - SUM(opp_pts)          AS point_diff,
       GROUP_CONCAT(CASE WHEN rn <= 5 THEN (CASE WHEN won THEN 'G' ELSE 'M' END) END, '') AS last5
FROM ordered o
JOIN dim_team d USING (team_code)
GROUP BY o.season_code, o.team_code;

-- Four Factors + hücum/savunma reytingi (100 pozisyon başına sayı)
DROP VIEW IF EXISTS v_team_advanced;
CREATE VIEW v_team_advanced AS
SELECT season_code,
       team_code,
       COUNT(*)                                                          AS gp,
       ROUND(AVG(poss), 1)                                               AS pace,
       ROUND(100.0 * SUM(pts) / SUM(poss), 1)                            AS off_rtg,
       ROUND(100.0 * SUM(opp_pts) / SUM(opp_poss), 1)                    AS def_rtg,
       ROUND(100.0 * SUM(pts) / SUM(poss) - 100.0 * SUM(opp_pts) / SUM(opp_poss), 1) AS net_rtg,
       ROUND(100.0 * (SUM(fg2m + fg3m) + 0.5 * SUM(fg3m)) / SUM(fga), 1) AS efg_pct,
       ROUND(100.0 * SUM(tov) / SUM(poss), 1)                            AS tov_pct,
       ROUND(100.0 * SUM(oreb) / SUM(oreb + opp_dreb), 1)                AS oreb_pct,
       ROUND(100.0 * SUM(fta) / SUM(fga), 1)                             AS ft_rate,
       ROUND(100.0 * SUM(fg3a) / SUM(fga), 1)                            AS three_rate
FROM v_team_game_adv
GROUP BY season_code, team_code;

-- Oyuncu sezon ortalamaları + True Shooting % + PIR sıralaması
DROP VIEW IF EXISTS v_player_season;
CREATE VIEW v_player_season AS
SELECT g.season_code,
       p.player_id,
       dp.player_name,
       p.team_code,
       COUNT(*)                                   AS gp,
       ROUND(AVG(p.minutes), 1)                   AS mpg,
       ROUND(AVG(p.pts), 1)                       AS ppg,
       ROUND(AVG(p.reb), 1)                       AS rpg,
       ROUND(AVG(p.ast), 1)                       AS apg,
       ROUND(AVG(p.pir), 1)                       AS pir,
       ROUND(100.0 * SUM(p.pts) / NULLIF(2 * (SUM(p.fg2a + p.fg3a) + 0.44 * SUM(p.fta)), 0), 1) AS ts_pct,
       ROUND(AVG(p.plus_minus), 1)                AS plus_minus,
       RANK() OVER (PARTITION BY g.season_code ORDER BY AVG(p.pir) DESC) AS pir_rank
FROM fact_player_game p
JOIN fact_game g   ON g.game_id = p.game_id
JOIN dim_player dp ON dp.player_id = p.player_id
WHERE p.minutes > 0
GROUP BY g.season_code, p.player_id, p.team_code;
