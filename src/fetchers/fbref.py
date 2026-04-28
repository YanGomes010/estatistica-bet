"""
fbref.py - Fetcher para dados avançados do FBref via soccerdata

Fornece:
  - xG (Expected Goals) por jogo e temporada
  - Posse de bola, finalizações, criação de chances
  - Estatísticas individuais de jogadores

soccerdata: https://soccerdata.readthedocs.io/
Instale com: pip install soccerdata
"""
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from config import COMPETITIONS, DEFAULT_SEASON, CACHE_RAW_DIR
from src.cache.cache_manager import get_cache

logger = logging.getLogger(__name__)

# soccerdata usa pasta própria para cache de dados brutos
SOCCERDATA_CACHE = CACHE_RAW_DIR / "soccerdata"
SOCCERDATA_CACHE.mkdir(exist_ok=True)


class FBrefFetcher:
    """
    Busca dados avançados do FBref usando a biblioteca soccerdata.
    Cache automático: 24 horas para estatísticas de temporada.
    """

    # Mapeamento dos slugs internos para os nomes que o soccerdata/FBref usa
    FBREF_LEAGUE_MAP = {
        "brasileirao_a":  "BRA-Campeonato Brasileiro Série A",
        "premier_league": "ENG-Premier League",
        "la_liga":        "ESP-La Liga",
        "ligue_1":        "FRA-Ligue 1",
        "bundesliga":     "GER-Bundesliga",
        "serie_a_it":     "ITA-Serie A",
        "champions_league": "INT-UEFA Champions League",
        "libertadores":   "INT-Copa Libertadores",
    }

    def __init__(self):
        self.cache = get_cache()
        self._check_soccerdata()

    def _check_soccerdata(self):
        try:
            import soccerdata  # noqa
            self._available = True
        except ImportError:
            self._available = False
            logger.warning(
                "soccerdata não instalado. Dados do FBref não disponíveis. "
                "Execute: pip install soccerdata"
            )

    def _get_fbref_reader(self, league: str, seasons: list):
        """Retorna instância de FBref reader."""
        import soccerdata as sd
        return sd.FBref(
            leagues=league,
            seasons=seasons,
            data_dir=SOCCERDATA_CACHE,
        )

    # ------------------------------------------------------------------ #
    # xG POR JOGO
    # ------------------------------------------------------------------ #
    def get_season_xg(
        self,
        competition_key: str,
        season: int = DEFAULT_SEASON,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Retorna dados de xG (Expected Goals) para todos os jogos da temporada.
        Colunas: home_team, away_team, home_xg, away_xg, home_goals, away_goals, date
        """
        cache_id = f"fbref_xg_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("fbref_stats", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        if not self._available:
            return self._empty_xg_df()

        fbref_league = self.FBREF_LEAGUE_MAP.get(competition_key)
        if not fbref_league:
            logger.warning(f"FBref: competição '{competition_key}' não mapeada")
            return self._empty_xg_df()

        try:
            reader = self._get_fbref_reader(fbref_league, [season])
            df = reader.read_schedule()
            df = df.reset_index()

            # Normaliza colunas
            col_map = {}
            for col in df.columns:
                col_lower = col.lower().replace(" ", "_")
                col_map[col] = col_lower
            df = df.rename(columns=col_map)

            # Seleciona colunas relevantes com fallbacks
            keep = {}
            for target, candidates in {
                "date":       ["date"],
                "home_team":  ["home_team", "home"],
                "away_team":  ["away_team", "away"],
                "home_goals": ["home_goals", "score_home"],
                "away_goals": ["away_goals", "score_away"],
                "home_xg":    ["home_xg", "xg_home", "xg"],
                "away_xg":    ["away_xg", "xg_away"],
            }.items():
                for c in candidates:
                    if c in df.columns:
                        keep[c] = target
                        break

            df = df.rename(columns=keep)[[v for v in keep.values() if v in df.columns.tolist() + list(keep.values())]]
            df = df[[c for c in ["date","home_team","away_team","home_goals","away_goals","home_xg","away_xg"] if c in df.columns]]

            self.cache.set("fbref_stats", cache_id, df)
            return df

        except Exception as e:
            logger.error(f"Erro ao buscar xG do FBref: {e}")
            return self._empty_xg_df()

    # ------------------------------------------------------------------ #
    # ESTATÍSTICAS DE ATAQUE/CRIAÇÃO DE EQUIPES
    # ------------------------------------------------------------------ #
    def get_team_shooting_stats(
        self,
        competition_key: str,
        season: int = DEFAULT_SEASON,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Estatísticas de finalização por equipe:
        Shots, SoT, xG, npxG, etc.
        """
        cache_id = f"fbref_shooting_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("fbref_stats", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        if not self._available:
            return pd.DataFrame()

        fbref_league = self.FBREF_LEAGUE_MAP.get(competition_key)
        if not fbref_league:
            return pd.DataFrame()

        try:
            reader = self._get_fbref_reader(fbref_league, [season])
            df = reader.read_team_season_stats(stat_type="shooting")
            df = df.reset_index()
            self.cache.set("fbref_stats", cache_id, df)
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar stats de finalização: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # ESTATÍSTICAS DE POSSE / PASSE
    # ------------------------------------------------------------------ #
    def get_team_possession_stats(
        self,
        competition_key: str,
        season: int = DEFAULT_SEASON,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Posse de bola e estatísticas de passe por equipe."""
        cache_id = f"fbref_possession_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("fbref_stats", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        if not self._available:
            return pd.DataFrame()

        fbref_league = self.FBREF_LEAGUE_MAP.get(competition_key)
        if not fbref_league:
            return pd.DataFrame()

        try:
            reader = self._get_fbref_reader(fbref_league, [season])
            df = reader.read_team_season_stats(stat_type="possession")
            df = df.reset_index()
            self.cache.set("fbref_stats", cache_id, df)
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar stats de posse: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # STATS DE JOGADORES
    # ------------------------------------------------------------------ #
    def get_player_stats(
        self,
        competition_key: str,
        season: int = DEFAULT_SEASON,
        stat_type: str = "standard",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Estatísticas individuais de jogadores.
        stat_type: standard | shooting | passing | defense | gca | keeper
        """
        cache_id = f"fbref_players_{stat_type}_{competition_key}_{season}"
        if not force_refresh:
            cached = self.cache.get("fbref_stats", cache_id)
            if cached is not None:
                return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)

        if not self._available:
            return pd.DataFrame()

        fbref_league = self.FBREF_LEAGUE_MAP.get(competition_key)
        if not fbref_league:
            return pd.DataFrame()

        try:
            reader = self._get_fbref_reader(fbref_league, [season])
            df = reader.read_player_season_stats(stat_type=stat_type)
            df = df.reset_index()
            self.cache.set("fbref_stats", cache_id, df)
            return df
        except Exception as e:
            logger.error(f"Erro ao buscar player stats ({stat_type}): {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------ #
    # HELPERS
    # ------------------------------------------------------------------ #
    @staticmethod
    def _empty_xg_df() -> pd.DataFrame:
        return pd.DataFrame(columns=[
            "date", "home_team", "away_team",
            "home_goals", "away_goals", "home_xg", "away_xg"
        ])

    def is_available(self) -> bool:
        return self._available


# Instância global
_fbref_fetcher: Optional[FBrefFetcher] = None

def get_fbref() -> FBrefFetcher:
    global _fbref_fetcher
    if _fbref_fetcher is None:
        _fbref_fetcher = FBrefFetcher()
    return _fbref_fetcher
