"""
config.py - Configurações centrais do Football Analytics App
Carrega variáveis de ambiente e define constantes globais.
"""
import os
from datetime import datetime as _dt
from pathlib import Path
from dotenv import load_dotenv

# --- Carrega .env ---
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# ============================================================
# CAMINHOS
# ============================================================
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CACHE_RAW_DIR = CACHE_DIR / "raw"
CACHE_PROCESSED_DIR = CACHE_DIR / "processed"
DB_PATH = DATA_DIR / "db" / "football.db"

for d in [CACHE_RAW_DIR, CACHE_PROCESSED_DIR, DATA_DIR / "db"]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# CHAVES DE API
# ============================================================
RAPIDAPI_KEY        = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST       = os.getenv("RAPIDAPI_HOST", "api-football-v1.p.rapidapi.com")
APISPORTS_KEY       = os.getenv("APISPORTS_KEY", "")          # API-Sports direto (sem RapidAPI)
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")
PRIMARY_API         = os.getenv("PRIMARY_API", "api_football")

# URL base: prefere api-sports.io direto; cai para RapidAPI se só tiver RAPIDAPI_KEY
API_FOOTBALL_BASE_URL = (
    "https://v3.football.api-sports.io"
    if APISPORTS_KEY
    else f"https://{RAPIDAPI_HOST}"
)

# ============================================================
# CONFIGURAÇÕES DE CACHE (TTL em segundos)
# ============================================================
CACHE_TTL = {
    "standings":   int(os.getenv("CACHE_STANDINGS_TTL_HOURS", 12)) * 3600,
    "fixtures":    int(os.getenv("CACHE_FIXTURES_TTL_HOURS", 6)) * 3600,
    "results":     None,
    "team_info":   7 * 24 * 3600,
    "players":     24 * 3600,
    "injuries":    6 * 3600,
    "fbref_stats": 24 * 3600,
    "h2h":         None,
    "live":        60,
}

# ============================================================
# TEMPORADA E TIMEZONE
# ============================================================
_now = _dt.now()
_EUROPEAN = frozenset({
    "premier_league", "la_liga", "bundesliga", "serie_a_it",
    "ligue_1", "champions_league", "europa_league", "conference_league",
    "championship", "la_liga2", "bundesliga_2", "serie_b_it", "ligue_2",
    "primeira_liga", "eredivisie", "pro_league", "super_lig", "scottish_prem",
})


def get_current_season(competition_key="brasileirao_a"):
    """
    Retorna o ano da temporada atual para a competição.

    Limites do plano gratuito api-sports.io: máx. season=2024.
    Football-data.org não tem essa restrição para ligas europeias.
    """
    override = os.getenv("DEFAULT_SEASON")
    if override:
        return int(override)
    year, month = _dt.now().year, _dt.now().month
    if competition_key in _EUROPEAN:
        # Temporada europeia: 2025 = agosto/2025 a maio/2026
        return year - 1 if month < 7 else year
    return year


# Temporada máxima disponível no plano free do api-sports.io
APISPORTS_FREE_MAX_SEASON = 2024


DEFAULT_SEASON = int(os.getenv("DEFAULT_SEASON", str(_now.year)))
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")

