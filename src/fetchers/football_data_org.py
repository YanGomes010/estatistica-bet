"""
football_data_org.py - Cliente completo para football-data.org v4

Plano gratuito inclui:
  Premier League, La Liga, Bundesliga, Serie A, Ligue 1,
  Champions League, Europa League, Conference League,
  Copa do Mundo, Eurocopa, e mais.

  ⚠️  Brasileirão NÃO está no plano gratuito.
      Para Brasileirão use API-Football (RapidAPI).

Limite gratuito: 10 requisições/minuto
Documentação: https://www.football-data.org/documentation/quickstart
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from config import FOOTBALL_DATA_API_KEY, FOOTBALL_DATA_BASE_URL
from src.cache.cache_manager import get_cache

logger = logging.getLogger(__name__)

# ── Competições disponíveis no plano gratuito ─────────────────────
FD_FREE_COMPETITIONS = {
    "premier_league":   "PL",
    "la_liga":          "PD",
    "bundesliga":       "BL1",
    "serie_a_it":       "SA",
    "ligue_1":          "FL1",
    "champions_league": "CL",
    "europa_league":    "EL",
}

# Competições que NÃO estão no plano gratuito (requerem API-Football/RapidAPI)
FD_PAID_ONLY = {
    "brasileirao_a", "brasileirao_b", "copa_brasil",
    "sudamericana", "libertadores",   # CLI requer plano pago no FD.org
}


def get_fd_season(competition_key: str) -> int:
    """
    Retorna o ano de temporada correto para football-data.org.

    European leagues (PL, PD, etc.) usam o ano de INÍCIO da temporada.
    Em abril de 2026, a temporada 2025/26 iniciou em 2025 → retorna 2025.
    Brazilian leagues usam o ano corrente → retorna 2026.
    """
    now = datetime.now()
    year = now.year
    month = now.month

    european = {
        "premier_league", "la_liga", "bundesliga", "serie_a_it",
        "ligue_1", "champions_league", "europa_league",
    }
    if competition_key in european:
        # Temporada europeia começa em agosto; antes de julho = temporada anterior
        return year - 1 if month < 7 else year
    return year  # Ligas sul-americanas/Brasil usam ano corrente


class FootballDataOrgClient:
    """Cliente HTTP para football-data.org v4."""

    BASE_URL = FOOTBALL_DATA_BASE_URL
    RATE_DELAY = 6.5   # 10 req/min = 1 a cada 6s

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": FOOTBALL_DATA_API_KEY,
            "Content-Type": "application/json",
        })
        self._last_request = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.RATE_DELAY:
            time.sleep(self.RATE_DELAY - elapsed)
        self._last_request = time.time()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15))
    def get(self, endpoint: str, params: dict = None) -> dict:
        if not FOOTBALL_DATA_API_KEY or FOOTBALL_DATA_API_KEY == "sua_chave_aqui":
            raise ValueError(
                "FOOTBALL_DATA_API_KEY não configurada. "
                "Edite o .env e insira sua chave de https://www.football-data.org"
            )
        self._throttle()
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        resp = self.session.get(url, params=params or {}, timeout=15)

        if resp.status_code == 403:
            raise PermissionError(
                f"Acesso negado à competição. "
                f"Verifique se ela está no seu plano (gratuito não inclui Brasileirão). "
                f"URL: {url}"
            )
        if resp.status_code == 429:
            raise RuntimeError("Rate limit atingido. Aguarde 1 minuto.")
        resp.raise_for_status()
        return resp.json()


class FDOrgFetcher:
    """Fetcher de alto nível para football-data.org com cache automático."""

    def __init__(self):
        self.client = FootballDataOrgClient()
        self.cache = get_cache()

    # ── Classificação ──────────────────────────────────────────────
    def get_standings(
        self,
        competition_key: str,
        season: int = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        if competition_key in FD_PAID_ONLY:
            raise PermissionError(
                f"'{competition_key}' não está disponível no plano gratuito do football-data.org. "
                "Configure API-Football (RapidAPI) no .env para acessar essa competição."
            )

        code = FD_FREE_COMPETITIONS.get(competition_key)
        if not code:
            raise ValueError(f"Competição '{competition_key}' não mapeada para football-data.org")

        if season is None:
            season = get_fd_season(competition_key)

        cache_id = f"fd_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("standings", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        logger.info(f"[FD.org] Classificação: {competition_key} season={season}")
        data = self.client.get(f"competitions/{code}/standings", {"season": season})

        rows = []
        for group in data.get("standings", []):
            if group.get("type") != "TOTAL":
                continue
            for t in group.get("table", []):
                team = t.get("team", {})
                rows.append({
                    "position":      t.get("position"),
                    "team_id":       team.get("id"),
                    "team_name":     team.get("name") or team.get("shortName", ""),
                    "team_logo":     team.get("crest", ""),
                    "played":        t.get("playedGames", 0),
                    "won":           t.get("won", 0),
                    "drawn":         t.get("draw", 0),
                    "lost":          t.get("lost", 0),
                    "goals_for":     t.get("goalsFor", 0),
                    "goals_against": t.get("goalsAgainst", 0),
                    "goal_diff":     t.get("goalDifference", 0),
                    "points":        t.get("points", 0),
                    "form":          t.get("form", ""),
                    "description":   t.get("description", ""),
                    "season":        season,
                    "competition":   competition_key,
                })

        df = pd.DataFrame(rows)
        self.cache.set("standings", cache_id, df)
        return df

    # ── Jogos de uma competição ────────────────────────────────────
    def get_fixtures(
        self,
        competition_key: str,
        season: int = None,
        status: str = None,
        date_from: str = None,
        date_to: str = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        if competition_key in FD_PAID_ONLY:
            raise PermissionError(
                f"'{competition_key}' não está no plano gratuito do football-data.org."
            )

        code = FD_FREE_COMPETITIONS.get(competition_key)
        if not code:
            raise ValueError(f"Competição '{competition_key}' não mapeada")

        if season is None:
            season = get_fd_season(competition_key)

        cache_id = f"fd_fix_{competition_key}_{season}"
        if date_from:
            cache_id += f"_{date_from}"
        if status:
            cache_id += f"_{status}"

        today = datetime.now().strftime("%Y-%m-%d")
        is_historical = date_to and date_to < today
        cat = "results" if is_historical else "fixtures"

        if not force_refresh:
            cached = self.cache.get(cat, cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        params = {"season": season}
        if status:
            params["status"] = status
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to

        logger.info(f"[FD.org] Fixtures: {competition_key} season={season} status={status}")
        data = self.client.get(f"competitions/{code}/matches", params)

        df = self._parse_matches(data.get("matches", []), competition_key)
        self.cache.set(cat, cache_id, df, permanent=is_historical)
        return df

    # ── Jogos de HOJE / semana (todas as competições de uma vez) ──
    def get_matches_by_date(
        self,
        date_from: str,
        date_to: str,
        competitions: list = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Retorna todos os jogos disponíveis em um período (cross-competition).
        competitions: lista de códigos FD (ex: ['PL','CL']). None = todos disponíveis.
        """
        cache_id = f"fd_matches_{date_from}_{date_to}"
        if competitions:
            cache_id += "_" + "_".join(sorted(competitions))

        today = datetime.now().strftime("%Y-%m-%d")
        is_past = date_to < today
        cat = "results" if is_past else "fixtures"

        if not force_refresh:
            cached = self.cache.get(cat, cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        params = {"dateFrom": date_from, "dateTo": date_to}
        if competitions:
            params["competitions"] = ",".join(competitions)

        logger.info(f"[FD.org] Matches {date_from} → {date_to}")
        data = self.client.get("matches", params)

        df = self._parse_matches(data.get("matches", []))
        self.cache.set(cat, cache_id, df, permanent=is_past)
        return df

    # ── Times de uma competição ────────────────────────────────────
    def get_teams(
        self,
        competition_key: str,
        season: int = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        code = FD_FREE_COMPETITIONS.get(competition_key)
        if not code:
            return pd.DataFrame()

        if season is None:
            season = get_fd_season(competition_key)

        cache_id = f"fd_teams_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("team_info", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        data = self.client.get(f"competitions/{code}/teams", {"season": season})
        rows = []
        for t in data.get("teams", []):
            rows.append({
                "team_id":   t.get("id"),
                "team_name": t.get("name") or t.get("shortName", ""),
                "team_logo": t.get("crest", ""),
                "team_code": t.get("tla", ""),
                "competition": competition_key,
                "season": season,
            })
        df = pd.DataFrame(rows)
        self.cache.set("team_info", cache_id, df)
        return df

    # ── Últimos jogos de um time ───────────────────────────────────
    def get_team_recent_fixtures(
        self,
        team_id: int,
        last_n: int = 10,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        cache_id = f"fd_team_{team_id}_last{last_n}"
        if not force_refresh:
            cached = self.cache.get("results", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        params = {"limit": last_n, "status": "FINISHED"}
        data = self.client.get(f"teams/{team_id}/matches", params)
        df = self._parse_matches(data.get("matches", []))
        if not df.empty:
            df["is_home"] = df["home_team_id"] == team_id
            df = df.sort_values("date", ascending=False)
        self.cache.set("results", cache_id, df, permanent=True)
        return df

    # ── H2H ───────────────────────────────────────────────────────
    def get_h2h(
        self,
        fixture_id: int,
        last: int = 10,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """FD.org fornece H2H via endpoint de partida específica."""
        cache_id = f"fd_h2h_{fixture_id}"
        if not force_refresh:
            cached = self.cache.get("h2h", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        data = self.client.get(f"matches/{fixture_id}/head2head",
                               {"limit": last})
        df = self._parse_matches(data.get("matches", []))
        self.cache.set("h2h", cache_id, df, permanent=True)
        return df

    # ── Parser universal de partidas ──────────────────────────────
    @staticmethod
    def _parse_matches(matches: list, default_comp: str = "") -> pd.DataFrame:
        rows = []
        for m in matches:
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            score = m.get("score", {})
            ft = score.get("fullTime", {})
            ht = score.get("halfTime", {})
            comp = m.get("competition", {})
            rows.append({
                "fixture_id":      m.get("id"),
                "date":            m.get("utcDate"),
                "status":          m.get("status", ""),
                "matchday":        m.get("matchday"),
                "home_team_id":    home.get("id"),
                "home_team":       home.get("name") or home.get("shortName", ""),
                "home_team_logo":  home.get("crest", ""),
                "away_team_id":    away.get("id"),
                "away_team":       away.get("name") or away.get("shortName", ""),
                "away_team_logo":  away.get("crest", ""),
                "home_goals":      ft.get("home"),
                "away_goals":      ft.get("away"),
                "ht_home":         ht.get("home"),
                "ht_away":         ht.get("away"),
                "competition":     comp.get("code", default_comp),
                "competition_name": comp.get("name", default_comp),
                "season":          m.get("season", {}).get("startDate", "")[:4],
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.sort_values("date")
        return df


# ── Mapeamento de status FD.org → legível ──────────────────────────
FD_STATUS_MAP = {
    "SCHEDULED":   ("🕐", "Agendado"),
    "TIMED":       ("🕐", "Agendado"),
    "IN_PLAY":     ("🔴", "Ao Vivo"),
    "PAUSED":      ("⏸️", "Intervalo"),
    "FINISHED":    ("✅", "Encerrado"),
    "POSTPONED":   ("⚠️", "Adiado"),
    "SUSPENDED":   ("⛔", "Suspenso"),
    "CANCELLED":   ("❌", "Cancelado"),
}


_fd_fetcher: Optional[FDOrgFetcher] = None

def get_fd_fetcher() -> FDOrgFetcher:
    global _fd_fetcher
    if _fd_fetcher is None:
        _fd_fetcher = FDOrgFetcher()
    return _fd_fetcher
