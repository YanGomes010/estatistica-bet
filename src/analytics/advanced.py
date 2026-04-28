"""
advanced.py - Métricas Avançadas

Calcula e cruza:
  - xG a favor e contra por jogo
  - xG acumulado na temporada
  - Eficiência (gols reais vs xG)
  - Posse de bola média
  - Finalizações no alvo (SoT)
  - Rating de performance (índice composto)
"""
import pandas as pd
import numpy as np
from typing import Optional


# ------------------------------------------------------------------ #
# xG - Expected Goals
# ------------------------------------------------------------------ #
def compute_xg_stats(
    xg_df: pd.DataFrame,
    team_name: str,
) -> dict:
    """
    Calcula estatísticas de xG para um time específico.

    Args:
        xg_df:     DataFrame com colunas home_team, away_team, home_xg, away_xg, etc.
        team_name: Nome do time

    Returns:
        dict com xG médio, acumulado, eficiência
    """
    if xg_df.empty or ("home_xg" not in xg_df.columns):
        return _empty_xg_stats(team_name)

    home_games = xg_df[xg_df["home_team"] == team_name].copy()
    away_games = xg_df[xg_df["away_team"] == team_name].copy()

    xg_for   = list(home_games["home_xg"].fillna(0)) + list(away_games["away_xg"].fillna(0))
    xg_ag    = list(home_games["away_xg"].fillna(0)) + list(away_games["home_xg"].fillna(0))
    gf       = list(home_games.get("home_goals", pd.Series(dtype=float)).fillna(0)) + \
               list(away_games.get("away_goals", pd.Series(dtype=float)).fillna(0))
    ga       = list(home_games.get("away_goals", pd.Series(dtype=float)).fillna(0)) + \
               list(away_games.get("home_goals", pd.Series(dtype=float)).fillna(0))

    played = len(xg_for)
    if played == 0:
        return _empty_xg_stats(team_name)

    total_xgf = sum(xg_for)
    total_xga = sum(xg_ag)
    total_gf  = sum(gf)
    total_ga  = sum(ga)

    return {
        "team_name":        team_name,
        "played":           played,
        "total_xgf":        round(total_xgf, 2),
        "total_xga":        round(total_xga, 2),
        "xgd":              round(total_xgf - total_xga, 2),
        "avg_xgf":          round(total_xgf / played, 2),
        "avg_xga":          round(total_xga / played, 2),
        "total_gf":         int(total_gf),
        "total_ga":         int(total_ga),
        "xg_efficiency":    round(total_gf / total_xgf, 2) if total_xgf > 0 else None,
        "xga_efficiency":   round(total_ga / total_xga, 2) if total_xga > 0 else None,
        "over_performing":  total_gf > total_xgf,
        "under_performing": total_gf < total_xgf,
    }


# ------------------------------------------------------------------ #
# PERFORMANCE RATING (índice composto)
# ------------------------------------------------------------------ #
def compute_performance_score(
    form: dict,
    xg_stats: Optional[dict] = None,
    home_away: Optional[dict] = None,
    context: str = "home",  # "home" ou "away"
) -> float:
    """
    Calcula score de performance composto (0-100) para um time.
    Útil para comparação rápida antes de um confronto.

    Componentes:
      - Aproveitamento recente (40%)
      - xG diferencial (30%) se disponível
      - Aproveitamento no contexto home/away (30%)
    """
    score = 0.0
    weights_used = 0.0

    # Componente 1: aproveitamento recente
    if form.get("played", 0) > 0:
        score += form["pct"] * 0.4
        weights_used += 0.4

    # Componente 2: xG
    if xg_stats and xg_stats.get("played", 0) > 0:
        xgd = xg_stats.get("xgd", 0)
        xg_score = min(max((xgd + 2) / 4 * 100, 0), 100)  # normaliza -2..+2 → 0..100
        score += xg_score * 0.3
        weights_used += 0.3

    # Componente 3: aproveitamento casa/fora
    if home_away and context in home_away:
        ctx_pct = home_away[context].get("pct", 0)
        score += ctx_pct * 0.3
        weights_used += 0.3

    if weights_used == 0:
        return 0.0

    # Normaliza para os pesos efetivamente usados
    return round(score / weights_used * (weights_used / 1.0), 1)