# ============================================================
# COMPETIÇÕES SUPORTADAS
# ============================================================
COMPETITIONS = {
    # ════════════════════════════════════════════════════════
    # BRASIL
    # ════════════════════════════════════════════════════════
    "brasileirao_a": {
        "name": "Brasileirão Série A",
        "country": "Brazil",
        "flag": "🇧🇷",
        "api_football_id": 71,
        "football_data_id": "BSA",
        "fbref_id": "24",
        "fbref_name": "Serie A",
        "group": "Brasil",
        "seasons_available": list(range(2015, 2028)),
    },
    "brasileirao_b": {
        "name": "Brasileirão Série B",
        "country": "Brazil",
        "flag": "🇧🇷",
        "api_football_id": 72,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Brasil",
        "seasons_available": list(range(2018, 2028)),
    },
    "brasileirao_c": {
        "name": "Brasileirão Série C",
        "country": "Brazil",
        "flag": "🇧🇷",
        "api_football_id": 75,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Brasil",
        "seasons_available": list(range(2020, 2028)),
    },
    "copa_brasil": {
        "name": "Copa do Brasil",
        "country": "Brazil",
        "flag": "🇧🇷",
        "api_football_id": 73,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Brasil",
        "seasons_available": list(range(2018, 2028)),
    },
    "copa_nordeste": {
        "name": "Copa do Nordeste",
        "country": "Brazil",
        "flag": "🇧🇷",
        "api_football_id": 735,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Brasil",
        "seasons_available": list(range(2020, 2028)),
    },
    # ════════════════════════════════════════════════════════
    # AMÉRICA DO SUL
    # ════════════════════════════════════════════════════════
    "libertadores": {
        "name": "Copa Libertadores",
        "country": "South America",
        "flag": "🌎",
        "api_football_id": 13,
        "football_data_id": "CLI",
        "fbref_id": "14",
        "fbref_name": "Copa Libertadores",
        "group": "América do Sul",
        "seasons_available": list(range(2018, 2028)),
    },
    "sudamericana": {
        "name": "Copa Sul-Americana",
        "country": "South America",
        "flag": "🌎",
        "api_football_id": 11,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    "liga_argentina": {
        "name": "Liga Profesional Argentina",
        "country": "Argentina",
        "flag": "🇦🇷",
        "api_football_id": 128,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    "liga_colombiana": {
        "name": "Liga BetPlay Colombia",
        "country": "Colombia",
        "flag": "🇨🇴",
        "api_football_id": 239,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    "liga_chilena": {
        "name": "Primera División Chile",
        "country": "Chile",
        "flag": "🇨🇱",
        "api_football_id": 265,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    "liga_uruguaia": {
        "name": "Primera División Uruguai",
        "country": "Uruguay",
        "flag": "🇺🇾",
        "api_football_id": 268,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    "liga_mexicana": {
        "name": "Liga MX",
        "country": "Mexico",
        "flag": "🇲🇽",
        "api_football_id": 262,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Sul",
        "seasons_available": list(range(2020, 2028)),
    },
    # ════════════════════════════════════════════════════════
    # EUROPA — ELITE
    # ════════════════════════════════════════════════════════
    "champions_league": {
        "name": "UEFA Champions League",
        "country": "Europe",
        "flag": "🏆",
        "api_football_id": 2,
        "football_data_id": "CL",
        "fbref_id": "8",
        "fbref_name": "Champions League",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "europa_league": {
        "name": "UEFA Europa League",
        "country": "Europe",
        "flag": "🇪🇺",
        "api_football_id": 3,
        "football_data_id": "EL",
        "fbref_id": "19",
        "fbref_name": "Europa League",
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "conference_league": {
        "name": "UEFA Conference League",
        "country": "Europe",
        "flag": "🇪🇺",
        "api_football_id": 848,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2021, 2028)),
    },
    "premier_league": {
        "name": "Premier League",
        "country": "England",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "api_football_id": 39,
        "football_data_id": "PL",
        "fbref_id": "9",
        "fbref_name": "Premier League",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "championship": {
        "name": "EFL Championship",
        "country": "England",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "api_football_id": 40,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "la_liga": {
        "name": "La Liga",
        "country": "Spain",
        "flag": "🇪🇸",
        "api_football_id": 140,
        "football_data_id": "PD",
        "fbref_id": "12",
        "fbref_name": "La Liga",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "la_liga2": {
        "name": "La Liga 2",
        "country": "Spain",
        "flag": "🇪🇸",
        "api_football_id": 141,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "flag": "🇩🇪",
        "api_football_id": 78,
        "football_data_id": "BL1",
        "fbref_id": "20",
        "fbref_name": "Fussball-Bundesliga",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "bundesliga_2": {
        "name": "2. Bundesliga",
        "country": "Germany",
        "flag": "🇩🇪",
        "api_football_id": 79,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "serie_a_it": {
        "name": "Serie A (Itália)",
        "country": "Italy",
        "flag": "🇮🇹",
        "api_football_id": 135,
        "football_data_id": "SA",
        "fbref_id": "11",
        "fbref_name": "Serie A",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "serie_b_it": {
        "name": "Serie B (Itália)",
        "country": "Italy",
        "flag": "🇮🇹",
        "api_football_id": 136,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "ligue_1": {
        "name": "Ligue 1",
        "country": "France",
        "flag": "🇫🇷",
        "api_football_id": 61,
        "football_data_id": "FL1",
        "fbref_id": "13",
        "fbref_name": "Ligue 1",
        "group": "Europa",
        "seasons_available": list(range(2018, 2028)),
    },
    "ligue_2": {
        "name": "Ligue 2",
        "country": "France",
        "flag": "🇫🇷",
        "api_football_id": 62,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "primeira_liga": {
        "name": "Primeira Liga",
        "country": "Portugal",
        "flag": "🇵🇹",
        "api_football_id": 94,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "eredivisie": {
        "name": "Eredivisie",
        "country": "Netherlands",
        "flag": "🇳🇱",
        "api_football_id": 88,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "pro_league": {
        "name": "Pro League (Bélgica)",
        "country": "Belgium",
        "flag": "🇧🇪",
        "api_football_id": 144,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "super_lig": {
        "name": "Süper Lig",
        "country": "Turkey",
        "flag": "🇹🇷",
        "api_football_id": 203,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    "scottish_prem": {
        "name": "Scottish Premiership",
        "country": "Scotland",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "api_football_id": 179,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "Europa",
        "seasons_available": list(range(2020, 2028)),
    },
    # ════════════════════════════════════════════════════════
    # NORTE-AMÉRICA
    # ════════════════════════════════════════════════════════
    "mls": {
        "name": "MLS",
        "country": "USA",
        "flag": "🇺🇸",
        "api_football_id": 253,
        "football_data_id": None,
        "fbref_id": None,
        "fbref_name": None,
        "group": "América do Norte",
        "seasons_available": list(range(2020, 2028)),
    },
}

COMP_BY_API_ID = {v["api_football_id"]: k for k, v in COMPETITIONS.items()}

COMPETITION_GROUPS = {}
for key, comp in COMPETITIONS.items():
    group = comp["group"]
    COMPETITION_GROUPS.setdefault(group, []).append(key)

FORM_GAMES = 5
H2H_GAMES  = 10

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"

FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}
LIVE_STATUSES     = {"1H", "2H", "ET", "P", "BT", "HT", "LIVE"}
UPCOMING_STATUSES = {"NS", "TBD"}


def get_competition(key: str) -> dict:
    if key not in COMPETITIONS:
        raise ValueError(f"Competicao '{key}' nao encontrada.")
    return COMPETITIONS[key]


def list_competitions_by_group():
    result = {}
    for group, keys in COMPETITION_GROUPS.items():
        result[group] = [
            {"key": k, "name": COMPETITIONS[k]["name"],
             "flag": COMPETITIONS[k]["flag"], "country": COMPETITIONS[k]["country"]}
            for k in keys
        ]
    return result
