"""
api_football.py - Fetcher unificado com roteamento em 3 camadas:
  1. ESPN (gratuito, sem chave)  → temporada atual 2025/2026+
  2. api-sports.io direto        → histórico até 2024 (100 req/dia free)
  3. football-data.org           → ligas europeias (PRIMARY_API=football_data)
"""
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    API_FOOTBALL_BASE_URL,
    RAPIDAPI_KEY, RAPIDAPI_HOST, APISPORTS_KEY,
    PRIMARY_API, COMPETITIONS,
    FINISHED_STATUSES, DEFAULT_SEASON,
    get_current_season, APISPORTS_FREE_MAX_SEASON,
)
from src.cache.cache_manager import get_cache

logger = logging.getLogger(__name__)


# ================================================================== #
# CLIENTE API-FOOTBALL / API-SPORTS.IO
# ================================================================== #
class APIFootballClient:
    BASE_URL = API_FOOTBALL_BASE_URL
    RATE_LIMIT_DELAY = 1.2

    def __init__(self):
        self.session = requests.Session()
        if APISPORTS_KEY:
            self.session.headers.update({"x-apisports-key": APISPORTS_KEY})
            self._auth_mode = "apisports"
        else:
            self.session.headers.update({
                "X-RapidAPI-Key":  RAPIDAPI_KEY,
                "X-RapidAPI-Host": RAPIDAPI_HOST,
            })
            self._auth_mode = "rapidapi"
        self._last_request = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request = time.time()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
    def get(self, endpoint: str, params: dict = None) -> dict:
        if not APISPORTS_KEY and (not RAPIDAPI_KEY or RAPIDAPI_KEY == "sua_chave_aqui"):
            raise ValueError("Nenhuma chave de API configurada. Adicione APISPORTS_KEY no .env.")
        self._throttle()
        url = f"{self.BASE_URL}/{endpoint}"
        resp = self.session.get(url, params=params or {}, timeout=15)
        if resp.status_code == 401:
            raise PermissionError("Chave invalida (401). Verifique APISPORTS_KEY no .env.")
        if resp.status_code in (402, 403):
            raise PermissionError(
                f"Acesso negado ({resp.status_code}). Verifique sua conta em dashboard.api-football.com"
            )
        if resp.status_code == 429:
            raise RuntimeError("Limite de requisicoes atingido (429). Aguarde 1 minuto.")
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            errs = data["errors"]
            if isinstance(errs, dict):
                errs = list(errs.values())
            if errs and errs != [""]:
                raise RuntimeError(f"API Error: {errs}")
        return data



# ================================================================== #
# NORMALIZACAO DE COLUNAS (compatibilidade com cache antigo / ESPN)
# ================================================================== #
_STANDINGS_COL_MAP = {
    "gf":     "goals_for",
    "ga":     "goals_against",
    "gd":     "goal_diff",
    "wins":   "won",
    "draws":  "drawn",
    "losses": "lost",
}