# ------------------------------------------------------------------ #
# ANÁLISE DE SHOOTING (FBref)
# ------------------------------------------------------------------ #
def extract_team_shooting(
    shooting_df: pd.DataFrame,
    team_name: str,
) -> dict:
    """Extrai métricas de finalização para um time do DataFrame FBref."""
    if shooting_df.empty:
        return {"team_name": team_name}

    # Tenta encontrar o time (pode ter variações de nome)
    mask = shooting_df["team"].str.lower().str.contains(team_name.lower(), na=False) \
        if "team" in shooting_df.columns else pd.Series([False]*len(shooting_df))

    row = shooting_df[mask]
    if row.empty:
        return {"team_name": team_name}

    row = row.iloc[0]
    result = {"team_name": team_name}

    field_map = {
        "shots_total":   ["sh", "shots", "shots_total"],
        "shots_on_target": ["sot", "shots_on_target"],
        "sot_pct":       ["sot_pct", "sot%"],
        "goals":         ["gls", "goals", "g"],
        "xg":            ["xg", "npxg", "xg_expected"],
        "npxg":          ["npxg"],
        "avg_shot_dist": ["dist", "avg_shot_dist"],
        "pens_made":     ["pk", "pens_made"],
    }

    for target, candidates in field_map.items():
        for c in candidates:
            cols_lower = {col.lower(): col for col in row.index}
            if c in cols_lower:
                result[target] = row[cols_lower[c]]
                break

    return result


# ------------------------------------------------------------------ #
# POSSE DE BOLA (FBref)
# ------------------------------------------------------------------ #
def extract_team_possession(
    possession_df: pd.DataFrame,
    team_name: str,
) -> dict:
    """Extrai métricas de posse para um time."""
    if possession_df.empty:
        return {"team_name": team_name}

    mask = possession_df["team"].str.lower().str.contains(team_name.lower(), na=False) \
        if "team" in possession_df.columns else pd.Series([False]*len(possession_df))

    row = possession_df[mask]
    if row.empty:
        return {"team_name": team_name}

    row = row.iloc[0]
    result = {"team_name": team_name}

    field_map = {
        "possession_pct": ["poss", "possession", "possession_pct"],
        "touches":        ["touches", "touch"],
        "progressive_carries": ["prgc", "progressive_carries"],
        "progressive_passes": ["prgp", "progressive_passes"],
        "dribbles":       ["succ", "dribbles_completed"],
    }

    for target, candidates in field_map.items():
        for c in candidates:
            cols_lower = {col.lower(): col for col in row.index}
            if c in cols_lower:
                result[target] = row[cols_lower[c]]
                break

    return result


# ------------------------------------------------------------------ #
# RESUMO COMPARATIVO PRÉ-JOGO
# ------------------------------------------------------------------ #
def build_match_preview(
    home_team_name: str,
    away_team_name: str,
    home_form: dict,
    away_form: dict,
    home_xg: Optional[dict] = None,
    away_xg: Optional[dict] = None,
    home_away_home: Optional[dict] = None,
    home_away_away: Optional[dict] = None,
    h2h: Optional[dict] = None,
    home_injuries: Optional[pd.DataFrame] = None,
    away_injuries: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Monta resumo completo pré-jogo com todos os dados cruzados.
    """
    home_score = compute_performance_score(
        home_form, home_xg,
        home_away_home, context="home"
    )
    away_score = compute_performance_score(
        away_form, away_xg,
        home_away_away, context="away"
    )

    diff = home_score - away_score
    if diff > 10:
        advantage = f"🏠 {home_team_name} favorito"
    elif diff < -10:
        advantage = f"✈️ {away_team_name} favorito"
    else:
        advantage = "⚖️ Jogo equilibrado"

    return {
        "home_team":      home_team_name,
        "away_team":      away_team_name,
        "home_score":     home_score,
        "away_score":     away_score,
        "advantage":      advantage,
        "home_form":      home_form,
        "away_form":      away_form,
        "home_xg":        home_xg or {},
        "away_xg":        away_xg or {},
        "h2h":            h2h or {},
        "home_injuries":  len(home_injuries) if home_injuries is not None else 0,
        "away_injuries":  len(away_injuries) if away_injuries is not None else 0,
    }


def _empty_xg_stats(team_name: str) -> dict:
    return {
        "team_name": team_name, "played": 0,
        "total_xgf": 0, "total_xga": 0, "xgd": 0,
        "avg_xgf": 0, "avg_xga": 0,
        "total_gf": 0, "total_ga": 0,
        "xg_efficiency": None, "xga_efficiency": None,
        "over_performing": False, "under_performing": False,
    }
