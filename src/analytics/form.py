"""
form.py - Análise de Forma Recente

Calcula:
  - Forma dos últimos N jogos (W/D/L) com decaimento temporal exponencial
  - Desempenho mandante vs. visitante
  - Médias de gols pró e contra (ponderadas por recência)
  - Pontuação e percentual de aproveitamento
"""
import pandas as pd
import numpy as np
from typing import Optional

from config import FORM_GAMES

# Decaimento padrão: ~0.02/dia → jogo de 30 dias atrás vale ~55% do atual
DEFAULT_DECAY = 0.02


def compute_form(
    fixtures_df: pd.DataFrame,
    team_id: int,
    last_n: int = FORM_GAMES,
    decay_per_day: float = DEFAULT_DECAY,
) -> dict:
    """
    Calcula a forma recente de um time com decaimento exponencial temporal.

    Args:
        fixtures_df:   DataFrame de jogos (home_team_id, away_team_id,
                       home_goals, away_goals, status, date)
        team_id:       ID do time
        last_n:        Número de jogos a considerar
        decay_per_day: Fator de decaimento por dia (0 = sem decaimento)
                       0.02 → jogo de 30 dias atrás vale 55% de um jogo de hoje

    Returns:
        dict com métricas de forma (avg_gf e avg_ga ponderados por recência)
    """
    df = fixtures_df.copy()

    # Normaliza IDs para comparação
    try:
        team_id = int(team_id)
        df["home_team_id"] = pd.to_numeric(df["home_team_id"], errors="coerce")
        df["away_team_id"] = pd.to_numeric(df["away_team_id"], errors="coerce")
    except Exception:
        pass

    # Filtra jogos finalizados deste time
    FINISHED = {"FT", "AET", "PEN", "AWD", "WO", "STATUS_FINAL", "Final", "Match Finished"}
    df = df[
        ((df["home_team_id"] == team_id) | (df["away_team_id"] == team_id)) &
        (df["status"].isin(FINISHED))
    ].copy()

    if df.empty:
        return _empty_form(team_id)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", ascending=False).head(last_n)

    # Referência temporal: jogo mais recente = dia 0
    max_date = df["date"].max()
    df["days_ago"] = (max_date - df["date"]).dt.days.clip(lower=0)
    df["weight"]   = np.exp(-decay_per_day * df["days_ago"])

    # ── Vectorized result computation (sem iterrows) ──────────────
    is_home_mask = df["home_team_id"] == team_id
    hg_arr = pd.to_numeric(df["home_goals"], errors="coerce").fillna(0).values.astype(float)
    ag_arr = pd.to_numeric(df["away_goals"], errors="coerce").fillna(0).values.astype(float)
    gf_arr = np.where(is_home_mask, hg_arr, ag_arr)
    ga_arr = np.where(is_home_mask, ag_arr, hg_arr)
    result_arr = np.where(gf_arr > ga_arr, "W", np.where(gf_arr < ga_arr, "L", "D"))

    form_df = pd.DataFrame({
        "date":        df["date"].values,
        "fixture_id":  df["fixture_id"].values if "fixture_id" in df.columns else None,
        "home_team":   df["home_team"].values  if "home_team"  in df.columns else None,
        "away_team":   df["away_team"].values  if "away_team"  in df.columns else None,
        "gf":          gf_arr,
        "ga":          ga_arr,
        "result":      result_arr,
        "is_home":     is_home_mask.values,
        "weight":      df["weight"].values,
        "competition": df["competition"].values if "competition" in df.columns else "",
    })

    # Contagens não ponderadas (para exibição)
    wins   = int((form_df["result"] == "W").sum())
    draws  = int((form_df["result"] == "D").sum())
    losses = int((form_df["result"] == "L").sum())
    played = len(form_df)

    gf_total = int(form_df["gf"].sum())
    ga_total = int(form_df["ga"].sum())
    points   = wins * 3 + draws
    max_pts  = played * 3
    pct      = round(points / max_pts * 100, 1) if max_pts > 0 else 0.0

    form_string = "".join(
        form_df.sort_values("date", ascending=False)["result"].tolist()
    )

    # Médias ponderadas por recência (usadas no modelo de probabilidades)
    total_w  = form_df["weight"].sum()
    if total_w > 0:
        avg_gf_w = float((form_df["gf"] * form_df["weight"]).sum() / total_w)
        avg_ga_w = float((form_df["ga"] * form_df["weight"]).sum() / total_w)
    else:
        avg_gf_w = float(gf_total / played) if played else 0.0
        avg_ga_w = float(ga_total / played) if played else 0.0

    return {
        "team_id":       team_id,
        "played":        played,
        "wins":          wins,
        "draws":         draws,
        "losses":        losses,
        "goals_for":     gf_total,
        "goals_against": ga_total,
        "goal_diff":     gf_total - ga_total,
        "points":        points,
        "pct":           pct,
        "form_string":   form_string,
        # Médias simples (exibição)
        "avg_gf":        round(gf_total / played, 2) if played else 0.0,
        "avg_ga":        round(ga_total / played, 2) if played else 0.0,
        # Médias ponderadas por recência (modelo)
        "avg_gf_w":      round(avg_gf_w, 3),
        "avg_ga_w":      round(avg_ga_w, 3),
        "form_df":       form_df,
    }


