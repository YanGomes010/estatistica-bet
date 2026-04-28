"""
h2h.py - Análise de Confrontos Diretos (Head to Head)

Calcula:
  - Histórico de resultados H2H
  - Vantagem de cada time nos últimos encontros
  - Médias de gols nos confrontos
  - Tendências (mais gols em casa, etc.)
"""
import pandas as pd
import numpy as np
from typing import Tuple


def compute_h2h(
    h2h_df: pd.DataFrame,
    team1_id: int,
    team2_id: int,
) -> dict:
    """
    Analisa histórico de confrontos entre dois times.

    Args:
        h2h_df:   DataFrame de confrontos (get_h2h())
        team1_id: ID do time 1 (perspectiva principal)
        team2_id: ID do time 2

    Returns:
        dict com análise completa do H2H
    """
    if h2h_df.empty:
        return _empty_h2h(team1_id, team2_id)

    # Garante que as colunas de ID existem
    if "home_team_id" not in h2h_df.columns or "away_team_id" not in h2h_df.columns:
        return _empty_h2h(team1_id, team2_id)

    df = h2h_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date", ascending=False)

    # Normaliza IDs para o mesmo tipo (int quando possível)
    def _norm_id(v):
        try: return int(v)
        except (ValueError, TypeError): return v

    try:
        team1_id = _norm_id(team1_id)
        team2_id = _norm_id(team2_id)
        df["home_team_id"] = df["home_team_id"].apply(_norm_id)
        df["away_team_id"] = df["away_team_id"].apply(_norm_id)
    except Exception:
        pass

    t1_wins = t2_wins = draws = 0
    t1_gf = t1_ga = 0
    rows = []

    for _, row in df.iterrows():
        h = row["home_team_id"]
        a = row["away_team_id"]
        hg = row["home_goals"] or 0
        ag = row["away_goals"] or 0

        if h == team1_id:
            g1, g2 = hg, ag
            t1_home = True
        else:
            g1, g2 = ag, hg
            t1_home = False

        t1_gf += g1
        t1_ga += g2

        if g1 > g2:
            result_t1 = "W"
            t1_wins += 1
        elif g1 < g2:
            result_t1 = "L"
            t2_wins += 1
        else:
            result_t1 = "D"
            draws += 1

        rows.append({
            "date":           row["date"],
            "home_team":      row["home_team"],
            "away_team":      row["away_team"],
            "home_goals":     hg,
            "away_goals":     ag,
            "score":          f"{hg} - {ag}",
            "result_team1":   result_t1,
            "t1_was_home":    t1_home,
            "competition":    row.get("competition", ""),
            "season":         row.get("season", ""),
        })

    total = len(df)
    summary_df = pd.DataFrame(rows)

    avg_goals_per_game = round((t1_gf + t1_ga) / total, 2) if total else 0
    btts = summary_df[
        (summary_df["home_goals"] > 0) & (summary_df["away_goals"] > 0)
    ].shape[0]

    return {
        "team1_id":          team1_id,
        "team2_id":          team2_id,
        "total_games":       total,
        "team1_wins":        t1_wins,
        "team2_wins":        t2_wins,
        "draws":             draws,
        "team1_gf":          t1_gf,
        "team1_ga":          t1_ga,
        "team1_gd":          t1_gf - t1_ga,
        "team1_win_pct":     round(t1_wins / total * 100, 1) if total else 0,
        "team2_win_pct":     round(t2_wins / total * 100, 1) if total else 0,
        "draw_pct":          round(draws / total * 100, 1) if total else 0,
        "avg_goals_per_game": avg_goals_per_game,
        "avg_t1_gf":         round(t1_gf / total, 2) if total else 0,
        "avg_t1_ga":         round(t1_ga / total, 2) if total else 0,
        "btts_count":        btts,
        "btts_pct":          round(btts / total * 100, 1) if total else 0,
        "over25_count":      int(summary_df[
            (summary_df["home_goals"] + summary_df["away_goals"]) > 2.5
        ].shape[0]),
        "over25_pct":        round(
            summary_df[
                (summary_df["home_goals"] + summary_df["away_goals"]) > 2.5
            ].shape[0] / total * 100, 1
        ) if total else 0,
        "summary_df":        summary_df,
        "last_meeting":      rows[0] if rows else None,
    }


def h2h_trend_message(h2h: dict, team1_name: str, team2_name: str) -> str:
    """Gera mensagem de tendência do H2H."""
    if not h2h["total_games"]:
        return "Sem histórico de confrontos disponível."

    lines = []
    t1w = h2h["team1_wins"]
    t2w = h2h["team2_wins"]
    d = h2h["draws"]
    total = h2h["total_games"]

    if t1w > t2w:
        lines.append(f"✅ **{team1_name}** tem vantagem histórica: {t1w}V {d}E {t2w}D em {total} jogos")
    elif t2w > t1w:
        lines.append(f"✅ **{team2_name}** tem vantagem histórica: {t2w}V {d}E {t1w}D em {total} jogos")
    else:
        lines.append(f"⚖️ Histórico equilibrado: {t1w}V {d}E {t2w}D em {total} jogos")

    lines.append(f"⚽ Média de {h2h['avg_goals_per_game']} gols por jogo nos confrontos")

    if h2h["btts_pct"] >= 60:
        lines.append(f"🎯 Ambas marcam em {h2h['btts_pct']}% dos confrontos")

    if h2h["over25_pct"] >= 60:
        lines.append(f"📈 Mais de 2.5 gols em {h2h['over25_pct']}% dos jogos")

    return "\n".join(lines)


def _empty_h2h(team1_id: int, team2_id: int) -> dict:
    return {
        "team1_id": team1_id, "team2_id": team2_id,
        "total_games": 0, "team1_wins": 0, "team2_wins": 0, "draws": 0,
        "team1_gf": 0, "team1_ga": 0, "team1_gd": 0,
        "team1_win_pct": 0, "team2_win_pct": 0, "draw_pct": 0,
        "avg_goals_per_game": 0, "avg_t1_gf": 0, "avg_t1_ga": 0,
        "btts_count": 0, "btts_pct": 0, "over25_count": 0, "over25_pct": 0,
        "summary_df": pd.DataFrame(),
        "last_meeting": None,
    }
