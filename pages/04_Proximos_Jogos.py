"""
Página: Próximos Jogos
Calendário com análise de confronto ao clicar em ⚡ Analisar.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time as _time

st.set_page_config(page_title="Próximos Jogos | Football Analytics", page_icon="📅", layout="wide")

from config import COMPETITIONS, DEFAULT_SEASON, COMPETITION_GROUPS, get_current_season
from src.utils.helpers import format_date_br, check_api_configured, format_score
from src.fetchers.api_football import get_fetcher
from src.fetchers.fbref import get_fbref
from src.analytics.form import compute_form, compute_home_away_split
from src.analytics.h2h import compute_h2h
from src.analytics.advanced import compute_xg_stats
from src.analytics.betting import generate_betting_report, fit_dixon_coles, build_score_matrix

# ── CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
.analysis-panel {
    background: #0d1117; border: 1px solid #21262d;
    border-radius: 14px; padding: 24px; margin: 16px 0;
}
.match-header {
    text-align: center; padding: 20px 0 10px 0;
    border-bottom: 1px solid #21262d; margin-bottom: 20px;
}
.prob-bar-wrap { margin: 14px 0; }
.market-card {
    background: #13152a; border: 1px solid #1e2240;
    border-radius: 10px; padding: 14px 16px; margin: 8px 0;
}
.market-title { font-size: 0.75rem; color: #888; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 10px; }
.pick-row { display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; border-bottom: 1px solid #1a1d2e; }
.pick-row:last-child { border-bottom: none; }
.pick-label { color: #ccc; font-size: 0.9rem; }
.pick-prob { font-weight: 800; color: #fff; font-size: 0.95rem; }
.pick-odd { color: #FFC107; font-size: 0.8rem; margin-left: 8px; }
.best-pick {
    background: linear-gradient(135deg, #0a1f0a, #122a12);
    border: 2px solid #43A047; border-radius: 12px; padding: 16px; margin: 8px 0;
}
.best-pick-market { font-size: 0.72rem; color: #81C784; text-transform: uppercase; letter-spacing: 1px; }
.best-pick-pick { font-size: 1.3rem; font-weight: 800; color: #fff; margin: 4px 0; }
.best-pick-meta { font-size: 0.8rem; color: #aaa; }
.form-badge-W { display:inline-block; background:#388E3C; color:white;
    padding:3px 8px; border-radius:5px; font-weight:800; font-size:0.82rem; margin:1px; }
.form-badge-D { display:inline-block; background:#F57F17; color:white;
    padding:3px 8px; border-radius:5px; font-weight:800; font-size:0.82rem; margin:1px; }
.form-badge-L { display:inline-block; background:#C62828; color:white;
    padding:3px 8px; border-radius:5px; font-weight:800; font-size:0.82rem; margin:1px; }
.est-badge { display:inline-block; background:#1565C0; color:#90CAF9;
    padding:2px 7px; border-radius:4px; font-size:0.68rem; margin-left:6px; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Filtros")
    days_ahead    = st.slider("Dias à frente", 3, 30, 7)
    _cur          = DEFAULT_SEASON
    season        = st.selectbox("Temporada", list(range(_cur + 2, _cur - 3, -1)), index=2)
    force_refresh = st.button("🔄 Atualizar dados")

    st.markdown("**Competições:**")
    selected_comps = []
    for group, keys in COMPETITION_GROUPS.items():
        st.markdown(f"*{group}*")
        for key in keys:
            comp = COMPETITIONS[key]
            default_on = group == "Brasil"
            if st.checkbox(f"{comp['flag']} {comp['name']}", value=default_on, key=f"chk_{key}"):
                selected_comps.append(key)

# ── Validações ───────────────────────────────────────────────────────
if not any(check_api_configured().values()):
    st.error("❌ Configure suas chaves de API no arquivo `.env`.")
    st.stop()

if not selected_comps:
    st.info("Selecione pelo menos uma competição no menu lateral.")
    st.stop()

fetcher = get_fetcher()
fbref   = get_fbref()

refresh_key = int(_time.time() / 3600) + (1 if force_refresh else 0)

# ── Cache ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_upcoming(comp_key, szn, days, _rk):
    try:
        return fetcher.get_upcoming_fixtures(comp_key, szn, days_ahead=days, force_refresh=(_rk > 0))
    except PermissionError as e:
        return None, str(e)
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["402", "403", "RetryError", "HTTPError"]):
            return None, "Acesso negado. Verifique sua assinatura na API."
        return None, err

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_results(comp_key, szn, _rk):
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        df = fetcher.get_fixtures(comp_key, szn, from_date=from_date, to_date=today_str, status="FT")
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_season_fixtures(comp_key, szn):
    try:
        return fetcher.get_fixtures(comp_key, szn)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=7200, show_spinner=False)   # MLE: cache 2h (cálculo pesado)
def _fit_dc_model(comp_key, szn):
    """Ajusta parâmetros Dixon-Coles via MLE para a competição/temporada."""
    try:
        fixtures = fetcher.get_fixtures(comp_key, szn)
        if fixtures is not None and not fixtures.empty:
            return fit_dixon_coles(fixtures)
    except Exception:
        pass
    return {}

# ── Helpers de exibição ───────────────────────────────────────────────
def _form_badges(fs):
    if not fs:
        return '<span style="color:#555">Sem dados</span>'
    html = ""
    for c in str(fs)[-5:]:
        css = {"W": "form-badge-W", "D": "form-badge-D", "L": "form-badge-L"}.get(c.upper(), "")
        if css:
            html += f'<span class="{css}">{c.upper()}</span>'
    return html

def _prob_bar(p_home, p_draw, p_away, h_name, a_name):
    ph = round(p_home * 100, 1)
    pd_ = round(p_draw * 100, 1)
    pa = round(p_away * 100, 1)
    return f"""
