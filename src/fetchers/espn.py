"""
espn.py - Fetcher usando a API publica da ESPN (sem autenticacao).
Cobre Brasileirao 2026, Libertadores, Premier League e mais.
Retorna dados no mesmo formato do FootballDataFetcher.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Mapa: competition_key -> ESPN league slug
ESPN_LEAGUES = {
    # ── Brasil ──────────────────────────────────────────────────
    "brasileirao_a":    "bra.1",
    "brasileirao_b":    "bra.2",
    "brasileirao_c":    "bra.3",
    "copa_brasil":      "bra.cup",
    "copa_nordeste":    "bra.ne",
    "copa_verde":       "bra.verde",
    # ── América do Sul ───────────────────────────────────────────
    "libertadores":     "conmebol.libertadores",
    "sudamericana":     "conmebol.sudamericana",
    "recopa_sul":       "conmebol.recopa",
    "liga_argentina":   "arg.1",
    "liga_colombiana":  "col.1",
    "liga_chilena":     "chi.1",
    "liga_uruguaia":    "uru.1",
    "liga_mexicana":    "mex.1",
    # ── Europa ───────────────────────────────────────────────────
    "champions_league":     "uefa.champions",
    "europa_league":        "uefa.europa",
    "conference_league":    "uefa.europa.conference",
    "premier_league":       "eng.1",
    "championship":         "eng.2",
    "la_liga":              "esp.1",
    "la_liga2":             "esp.2",
    "bundesliga":           "ger.1",
    "bundesliga_2":         "ger.2",
    "serie_a_it":           "ita.1",
    "serie_b_it":           "ita.2",
    "ligue_1":              "fra.1",
    "ligue_2":              "fra.2",
    "primeira_liga":        "por.1",
    "eredivisie":           "ned.1",
    "pro_league":           "bel.1",
    "super_lig":            "tur.sl",
    "scottish_prem":        "sco.1",
    # ── América do Norte ─────────────────────────────────────────
    "mls":              "usa.1",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
    "Referer":    "https://www.espn.com",
}

BASE     = "https://site.api.espn.com/apis/site/v2/sports/soccer"
BASE_WEB = "https://site.web.api.espn.com/apis/v2/sports/soccer"

# Session persistente — reutiliza conexões TCP (1 handshake por host)
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def _int_id(v):
    """Converte ID para int quando possível (usado em todo o módulo)."""
    try:
        return int(v)
    except (ValueError, TypeError):
        return v


def _get(url, params=None):
    try:
        r = _SESSION.get(url, params=params or {}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("ESPN request failed: %s | %s", url, e)
        return {}


def _score_val(score_obj):
    """Extrai placar: int, float, string numerica ou dict {displayValue}."""
    if score_obj is None:
        return None
    if isinstance(score_obj, (int, float)):
        return int(score_obj)
    if isinstance(score_obj, str):
        try:
            return int(float(score_obj))
        except (ValueError, TypeError):
            return None
    if isinstance(score_obj, dict):
        # Tenta 'value' primeiro (numerico), depois 'displayValue'
        for key in ("value", "displayValue"):
            dv = score_obj.get(key)
            if dv is not None:
                try:
                    return int(float(dv))
                except (ValueError, TypeError):
                    continue
    return None


# ===================================================================
# STANDINGS
# ===================================================================
def get_standings(competition_key: str, season: int) -> pd.DataFrame:
    slug = ESPN_LEAGUES.get(competition_key)
    if not slug:
        return pd.DataFrame()

    url = f"{BASE_WEB}/{slug}/standings"
    data = _get(url, {"season": season, "sort": "points:desc"})
    children = data.get("children", [])
    if not children:
        return pd.DataFrame()

    def _parse_entries(entries, group_name="", group_idx=0):
        rows = []
        for e in entries:
            team = e.get("team", {})
            stats = {s["type"].lower(): s for s in e.get("stats", [])}

            def sv(key):
                s = stats.get(key.lower(), {})
                v = s.get("value")
                if v is not None:
                    try:
                        return int(float(v))
                    except (ValueError, TypeError):
                        pass
                dv = s.get("displayValue", "")
                try:
                    return int(float(dv)) if dv not in (None, "", "?", "+0") else 0
                except (ValueError, TypeError):
                    return 0

            gd_raw = stats.get("pointdifferential", {}).get("value", 0)
            try:
                gd = int(float(gd_raw)) if gd_raw is not None else 0
            except (ValueError, TypeError):
                gd = 0

            rows.append({
                "position":      sv("rank") or (len(rows) + 1),
                "team_id":       _int_id(team.get("id", "")),
                "team_name":     team.get("displayName", ""),
                "played":        sv("gamesplayed"),
                "won":           sv("wins"),
                "drawn":         sv("ties"),
                "lost":          sv("losses"),
                "goals_for":     sv("pointsfor"),
                "goals_against": sv("pointsagainst"),
                "goal_diff":     gd,
                "points":        sv("points"),
                "form":          "",
                "group":         group_name,
            })
        return rows

    # Suporta múltiplos grupos (Libertadores tem 8, Champions tem 8, etc.)
    all_rows = []
    for i, child in enumerate(children):
        group_name = child.get("name", f"Grupo {i+1}")
        entries = child.get("standings", {}).get("entries", [])
        all_rows.extend(_parse_entries(entries, group_name, i))

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    if df["position"].eq(0).all():
        df["position"] = range(1, len(df) + 1)
    return df


# ===================================================================
# TEAMS
# ===================================================================
def get_teams(competition_key: str, season: int) -> pd.DataFrame:
    slug = ESPN_LEAGUES.get(competition_key)
    if not slug:
        return pd.DataFrame()

    url = f"{BASE}/{slug}/teams"
    data = _get(url)
    sports = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])

    rows = []
    for t in sports:
        team = t.get("team", {})
        rows.append({
            "team_id":    _int_id(team.get("id", "")),
            "team_name":  team.get("displayName", ""),
            "team_short": team.get("abbreviation", ""),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ===================================================================
# FIXTURES  (date range)
# ===================================================================
def _fetch_scoreboard_range(slug: str, from_date: str, to_date: str) -> list:
    """
    Busca eventos num intervalo de datas (formato YYYY-MM-DD).
    Divide em chunks de 30 dias e faz as requests em paralelo (ThreadPoolExecutor).
    """
    url    = f"{BASE}/{slug}/scoreboard"
    d_from = datetime.strptime(from_date, "%Y-%m-%d")
    d_to   = datetime.strptime(to_date,   "%Y-%m-%d")

    # Monta lista de chunks (cursor_inicio, cursor_fim)
    chunks = []
    cursor = d_from
    while cursor <= d_to:
        chunk_end = min(cursor + timedelta(days=29), d_to)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    def _fetch_chunk(chunk):
        c_start, c_end = chunk
        params = {
            "dates": f"{c_start.strftime('%Y%m%d')}-{c_end.strftime('%Y%m%d')}",
            "limit": 200,
        }
        return _get(url, params).get("events", [])

    # Paraleliza requests (max 4 threads — respeita rate limit da ESPN)
    if len(chunks) <= 1:
        return _fetch_chunk(chunks[0]) if chunks else []

    all_events_ordered = [None] * len(chunks)
    with ThreadPoolExecutor(max_workers=4) as ex:
        future_to_idx = {ex.submit(_fetch_chunk, c): i for i, c in enumerate(chunks)}
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                all_events_ordered[idx] = fut.result()
            except Exception as e:
                logger.warning("ESPN chunk failed: %s", e)
                all_events_ordered[idx] = []

    # Flatten preservando a ordem cronológica dos chunks
    return [ev for chunk_events in all_events_ordered if chunk_events for ev in chunk_events]


def _events_to_df(events: list) -> pd.DataFrame:
    """Converte lista de eventos ESPN para DataFrame normalizado."""
    rows = []
    for e in events:
        competitions = e.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue

        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])

        status_obj = comp.get("status", {}).get("type", {})
        status     = status_obj.get("name", "NS")
        completed  = status_obj.get("completed", False)

        home_goals = _score_val(home.get("score")) if completed else None
        away_goals = _score_val(away.get("score")) if completed else None

        rows.append({
            "fixture_id":   e.get("id", ""),
            "date":         e.get("date", "")[:19],
            "home_team_id": _int_id(home.get("id", "")),
            "home_team":    home.get("team", {}).get("displayName", ""),
            "away_team_id": _int_id(away.get("id", "")),
            "away_team":    away.get("team", {}).get("displayName", ""),
            "home_goals":   home_goals,
            "away_goals":   away_goals,
            "ft_home":      home_goals,
            "ft_away":      away_goals,
            "status":       "FT" if completed else status,
            "status_long":  "Match Finished" if completed else status,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce").dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
    return df


def get_fixtures(competition_key: str, season: int,
                 from_date: str = None, to_date: str = None,
                 status: str = None) -> pd.DataFrame:
    slug = ESPN_LEAGUES.get(competition_key)
    if not slug:
        return pd.DataFrame()

    if from_date is None:
        from_date = f"{season}-01-01"
    if to_date is None:
        to_date = f"{season}-12-31"

    events = _fetch_scoreboard_range(slug, from_date, to_date)
    df = _events_to_df(events)

    if df.empty:
        return df

    if status == "FT":
        df = df[df["status"] == "FT"]

    return df.reset_index(drop=True)


def get_upcoming_fixtures(competition_key: str, season: int,
                          days_ahead: int = 14) -> pd.DataFrame:
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")
    to_date   = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    return get_fixtures(competition_key, season, from_date, to_date)


# ===================================================================
# H2H  (via schedule de cada time)
# ===================================================================
def get_h2h(home_team_id: str, away_team_id: str,
            competition_key: str, season: int, last: int = 10) -> pd.DataFrame:
    slug = ESPN_LEAGUES.get(competition_key)
    if not slug:
        return pd.DataFrame()

    url = f"{BASE}/{slug}/teams/{home_team_id}/schedule"
    data = _get(url, {"season": season})
    events = data.get("events", [])

    rows = []
    away_id_str = str(away_team_id)
    for e in events:
        comp = e.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        ids = [t.get("id", "") for t in teams]
        if away_id_str not in ids:
            continue

        completed = comp.get("status", {}).get("type", {}).get("completed", False)
        if not completed:
            continue

        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])

        hg = _score_val(home.get("score"))
        ag = _score_val(away.get("score"))

        rows.append({
            "date":         e.get("date", "")[:10],
            "home_team":    home.get("team", {}).get("displayName", ""),
            "away_team":    away.get("team", {}).get("displayName", ""),
            "home_team_id": _int_id(home.get("id", "")),
            "away_team_id": _int_id(away.get("id", "")),
            "home_goals":   hg,
            "away_goals":   ag,
            "result_team1": ("W" if hg > ag else "L" if hg < ag else "D") if (hg is not None and ag is not None) else "?",
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.sort_values("date", ascending=False).head(last)
    return df


def is_supported(competition_key: str) -> bool:
    return competition_key in ESPN_LEAGUES