def compute_home_away_split(
    fixtures_df: pd.DataFrame,
    team_id: int,
) -> dict:
    """
    Analisa desempenho separado como mandante e visitante.

    Returns:
        dict com stats home e away separadas
    """
    df = fixtures_df.copy()

    try:
        team_id = int(team_id)
        df["home_team_id"] = pd.to_numeric(df["home_team_id"], errors="coerce")
        df["away_team_id"] = pd.to_numeric(df["away_team_id"], errors="coerce")
    except Exception:
        pass

    FINISHED = {"FT", "AET", "PEN", "AWD", "WO", "STATUS_FINAL", "Final", "Match Finished"}
    df = df[
        ((df["home_team_id"] == team_id) | (df["away_team_id"] == team_id)) &
        (df["status"].isin(FINISHED))
    ]

    def _split_stats(sub_df: pd.DataFrame, as_home: bool) -> dict:
        if sub_df.empty:
            return {
                "played": 0, "wins": 0, "draws": 0, "losses": 0,
                "gf": 0, "ga": 0, "gd": 0, "points": 0,
                "pct": 0.0, "avg_gf": 0.0, "avg_ga": 0.0,
            }
        # Vetorizado: sem iterrows
        gf_col = "home_goals" if as_home else "away_goals"
        ga_col = "away_goals" if as_home else "home_goals"
        gf_s = pd.to_numeric(sub_df[gf_col], errors="coerce").fillna(0)
        ga_s = pd.to_numeric(sub_df[ga_col], errors="coerce").fillna(0)
        wins   = int((gf_s > ga_s).sum())
        draws  = int((gf_s == ga_s).sum())
        losses = int((gf_s < ga_s).sum())
        gf     = float(gf_s.sum())
        ga     = float(ga_s.sum())
        played = len(sub_df)
        points = wins * 3 + draws
        return {
            "played":  played,
            "wins":    wins,
            "draws":   draws,
            "losses":  losses,
            "gf":      int(gf),
            "ga":      int(ga),
            "gd":      int(gf - ga),
            "points":  points,
            "pct":     round(points / (played * 3) * 100, 1) if played else 0.0,
            "avg_gf":  round(gf / played, 2) if played else 0.0,
            "avg_ga":  round(ga / played, 2) if played else 0.0,
        }

    home_df = df[df["home_team_id"] == team_id]
    away_df = df[df["away_team_id"] == team_id]

    return {
        "home": _split_stats(home_df, as_home=True),
        "away": _split_stats(away_df, as_home=False),
    }


def form_badge(result: str) -> str:
    """Retorna emoji para resultado."""
    return {"W": "🟢", "D": "🟡", "L": "🔴"}.get(result, "⚪")


def form_string_html(form_string: str) -> str:
    """Converte string de forma em badges HTML coloridos."""
    colors = {"W": "#4CAF50", "D": "#FFC107", "L": "#F44336"}
    badges = []
    for r in form_string:
        color = colors.get(r, "#9E9E9E")
        badges.append(
            f'<span style="background:{color};color:white;padding:2px 6px;'
            f'border-radius:4px;margin:1px;font-weight:bold;">{r}</span>'
        )
    return " ".join(badges)


def _empty_form(team_id: int) -> dict:
    return {
        "team_id":       team_id,
        "played":        0,
        "wins":          0,
        "draws":         0,
        "losses":        0,
        "goals_for":     0,
        "goals_against": 0,
        "goal_diff":     0,
        "points":        0,
        "pct":           0.0,
        "form_string":   "",
        "avg_gf":        0.0,
        "avg_ga":        0.0,
        "avg_gf_w":      0.0,
        "avg_ga_w":      0.0,
        "form_df":       pd.DataFrame(),
    }