<div style="margin:16px 0">
  <div style="display:flex;height:32px;border-radius:8px;overflow:hidden;font-size:0.8rem;font-weight:700">
    <div style="width:{ph}%;background:#2E7D32;display:flex;align-items:center;justify-content:center;color:white">{ph}%</div>
    <div style="width:{pd_}%;background:#555;display:flex;align-items:center;justify-content:center;color:white">{pd_}%</div>
    <div style="width:{pa}%;background:#B71C1C;display:flex;align-items:center;justify-content:center;color:white">{pa}%</div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#888;margin-top:4px">
    <span>🏠 {h_name}</span><span>Empate</span><span>{a_name} ✈️</span>
  </div>
</div>"""

def _market_card(title, rows, badge=""):
    badge_html = f'<span class="est-badge">{badge}</span>' if badge else ""
    rows_html = ""
    for label, prob, odd in rows:
        pct = round(prob * 100, 1)
        rows_html += (
            f'<div class="pick-row">'
            f'<span class="pick-label">{label}</span>'
            f'<span><span class="pick-prob">{pct}%</span>'
            f'<span class="pick-odd">Odd justa: {odd:.2f}</span></span>'
            f'</div>'
        )
    return f'<div class="market-card"><div class="market-title">{title}{badge_html}</div>{rows_html}</div>'

def _stars(n):
    return "⭐" * n + "☆" * (5 - n)

# ── Análise de Confronto ──────────────────────────────────────────────
def _show_analysis(fixture, comp_key, szn):
    home_name = fixture.get("home_team", "Mandante")
    away_name = fixture.get("away_team", "Visitante")
    try:
        home_id = int(fixture.get("home_team_id", 0))
        away_id = int(fixture.get("away_team_id", 0))
    except (ValueError, TypeError):
        home_id = away_id = 0

    try:
        match_date = pd.to_datetime(fixture.get("date", "")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        match_date = "Data a confirmar"

    st.markdown("---")
    st.markdown(
        f'<div class="match-header">'
        f'<div style="font-size:0.8rem;color:#888;margin-bottom:6px">⚡ ANÁLISE DO CONFRONTO</div>'
        f'<div style="font-size:1.7rem;font-weight:800;color:#fff">{home_name} <span style="color:#FFC107">vs</span> {away_name}</div>'
        f'<div style="font-size:0.85rem;color:#888;margin-top:4px">📅 {match_date} &nbsp;|&nbsp; {COMPETITIONS.get(comp_key, {}).get("name", comp_key)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Fechar análise
    if st.button("✖ Fechar análise", key="close_analysis"):
        for k in ["analyze_fixture", "analyze_comp", "analyze_season"]:
            st.session_state.pop(k, None)
        st.rerun()

    # Carregamento de dados
    with st.spinner("🔬 Calibrando modelo e calculando probabilidades..."):
        fixtures_df = _fetch_season_fixtures(comp_key, szn)
        dc_params   = _fit_dc_model(comp_key, szn)

        if not fixtures_df.empty and home_id and away_id:
            home_form = compute_form(fixtures_df, home_id)
            away_form = compute_form(fixtures_df, away_id)
            home_ha   = compute_home_away_split(fixtures_df, home_id)
            away_ha   = compute_home_away_split(fixtures_df, away_id)
        else:
            from src.analytics.form import _empty_form
            home_form = _empty_form(home_id)
            away_form = _empty_form(away_id)
            home_ha   = {"home": {}, "away": {}}
            away_ha   = {"home": {}, "away": {}}

        try:
            h2h_raw = fetcher.get_h2h(home_id, away_id, last=10)
            h2h     = compute_h2h(h2h_raw, home_id, away_id)
        except Exception:
            h2h = None

        report = generate_betting_report(
            home_name, away_name,
            home_form, away_form,
            home_ha, away_ha,
            h2h=h2h,
            dc_params=dc_params,
            home_id=home_id,
            away_id=away_id,
        )

    # Barra de probabilidades
    st.markdown(
        _prob_bar(report.prob_home_win, report.prob_draw, report.prob_away_win, home_name, away_name),
        unsafe_allow_html=True,
    )

    # Lambdas esperados
    lh = round(report.home_lambda, 2)
    la = round(report.away_lambda, 2)
    col1, col2, col3 = st.columns(3)
    col1.metric("⚽ Gols esperados " + home_name, lh)
    col2.metric("📊 Total esperado", round(lh + la, 2))
    col3.metric("⚽ Gols esperados " + away_name, la)

    # Tag de fonte do modelo
    if report.model_source == "mle":
        n_m   = dc_params.get("n_matches", "?")
        rho_v = dc_params.get("rho", -0.13)
        st.caption(f"🔬 Modelo MLE Dixon-Coles · {n_m} jogos da temporada · ρ={rho_v:.3f}")
    else:
        st.caption("📊 Modelo de médias ponderadas (temporada com poucos jogos disponíveis)")

    st.markdown("")

    # ── Tabs ─────────────────────────────────────────────────────────
    tab_form, tab_markets, tab_h2h, tab_scores = st.tabs(
        ["📋 Forma", "💰 Mercados de Aposta", "⚔️ H2H", "🎯 Placares"]
    )

    # ─── TAB FORMA ───────────────────────────────────────────────────
    with tab_form:
        cL, cR = st.columns(2)
        with cL:
            hf  = home_form
            hha = home_ha.get("home", {})
            st.markdown(f"**🏠 {home_name}**")
            st.markdown(_form_badges(hf.get("form_string", "")), unsafe_allow_html=True)
            st.markdown("")
            st.metric("Aproveitamento", f"{hf.get('pct', 0):.1f}%")
            st.metric("V / E / D", f"{hf.get('wins',0)} / {hf.get('draws',0)} / {hf.get('losses',0)}")
            st.metric("Gols Pró / Contra", f"{hf.get('avg_gf',0):.2f} / {hf.get('avg_ga',0):.2f}")
            st.caption("Como mandante")
            st.metric("Aproveit. em casa", f"{hha.get('pct',0):.1f}%")
            st.metric("V/E/D em casa", f"{hha.get('wins',0)}/{hha.get('draws',0)}/{hha.get('losses',0)}")
        with cR:
            af  = away_form
            aha = away_ha.get("away", {})
            st.markdown(f"**✈️ {away_name}**")
            st.markdown(_form_badges(af.get("form_string", "")), unsafe_allow_html=True)
            st.markdown("")
            st.metric("Aproveitamento", f"{af.get('pct', 0):.1f}%")
            st.metric("V / E / D", f"{af.get('wins',0)} / {af.get('draws',0)} / {af.get('losses',0)}")
            st.metric("Gols Pró / Contra", f"{af.get('avg_gf',0):.2f} / {af.get('avg_ga',0):.2f}")
            st.caption("Como visitante")
            st.metric("Aproveit. fora", f"{aha.get('pct',0):.1f}%")
            st.metric("V/E/D fora", f"{aha.get('wins',0)}/{aha.get('draws',0)}/{aha.get('losses',0)}")

    # ─── TAB MERCADOS ────────────────────────────────────────────────
    with tab_markets:
        from src.analytics.betting import (
            calc_over_under, calc_btts, calc_double_chance,
            calc_asian_handicap, calc_team_over_under,
        )

        matrix  = report.score_matrix
        ph      = report.prob_home_win
        pd_val  = report.prob_draw
        pa      = report.prob_away_win

        def fmt(p):
            return f"{p * 100:.1f}%"

        def odd_str(p):
            return f"{1/p:.2f}" if p > 0.01 else "—"

        col_a, col_b = st.columns(2)

        with col_a:
            # 1X2
            st.markdown("**🏆 Resultado Final (1X2)**")
            st.dataframe(pd.DataFrame({
                "Opção":         [f"🏠 {home_name}", "🤝 Empate", f"✈️ {away_name}"],
                "Probabilidade": [fmt(ph), fmt(pd_val), fmt(pa)],
                "Odd Justa":     [odd_str(ph), odd_str(pd_val), odd_str(pa)],
            }), use_container_width=True, hide_index=True)

            # Ambas Marcam
            p_yes, p_no = calc_btts(matrix)
            st.markdown("**⚽ Ambas Marcam (BTTS)**")
            st.dataframe(pd.DataFrame({
                "Opção":         ["Sim", "Não"],
                "Probabilidade": [fmt(p_yes), fmt(p_no)],
                "Odd Justa":     [odd_str(p_yes), odd_str(p_no)],
            }), use_container_width=True, hide_index=True)

            # Over/Under gols
            st.markdown("**📈 Total de Gols**")
            ou_data = []
            for line in [0.5, 1.5, 2.5, 3.5]:
                ov, un = calc_over_under(matrix, line)
                ou_data.append({"Mercado": f"Over {line}", "Prob.": fmt(ov), "Odd": odd_str(ov)})
                ou_data.append({"Mercado": f"Under {line}", "Prob.": fmt(un), "Odd": odd_str(un)})
            st.dataframe(pd.DataFrame(ou_data), use_container_width=True, hide_index=True)

            # Escanteios estimativa
            avg_att_h   = home_form.get("avg_gf") or 1.2
            avg_att_a   = away_form.get("avg_gf") or 1.0
            c_est       = round(5.0 + avg_att_h * 1.8 + 4.8 + avg_att_a * 1.6, 1)
            p_oc        = min(0.75, max(0.25, (c_est - 9.5) / 6.0 + 0.5))
            st.markdown(f"**🚩 Escanteios** *(est. ~{c_est:.1f}/jogo)*")
            st.dataframe(pd.DataFrame({
                "Mercado":  ["Over 9.5", "Under 9.5", "Over 11.5", "Under 11.5"],
                "Prob. Est": [fmt(p_oc), fmt(1-p_oc),
                              fmt(max(0.1, p_oc-0.25)),
                              fmt(min(0.9, 1-max(0.1, p_oc-0.25)))],
            }), use_container_width=True, hide_index=True)

        with col_b:
            # Dupla Chance
            dc = calc_double_chance(ph, pd_val, pa)
            st.markdown("**🔀 Dupla Chance**")
            st.dataframe(pd.DataFrame({
                "Opção":         ["1X (Casa/Emp)", "12 (Casa/Fora)", "X2 (Emp/Fora)"],
                "Probabilidade": [fmt(dc["1X"]), fmt(dc["12"]), fmt(dc["X2"])],
                "Odd Justa":     [odd_str(dc["1X"]), odd_str(dc["12"]), odd_str(dc["X2"])],
            }), use_container_width=True, hide_index=True)

            # Gols Mandante
            oh05, uh05 = calc_team_over_under(matrix, "home", 0.5)
            oh15, uh15 = calc_team_over_under(matrix, "home", 1.5)
            st.markdown(f"**🏠 Gols {home_name}**")
            st.dataframe(pd.DataFrame({
                "Mercado":       ["Over 0.5", "Under 0.5", "Over 1.5", "Under 1.5"],
                "Probabilidade": [fmt(oh05), fmt(uh05), fmt(oh15), fmt(uh15)],
                "Odd Justa":     [odd_str(oh05), odd_str(uh05), odd_str(oh15), odd_str(uh15)],
            }), use_container_width=True, hide_index=True)

            # Gols Visitante
            oa05, ua05 = calc_team_over_under(matrix, "away", 0.5)
            oa15, ua15 = calc_team_over_under(matrix, "away", 1.5)
            st.markdown(f"**✈️ Gols {away_name}**")
            st.dataframe(pd.DataFrame({
                "Mercado":       ["Over 0.5", "Under 0.5", "Over 1.5", "Under 1.5"],
                "Probabilidade": [fmt(oa05), fmt(ua05), fmt(oa15), fmt(ua15)],
                "Odd Justa":     [odd_str(oa05), odd_str(ua05), odd_str(oa15), odd_str(ua15)],
            }), use_container_width=True, hide_index=True)

            # Handicap Asiático
            st.markdown(f"**⚖️ Handicap Asiático**")
            hc_data = []
            for hc in [-1.0, -0.5, 0.0, 0.5, 1.0]:
                pc_h, pc_a = calc_asian_handicap(matrix, hc)
                sign = "+" if hc >= 0 else ""
                hc_data.append({
                    "Handicap": f"{home_name} {sign}{hc}",
                    "Prob. Casa": fmt(pc_h),
                    "Prob. Fora": fmt(pc_a),
                })
            st.dataframe(pd.DataFrame(hc_data), use_container_width=True, hide_index=True)

            # Cartões estimativa
            h2h_games   = h2h.get("total_games", 0) if h2h else 0
            cards_est   = round(3.2 + (0.5 if h2h_games >= 3 else 0.0), 1)
            p_oc2       = min(0.72, max(0.28, (cards_est - 2.5) / 3.0 + 0.3))
            st.markdown(f"**🟨 Cartões** *(est. ~{cards_est:.1f}/jogo)*")
            st.dataframe(pd.DataFrame({
                "Mercado":  ["Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"],
                "Prob. Est": [fmt(p_oc2), fmt(1-p_oc2),
                              fmt(max(0.15, p_oc2-0.22)),
                              fmt(min(0.85, 1-max(0.15, p_oc2-0.22)))],
            }), use_container_width=True, hide_index=True)

        # ── Picks por nível de risco ──────────────────────────────────
        st.markdown("---")
        st.markdown("### 🎯 Recomendações de Aposta")
        st.caption("Picks gerados pelo modelo Poisson + Dixon-Coles. Escanteios e cartões são estimativas.")

        risk_tiers = [
            ("baixo", "🟢 Baixo Risco",  "prob ≥ 65%  —  apostas mais seguras"),
            ("medio", "🟡 Risco Médio",  "prob 50–65%  —  bom equilíbrio odds/probabilidade"),
            ("alto",  "🔴 Risco Alto",   "prob 40–50%  —  odds atrativas, maior incerteza"),
        ]
        any_picks = False
        for risk_key, risk_label, risk_desc in risk_tiers:
            picks = report.picks_by_risk.get(risk_key, [])
            if not picks:
                continue
            any_picks = True
            st.markdown(f"**{risk_label}** — *{risk_desc}*")
            cols = st.columns(min(3, len(picks)))
            for i, pk in enumerate(picks):
                with cols[i]:
                    st.metric(
                        label=f"{_stars(pk.star_rating)} {pk.market}",
                        value=pk.pick,
                        delta=f"{pk.probability*100:.1f}%  |  Odd: {pk.odds_fair:.2f}  |  Conf: {pk.confidence}/100",
                    )
        if not any_picks:
            st.info("Dados insuficientes para gerar recomendações neste confronto.")

    # ─── TAB H2H ──────────────────────────────────────────────────────
    with tab_h2h:
        if h2h and h2h.get("total_games", 0) > 0:
            tg = h2h["total_games"]
            t1w = h2h.get("team1_wins", 0)
            dw  = h2h.get("draws", 0)
            t2w = h2h.get("team2_wins", 0)
            avg_g = h2h.get("avg_goals_per_game", 0)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Jogos H2H", tg)
            c2.metric(f"Vitórias {home_name}", t1w)
            c3.metric("Empates", dw)
            c4.metric(f"Vitórias {away_name}", t2w)

            ph2h = t1w / tg if tg > 0 else 0
            pd2h = dw  / tg if tg > 0 else 0
            pa2h = t2w / tg if tg > 0 else 0
            st.markdown(
                _prob_bar(ph2h, pd2h, pa2h, home_name, away_name),
                unsafe_allow_html=True,
            )
            st.metric("Média de Gols nos H2H", f"{avg_g:.2f}")

            h2h_history = h2h.get("summary_df", pd.DataFrame())
            if isinstance(h2h_history, pd.DataFrame) and not h2h_history.empty:
                st.markdown("**Últimos confrontos:**")
                display = h2h_history.copy()
                if "home_goals" in display.columns and "away_goals" in display.columns:
                    display["Placar"] = display.apply(
                        lambda r: f"{r.get('home_team','')}  {int(r.get('home_goals',0))}-{int(r.get('away_goals',0))}  {r.get('away_team','')}",
                        axis=1,
                    )
                    cols_show = [c for c in ["date", "Placar"] if c in display.columns]
                    st.dataframe(display[cols_show], use_container_width=True, hide_index=True)
        else:
            st.info("Sem histórico de confrontos diretos disponível para esta competição/temporada.")

    # ─── TAB PLACARES ─────────────────────────────────────────────────
    with tab_scores:
        top = report.top_scores
        if top:
            st.markdown("#### Placares mais prováveis pelo modelo Poisson")
            max_p = top[0][1] if top else 1
            for score_str, pct in top:
                bar_w = int(pct / max_p * 100)
                st.markdown(
                    f'<div style="margin:6px 0;display:flex;align-items:center;gap:12px">'
                    f'<span style="font-weight:800;font-size:1.1rem;min-width:40px;color:#fff">{score_str}</span>'
                    f'<div style="flex:1;background:#1a1d2e;border-radius:4px;height:20px">'
                    f'<div style="width:{bar_w}%;background:#1565C0;height:100%;border-radius:4px"></div></div>'
                    f'<span style="color:#90CAF9;font-weight:700;min-width:42px">{pct:.1f}%</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Sem dados suficientes para calcular placares prováveis.")

    st.caption("⚠️ Análise informativa. Escanteios e cartões são estimativas sem dados diretos. Aposte com responsabilidade.")


# ── Título ────────────────────────────────────────────────────────────
st.title("📅 Próximos Jogos & Calendário")

today = datetime.now().date()

STATUS_SCHEDULED = {
    "Not Started", "NS", "TBD", "STATUS_SCHEDULED",
    "Scheduled", "scheduled", "STATUS_POSTPONED", "Postponed",
}
STATUS_FINISHED = {"Match Finished", "FT", "AET", "PEN", "STATUS_FINAL", "Final"}

TRANS = {
    "Monday": "Segunda-feira", "Tuesday": "Terça-feira",
    "Wednesday": "Quarta-feira", "Thursday": "Quinta-feira",
    "Friday": "Sexta-feira", "Saturday": "Sábado", "Sunday": "Domingo",
}

# ── Carrega todos os jogos de todas as competições ────────────────────
all_frames  = []
load_errors = []

with st.spinner("Carregando jogos..."):
    for comp_key in selected_comps:
        comp   = COMPETITIONS[comp_key]
        result = _fetch_upcoming(comp_key, season, days_ahead, refresh_key)
        if isinstance(result, tuple):
            df_c, err = result
            if df_c is None:
                load_errors.append(f"**{comp['name']}**: {err}")
                continue
        else:
            df_c = result
        if df_c is not None and not df_c.empty:
            df_c = df_c.copy()
            df_c["comp_key"]  = comp_key
            df_c["comp_name"] = comp["name"]
            df_c["comp_flag"] = comp.get("flag", "🏆")
            all_frames.append(df_c)

for err_msg in load_errors:
    st.warning(f"⚠️ {err_msg}")

if not all_frames:
    st.info(f"Nenhum jogo encontrado nos próximos {days_ahead} dias nas competições selecionadas.")
    st.stop()

df_all = pd.concat(all_frames, ignore_index=True)
df_all["date"] = pd.to_datetime(df_all["date"])
df_all["day"]  = df_all["date"].dt.date
df_all = df_all.sort_values(["date", "comp_key"])

days_list = sorted(df_all["day"].unique())

# ── Paginação ─────────────────────────────────────────────────────────
PAGE_SIZE = 5
page_key  = "page_unified"
if page_key not in st.session_state:
    st.session_state[page_key] = 0

total_pages = max(1, (len(days_list) + PAGE_SIZE - 1) // PAGE_SIZE)
page        = min(st.session_state[page_key], total_pages - 1)
days_page   = days_list[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

col_prev, col_info, col_next = st.columns([1, 3, 1])
with col_prev:
    if st.button("◀ Anterior", key="prev_unified", disabled=(page == 0)):
        st.session_state[page_key] = page - 1
        st.rerun()
with col_info:
    total_games = len(df_all)
    st.markdown(
        f"<div style='text-align:center;padding-top:6px;color:#888;font-size:0.85rem'>"
        f"Semana {page+1} de {total_pages} &nbsp;•&nbsp; {total_games} jogos no período</div>",
        unsafe_allow_html=True,
    )
with col_next:
    if st.button("Próximo ▶", key="next_unified", disabled=(page >= total_pages - 1)):
        st.session_state[page_key] = page + 1
        st.rerun()

# ── Lista de jogos ────────────────────────────────────────────────────
for day in days_page:
    day_games = df_all[df_all["day"] == day]
    day_label = day.strftime("%A, %d/%m/%Y")
    for en, pt in TRANS.items():
        day_label = day_label.replace(en, pt)

    is_today    = day == today
    is_tomorrow = day == today + timedelta(days=1)

    if is_today:
        badge_html   = '<span style="background:#C62828;color:#fff;padding:2px 10px;border-radius:5px;font-size:0.7rem;margin-left:10px;font-weight:800;letter-spacing:1px">HOJE</span>'
        border_color = "#C62828"
    elif is_tomorrow:
        badge_html   = '<span style="background:#E65100;color:#fff;padding:2px 10px;border-radius:5px;font-size:0.7rem;margin-left:10px;font-weight:800;letter-spacing:1px">AMANHÃ</span>'
        border_color = "#E65100"
    else:
        badge_html   = ""
        border_color = "#1565C0"

    # Cabeçalho do dia
    st.markdown(
        f'<div style="margin:26px 0 4px 0;padding:9px 16px;'
        f'background:#0d1117;border-left:3px solid {border_color};'
        f'border-radius:0 8px 8px 0;display:flex;align-items:center">'
        f'<span style="font-weight:700;font-size:1rem;color:#e8e8e8">{day_label}</span>'
        f'{badge_html}'
        f'<span style="color:#3a3a4a;font-size:0.78rem;margin-left:auto">{len(day_games)} jogo(s)</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    for idx, row in day_games.iterrows():
        comp_key_r  = row.get("comp_key", "")
        comp_flag_r = row.get("comp_flag", "🏆")
        comp_name_r = row.get("comp_name", "")

        with st.container(border=True):
            c_time, c_home, c_score, c_away, c_comp, c_status, c_btn = st.columns(
                [1, 3.5, 1.5, 3.5, 2.5, 1.8, 1.5]
            )

            # Hora
            with c_time:
                try:
                    t = pd.to_datetime(row["date"]).strftime("%H:%M")
                except Exception:
                    t = "--:--"
                st.markdown(
                    f'<span style="color:#90CAF9;font-weight:800;font-size:1rem">{t}</span>',
                    unsafe_allow_html=True,
                )

            # Mandante
            with c_home:
                st.markdown(f'<span style="font-weight:700;font-size:0.97rem">{row["home_team"]}</span>', unsafe_allow_html=True)

            # Placar / vs
            with c_score:
                raw_status = row.get("status", "")
                if raw_status in STATUS_SCHEDULED or raw_status == "":
                    st.markdown(
                        '<div style="text-align:center;color:#3a3a5a;font-weight:700;font-size:0.95rem">vs</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    hg = row.get("home_goals") or row.get("ft_home")
                    ag = row.get("away_goals") or row.get("ft_away")
                    st.markdown(
                        f'<div style="text-align:center;font-weight:900;color:#FFC107;font-size:1rem">{format_score(hg, ag)}</div>',
                        unsafe_allow_html=True,
                    )

            # Visitante
            with c_away:
                st.markdown(f'<span style="font-weight:700;font-size:0.97rem">{row["away_team"]}</span>', unsafe_allow_html=True)

            # Competição
            with c_comp:
                st.markdown(
                    f'<span style="background:#111827;border:1px solid #1e2240;color:#9E9EC0;'
                    f'padding:3px 8px;border-radius:5px;font-size:0.72rem;white-space:nowrap">'
                    f'{comp_flag_r} {comp_name_r}</span>',
                    unsafe_allow_html=True,
                )

            # Status
            with c_status:
                raw_s = row.get("status_long") or row.get("status", "")
                if raw_s in STATUS_SCHEDULED or raw_s == "":
                    st.markdown('<span style="color:#546E7A;font-size:0.8rem">🕐 Em breve</span>', unsafe_allow_html=True)
                elif raw_s in STATUS_FINISHED:
                    st.markdown('<span style="color:#66BB6A;font-size:0.8rem">✅ Encerrado</span>', unsafe_allow_html=True)
                else:
                    clean = raw_s.replace("STATUS_", "").replace("_", " ").title()
                    st.markdown(f'<span style="color:#EF5350;font-size:0.8rem">🔴 {clean}</span>', unsafe_allow_html=True)

            # Botão
            with c_btn:
                fixture_id = row.get("fixture_id", f"{comp_key_r}_{idx}")
                if st.button("⚡ Analisar", key=f"analyze_{comp_key_r}_{fixture_id}", use_container_width=True):
                    st.session_state["analyze_fixture"] = row.to_dict()
                    st.session_state["analyze_comp"]    = comp_key_r
                    st.session_state["analyze_season"]  = season
                    st.rerun()

# ── Painel de análise ─────────────────────────────────────────────────
if "analyze_fixture" in st.session_state and st.session_state.get("analyze_comp"):
    _show_analysis(
        st.session_state["analyze_fixture"],
        st.session_state["analyze_comp"],
        st.session_state.get("analyze_season", season),
    )

# ── Resultados Recentes ───────────────────────────────────────────────
st.markdown("")
with st.expander("📋 Resultados Recentes (últimos 7 dias)", expanded=False):
    all_results = []
    for comp_key in selected_comps:
        comp   = COMPETITIONS[comp_key]
        res_df = _fetch_results(comp_key, season, refresh_key)
        if res_df is not None and not res_df.empty:
            res_df = res_df.copy()
            res_df["comp_flag"] = comp.get("flag", "🏆")
            res_df["comp_name"] = comp["name"]
            all_results.append(res_df)
    if all_results:
        res_all = pd.concat(all_results, ignore_index=True)
        res_all = res_all[res_all["status"].isin(["FT", "AET", "PEN", "STATUS_FINAL", "Final"])].copy()
        res_all = res_all.sort_values("date", ascending=False).head(20)
        if not res_all.empty:
            res_all["Data"]        = res_all["date"].apply(format_date_br)
            res_all["Competição"]  = res_all.apply(lambda r: f"{r['comp_flag']} {r['comp_name']}", axis=1)
            res_all["Placar"]      = res_all.apply(
                lambda r: (
                    f"{r['home_team']}  "
                    f"{format_score(r.get('ft_home', r.get('home_goals')), r.get('ft_away', r.get('away_goals')))}  "
                    f"{r['away_team']}"
                ),
                axis=1,
            )
            st.dataframe(
                res_all[["Data", "Competição", "Placar"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Nenhum resultado recente.")
    else:
        st.info("Nenhum resultado recente.")

st.divider()
st.caption("Fonte: ESPN / API-Football • Cache: 1h próximos jogos • 30min resultados | ⚡ = análise Poisson + Dixon-Coles")
