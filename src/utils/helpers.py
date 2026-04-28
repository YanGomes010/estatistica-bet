"""
helpers.py - Utilitários gerais do Football Analytics
"""
import pandas as pd
from datetime import datetime
import pytz
from config import TIMEZONE, COMPETITIONS


def format_date_br(dt) -> str:
    """Formata datetime para exibição em português BR."""
    if pd.isna(dt):
        return "-"
    if isinstance(dt, str):
        dt = pd.to_datetime(dt)
    try:
        tz = pytz.timezone(TIMEZONE)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(dt)[:16]


def format_score(home_goals, away_goals) -> str:
    """Formata placar. Trata None e NaN (float) com segurança."""
    def _safe_int(v):
        try:
            if v is None:
                return "-"
            if pd.isna(v):   # captura float NaN, pd.NA, np.nan
                return "-"
            return int(v)
        except (ValueError, TypeError):
            return "-"
    return f"{_safe_int(home_goals)} × {_safe_int(away_goals)}"


def result_color(result: str) -> str:
    """Cor CSS para resultado."""
    return {"W": "#4CAF50", "D": "#FFC107", "L": "#F44336"}.get(result, "#9E9E9E")


def competition_options() -> list:
    """Retorna lista de opções para selectbox do Streamlit."""
    return [
        (f"{c['flag']} {c['name']}", key)
        for key, c in COMPETITIONS.items()
    ]


def season_options(competition_key: str) -> list:
    """Retorna temporadas disponíveis para uma competição."""
    comp = COMPETITIONS.get(competition_key, {})
    seasons = comp.get("seasons_available", list(range(2020, 2028)))
    return sorted(seasons, reverse=True)


def check_api_configured() -> dict:
    """
    Verifica quais APIs estão configuradas.
    Aceita APISPORTS_KEY (api-sports.io direto) OU RAPIDAPI_KEY como api_football.
    ESPN é sempre disponível (sem chave), por isso api_football=True quando
    PRIMARY_API=api_football mesmo sem chave de histórico.
    """
    from config import RAPIDAPI_KEY, FOOTBALL_DATA_API_KEY, APISPORTS_KEY, PRIMARY_API
    _invalid = ("", "sua_chave_aqui")
    has_apisports = bool(APISPORTS_KEY and APISPORTS_KEY not in _invalid)
    has_rapidapi  = bool(RAPIDAPI_KEY  and RAPIDAPI_KEY  not in _invalid)
    has_fd        = bool(FOOTBALL_DATA_API_KEY and FOOTBALL_DATA_API_KEY not in _invalid)

    # api_football = tem chave de api-sports/rapidapi OU é o modo primário
    # (ESPN cobre 2025/2026+ sem chave nenhuma)
    has_api_football = has_apisports or has_rapidapi or (PRIMARY_API == "api_football")

    return {
        "api_football":  has_api_football,
        "football_data": has_fd,
    }


def pct_bar(value: float, max_val: float = 100, color: str = "#2196F3") -> str:
    """Gera barra de progresso HTML simples."""
    pct = min(max(value / max_val * 100, 0), 100)
    return (
        f'<div style="background:#eee;border-radius:4px;height:12px;width:100%">'
        f'<div style="background:{color};width:{pct:.1f}%;height:100%;border-radius:4px"></div>'
        f'</div>'
    )