def _normalize_standings(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que o DataFrame de standings sempre usa colunas padrao."""
    if df is None or df.empty:
        return df
    return df.rename(columns={k: v for k, v in _STANDINGS_COL_MAP.items() if k in df.columns})


# ================================================================== #
# FETCHER UNIFICADO
# ================================================================== #
class FootballDataFetcher:

    def __init__(self):
        self.cache = get_cache()
        self._primary = PRIMARY_API
        if self._primary == "football_data":
            from src.fetchers.football_data_org import get_fd_fetcher
            self._fd = get_fd_fetcher()
            self._api = None
        else:
            self._api = APIFootballClient()
            self._fd = None
        import src.fetchers.espn as _espn_mod
        self._espn = _espn_mod

    def _using_fd(self) -> bool:
        return self._primary == "football_data"

    def _use_espn(self, competition_key: str, season: int) -> bool:
        if self._using_fd():
            return False
        if season <= APISPORTS_FREE_MAX_SEASON:
            return False
        return self._espn.is_supported(competition_key)

    def _season(self, competition_key: str, season: int = None) -> int:
        if self._using_fd():
            from src.fetchers.football_data_org import get_fd_season
            return season if season is not None else get_fd_season(competition_key)
        raw = season if season is not None else get_current_season(competition_key)
        return raw

    # ------------------------------------------------------------------ #
    # STANDINGS
    # ------------------------------------------------------------------ #
    def get_standings(self, competition_key: str, season: int = None,
                      force_refresh: bool = False) -> pd.DataFrame:
        season = self._season(competition_key, season)
        if self._using_fd():
            return self._fd.get_standings(competition_key, season, force_refresh)

        # ESPN para seasons > 2024
        if self._use_espn(competition_key, season):
            logger.info("ESPN standings %s %s", competition_key, season)
            df = self._espn.get_standings(competition_key, season)
            if not df.empty:
                return _normalize_standings(df)

        cache_id = f"{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("standings", cache_id)
            if cached is not None:
                df = cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)
                return _normalize_standings(df)

        comp = COMPETITIONS[competition_key]
        data = self._api.get("standings", {"league": comp["api_football_id"], "season": season})
        rows = []
        for lb in data.get("response", []):
            for grp in lb.get("league", {}).get("standings", []):
                for t in grp:
                    rows.append({
                        "position":      t["rank"],
                        "team_id":       t["team"]["id"],
                        "team_name":     t["team"]["name"],
                        "team_logo":     t["team"]["logo"],
                        "played":        t["all"]["played"],
                        "won":           t["all"]["win"],
                        "drawn":         t["all"]["draw"],
                        "lost":          t["all"]["lose"],
                        "goals_for":     t["all"]["goals"]["for"],
                        "goals_against": t["all"]["goals"]["against"],
                        "goal_diff":     t["goalsDiff"],
                        "points":        t["points"],
                        "form":          t.get("form", ""),
                        "description":   t.get("description", ""),
                        "season":        season,
                        "competition":   competition_key,
                    })
        df = pd.DataFrame(rows)
        self.cache.set("standings", cache_id, df)
        return _normalize_standings(df)

    # ------------------------------------------------------------------ #
    # FIXTURES
    # ------------------------------------------------------------------ #
    def get_fixtures(self, competition_key: str, season: int = None,
                     team_id: int = None, from_date: str = None,
                     to_date: str = None, status: str = None,
                     force_refresh: bool = False) -> pd.DataFrame:
        season = self._season(competition_key, season)
        if self._using_fd():
            fd_status = {"FT": "FINISHED", "NS": "SCHEDULED", "TBD": "SCHEDULED"}.get(status)
            return self._fd.get_fixtures(
                competition_key, season,
                status=fd_status, date_from=from_date, date_to=to_date,
                force_refresh=force_refresh,
            )

        # ESPN para seasons > 2024
        if self._use_espn(competition_key, season):
            logger.info("ESPN fixtures %s %s", competition_key, season)
            return self._espn.get_fixtures(
                competition_key, season,
                from_date=from_date, to_date=to_date, status=status,
            )

        cache_id = f"{competition_key}_{season}"
        if team_id:   cache_id += f"_team{team_id}"
        if from_date: cache_id += f"_from{from_date}"
        today = datetime.now().strftime("%Y-%m-%d")

        # Jogos passados: cache permanente
        if to_date and to_date < today and not force_refresh:
            cached = self.cache.get("results", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)
        elif not force_refresh:
            cached = self.cache.get("fixtures", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        comp = COMPETITIONS[competition_key]
        params = {"league": comp["api_football_id"], "season": season}
        if team_id:   params["team"] = team_id
        if from_date: params["from"] = from_date
        if to_date:   params["to"]   = to_date
        if status:    params["status"] = status

        data = self._api.get("fixtures", params)
        rows = []
        for f in data.get("response", []):
            fix    = f["fixture"]
            teams  = f["teams"]
            goals  = f["goals"]
            score  = f.get("score", {})
            ft     = score.get("fulltime", {})
            rows.append({
                "fixture_id":   fix["id"],
                "date":         fix["date"][:19],
                "home_team_id": teams["home"]["id"],
                "home_team":    teams["home"]["name"],
                "away_team_id": teams["away"]["id"],
                "away_team":    teams["away"]["name"],
                "home_goals":   goals.get("home"),
                "away_goals":   goals.get("away"),
                "ft_home":      ft.get("home"),
                "ft_away":      ft.get("away"),
                "status":       fix["status"]["short"],
                "status_long":  fix["status"]["long"],
                "season":       season,
                "competition":  competition_key,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        cache_type = "results" if (to_date and to_date < today) else "fixtures"
        self.cache.set(cache_type, cache_id, df)
        return df

    # ------------------------------------------------------------------ #
    # UPCOMING FIXTURES
    # ------------------------------------------------------------------ #
    def get_upcoming_fixtures(self, competition_key: str, season: int = None,
                               days_ahead: int = 14, force_refresh: bool = False) -> pd.DataFrame:
        today   = datetime.now().strftime("%Y-%m-%d")
        to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        return self.get_fixtures(competition_key, season,
                                 from_date=today, to_date=to_date,
                                 force_refresh=force_refresh)

    # ------------------------------------------------------------------ #
    # TIMES
    # ------------------------------------------------------------------ #
    def get_teams(self, competition_key: str, season: int = None,
                  force_refresh: bool = False) -> pd.DataFrame:
        season = self._season(competition_key, season)
        if self._using_fd():
            return self._fd.get_teams(competition_key, season, force_refresh)

        # ESPN para seasons > 2024
        if self._use_espn(competition_key, season):
            logger.info("ESPN teams %s %s", competition_key, season)
            df = self._espn.get_teams(competition_key, season)
            if not df.empty:
                return df

        cache_id = f"{competition_key}_{season}_teams"
        if not force_refresh:
            cached = self.cache.get("team_info", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        comp = COMPETITIONS[competition_key]
        data = self._api.get("teams", {"league": comp["api_football_id"], "season": season})
        rows = []
        for item in data.get("response", []):
            t = item["team"]
            v = item.get("venue", {})
            rows.append({
                "team_id":    t["id"],
                "team_name":  t["name"],
                "team_logo":  t["logo"],
                "team_code":  t.get("code"),
                "founded":    t.get("founded"),
                "venue_name": v.get("name"),
                "venue_city": v.get("city"),
                "competition": competition_key,
                "season":      season,
            })
        df = pd.DataFrame(rows)
        self.cache.set("team_info", cache_id, df)
        return df

    # ------------------------------------------------------------------ #
    # LESÕES
    # ------------------------------------------------------------------ #
    def get_injuries(self, team_id: int, season: int = None,
                     force_refresh: bool = False) -> pd.DataFrame:
        if self._using_fd():
            return pd.DataFrame()
        season = season or DEFAULT_SEASON
        cache_id = f"injuries_team{team_id}_{season}"
        if not force_refresh:
            cached = self.cache.get("injuries", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)
        try:
            data = self._api.get("injuries", {"team": team_id, "season": season})
            rows = []
            for item in data.get("response", []):
                p = item["player"]
                rows.append({
                    "player_id":   p["id"],
                    "player_name": p["name"],
                    "reason":      p.get("reason", ""),
                    "team_id":     team_id,
                })
            df = pd.DataFrame(rows)
            self.cache.set("injuries", cache_id, df)
            return df
        except Exception as e:
            logger.warning("Lesoes indisponiveis para time %s: %s", team_id, e)
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # H2H
    # ------------------------------------------------------------------ #
    def get_h2h(self, team1_id: int, team2_id: int,
                last: int = 10, force_refresh: bool = False) -> pd.DataFrame:
        if self._using_fd():
            return pd.DataFrame()
        cache_id = f"h2h_{min(team1_id, team2_id)}_{max(team1_id, team2_id)}"
        if not force_refresh:
            cached = self.cache.get("h2h", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)
        try:
            data = self._api.get("fixtures/headtohead", {
                "h2h": f"{team1_id}-{team2_id}", "last": last,
            })
            rows = []
            for f in data.get("response", []):
                teams = f["teams"]
                goals = f["goals"]
                ft    = f.get("score", {}).get("fulltime", {})
                rows.append({
                    "fixture_id":   f["fixture"]["id"],
                    "date":         f["fixture"]["date"][:10],
                    "home_team_id": teams["home"]["id"],
                    "home_team":    teams["home"]["name"],
                    "away_team_id": teams["away"]["id"],
                    "away_team":    teams["away"]["name"],
                    "home_goals":   goals.get("home"),
                    "away_goals":   goals.get("away"),
                    "ft_home":      ft.get("home"),
                    "ft_away":      ft.get("away"),
                    "status":       f["fixture"]["status"]["short"],
                })
            df = pd.DataFrame(rows)
            if not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date", ascending=False)
            self.cache.set("h2h", cache_id, df)
            return df
        except Exception as e:
            logger.warning("H2H indisponivel: %s", e)
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # JOGOS POR DATA (cross-competition)
    # ------------------------------------------------------------------ #
    def get_matches_by_date(self, date_from: str, date_to: str,
                             competitions: list = None,
                             force_refresh: bool = False) -> pd.DataFrame:
        if self._using_fd():
            return self._fd.get_matches_by_date(date_from, date_to, competitions, force_refresh)
        frames = []
        comp_keys = competitions or list(COMPETITIONS.keys())
        for key in comp_keys:
            try:
                df = self.get_fixtures(key, from_date=date_from, to_date=date_to,
                                       force_refresh=force_refresh)
                if df is not None and not df.empty:
                    frames.append(df)
            except Exception:
                pass
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # ------------------------------------------------------------------ #
    # STATS DO TIME
    # ------------------------------------------------------------------ #
    def get_team_stats(self, team_id: int, competition_key: str,
                       season: int = None, force_refresh: bool = False) -> dict:
        if self._using_fd():
            return {}
        season = self._season(competition_key, season)
        comp   = COMPETITIONS.get(competition_key, {})
        league = comp.get("api_football_id")
        if not league:
            return {}
        cache_id = f"stats_{team_id}_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("fbref_stats", cache_id)
            if cached is not None:
                return cached if isinstance(cached, dict) else {}
        try:
            data = self._api.get("teams/statistics", {
                "team": team_id, "league": league, "season": season,
            })
            resp = data.get("response", {})
            result = {
                "xg_for":          resp.get("goals", {}).get("for", {}).get("average", {}).get("total", 0),
                "xg_against":      resp.get("goals", {}).get("against", {}).get("average", {}).get("total", 0),
                "possession":      resp.get("possession", {}).get("average", 0),
                "shots_on_target": resp.get("shots", {}).get("on", {}).get("average", 0),
            }
            self.cache.set("fbref_stats", cache_id, result)
            return result
        except Exception as e:
            logger.warning("Stats indisponiveis para time %s: %s", team_id, e)
            return {}


# ================================================================== #
# SINGLETON HELPERS
# ================================================================== #
_fetcher_instance = None

def get_fetcher() -> FootballDataFetcher:
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = FootballDataFetcher()
    return _fetcher_instance


class _FBrefStub:
    def get_team_stats(self, *args, **kwargs):   return {}
    def get_player_stats(self, *args, **kwargs): return pd.DataFrame()

_fbref_instance = None

def get_fbref():
    global _fbref_instance
    if _fbref_instance is None:
        try:
            from src.fetchers.fbref import FBrefFetcher
            _fbref_instance = FBrefFetcher()
        except Exception:
            _fbref_instance = _FBrefStub()
    return _fbref_instance
