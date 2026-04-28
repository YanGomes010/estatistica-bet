"""
Pagina: Confronto Direto (H2H)
Compara dois times com forma recente, H2H e desempenho.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Confronto Direto | Football Analytics",
    page_icon="crossed_swords",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d0f1a; }
[data-testid="stSidebar"]          { background: #111320; }
</style>
""", unsafe_allow_html=True)

from config import COMPETITIONS, H2H_GAMES, FORM_GAMES, get_current_season
from src.utils.helpers import check_api_configured, format_date_br
from src.fetchers.api_football import get_fetcher
from src.fetchers.football_data_org import FD_FREE_COMPETITIONS, FD_PAID_ONLY, get_fd_season
from src.analytics.form import compute_form, compute_home_away_split, form_string_html
from src.analytics.h2h import compute_h2h, h2h_trend_message
from src.analytics.advanced import build_match_preview
from src.analytics.betting import (
    generate_betting_report, fit_dixon_coles,
    calc_over_under, calc_btts,
    calc_double_chance, calc_asian_handicap, calc_team_over_under,
)

# ── API check ──────────────────────────────────────────────────────
api_status = check_api_configured()
using_fd   = api_status.get("football_data") and not api_status.get("api_football")
using_api  = api_status.get("api_football")

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuracoes")

    available = []
    for key, comp in COMPETITIONS.items():
        if using_fd and not using_api:
            if key in FD_PAID_ONLY or key not in FD_FREE_COMPETITIONS:
                continue
        available.append((f"{comp['flag']} {comp['name']}", key))

    if not available:
        available = [(f"{c['flag']} {c['name']}", k) for k, c in COMPETITIONS.items()]

    labels = [x[0] for x in available]
    keys   = [x[1] for x in available]
    default_idx = next((i for i, k in enumerate(keys) if k == "premier_league"), 0)

    sel_label = st.selectbox("Competicao", labels, index=default_idx)
    comp_key  = keys[labels.index(sel_label)]
    comp      = COMPETITIONS[comp_key]

    if using_fd and not using_api:
        default_szn = get_fd_season(comp_key)
    else:
        default_szn = get_current_season(comp_key)

    seasons = sorted(comp.get("seasons_available", list(range(2020, 2028))), reverse=True)
    if default_szn not in seasons:
        seasons = [default_szn] + seasons
    season = st.selectbox("Temporada", seasons, index=seasons.index(default_szn))

    h2h_n        = st.slider("Jogos H2H historico", 5, 20, H2H_GAMES)
    force_refresh = st.button("Atualizar dados")

# ── Verificacoes ────────────────────────────────────────────────────
st.markdown("# Confronto Direto")
st.caption("Analise pre-jogo com forma recente, H2H e desempenho")

if not any(api_status.values()):
    st.error("Configure suas chaves de API no `.env`.")
    st.stop()

if using_fd and not using_api and comp_key in FD_PAID_ONLY:
    st.error(f"**{comp['name']}** nao esta disponivel no plano gratuito.")
    st.info("Configure `RAPIDAPI_KEY` e `PRIMARY_API=api_football` no `.env`.")
    st.stop()

fetcher = get_fetcher()

# ── Carrega times ───────────────────────────────────────────────────
with st.spinner("Carregando times..."):
    try:
        teams_df = fetcher.get_teams(comp_key, season, force_refresh=force_refresh)
    except Exception as e:
        err_str = str(e)
        if "403" in err_str or "HTTPError" in err_str or "RetryError" in err_str:
            st.error("Acesso negado. Esta competicao nao esta disponivel no plano gratuito.")
            st.info("Configure `RAPIDAPI_KEY` no `.env` e `PRIMARY_API=api_football`.")
        else:
            st.error(f"Erro: {err_str}")
        st.stop()

if teams_df is None or teams_df.empty:
    st.warning("Nenhum time encontrado. Selecione outra competicao ou clique em 'Atualizar dados'.")
    st.info("Competicoes gratuitas: Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, Europa League.")
    st.stop()

team_names = sorted(teams_df["team_name"].tolist())
team_map   = dict(zip(teams_df["team_name"], teams_df["team_id"]))

# ── Selecao dos dois times ──────────────────────────────────────────
col_h, col_vs, col_a = st.columns([5, 1, 5])
with col_h:
    st.markdown("**Mandante**")
    home_name = st.selectbox("Time da Casa", team_names, index=0, label_visibility="collapsed")
with col_vs:
    st.markdown(
        "<div style='text-align:center;margin-top:32px;font-size:1.8rem;font-weight:900'>VS</div>",
        unsafe_allow_html=True,
    )
with col_a:
    st.markdown("**Visitante**")
    away_opts = [t for t in team_names if t != home_name]
    away_name = st.selectbox("Time Visitante", away_opts,
                              index=min(1, len(away_opts) - 1), label_visibility="collapsed")

home_id = team_map[home_name]
away_id = team_map[away_name]

analyze_btn = st.button("Analisar Confronto", type="primary", use_container_width=True)

if not analyze_btn:
    st.info("Selecione os times acima e clique em **Analisar Confronto**.")
    st.stop()

st.divider()

# ── Carrega dados ───────────────────────────────────────────────────
with st.spinner("Carregando analise..."):
    try:
        fixtures_df   = fetcher.get_fixtures(comp_key, season, force_refresh=force_refresh)
        h2h_df        = fetcher.get_h2h(home_id, away_id, last=h2h_n)
        home_injuries = fetcher.get_injuries(home_id, season)
        away_injuries = fetcher.get_injuries(away_id, season)
    except Exception as e:
        err_str = str(e)
        if "403" in err_str or "RetryError" in err_str or "HTTPError" in err_str:
            st.error("Acesso negado ao buscar dados desta competicao.")
        else:
            st.error(f"Erro: {err_str}")
        st.stop()

# ── Analytics ───────────────────────────────────────────────────────
home_form = compute_form(fixtures_df, home_id, FORM_GAMES)
away_form = compute_form(fixtures_df, away_id, FORM_GAMES)
home_ha   = compute_home_away_split(fixtures_df, home_id)
away_ha   = compute_home_away_split(fixtures_df, away_id)
h2h       = compute_h2h(h2h_df, home_id, away_id)

# Ajusta parâmetros Dixon-Coles via MLE (usa toda a temporada disponível)
with st.spinner("🔬 Calibrando modelo (MLE Dixon-Coles)..."):
    dc_params = fit_dixon_coles(fixtures_df)

try:
    preview = build_match_preview(
        home_name, away_name,
        home_form, away_form,
        {}, {},
        home_ha, away_ha,
        h2h, home_injuries, away_injuries,
    )
    st.markdown(f"### {preview.get('advantage', '')}")
    col_hs, _, col_as = st.columns([3, 1, 3])
    with col_hs:
        st.metric(home_name, f"{preview.get('home_score', 0)}/100")
        st.progress(preview.get("home_score", 0) / 100)
    with col_as:
        st.metric(away_name, f"{preview.get('away_score', 0)}/100")
        st.progress(preview.get("away_score", 0) / 100)
    st.divider()
except Exception:
    pass

# ── Forma Recente ───────────────────────────────────────────────────
st.subheader(f"Forma Recente - Ultimos {FORM_GAMES} Jogos")

col_hf, col_af = st.columns(2)
with col_hf:
    st.markdown(f"**{home_name}**")
    st.markdown(form_string_html(home_form["form_string"]), unsafe_allow_html=True)
    st.metric("Aproveitamento",  f"{home_form['pct']}%")
    st.metric("V / E / D",       f"{home_form['wins']} / {home_form['draws']} / {home_form['losses']}")
    st.metric("Gols Pro / Contra", f"{home_form['goals_for']} / {home_form['goals_against']}")
with col_af:
    st.markdown(f"**{away_name}**")
    st.markdown(form_string_html(away_form["form_string"]), unsafe_allow_html=True)
    st.metric("Aproveitamento",  f"{away_form['pct']}%")
    st.metric("V / E / D",       f"{away_form['wins']} / {away_form['draws']} / {away_form['losses']}")
    st.metric("Gols Pro / Contra", f"{away_form['goals_for']} / {away_form['goals_against']}")

st.divider()

# ── Casa/Fora ────────────────────────────────────────────────────────
st.subheader("Contexto do Jogo: Mandante vs Visitante")
col_hh, col_aa = st.columns(2)
with col_hh:
    hh = home_ha["home"]
    st.markdown(f"**{home_name} em casa**")
    st.metric("Aproveitamento", f"{hh['pct']}%")
    st.metric("Jogos / V-E-D",  f"{hh['played']} / {hh['wins']}-{hh['draws']}-{hh['losses']}")
    st.metric("Gols (Pro/Contra)", f"{hh['gf']} / {hh['ga']}")
with col_aa:
    aa = away_ha["away"]
    st.markdown(f"**{away_name} fora de casa**")
    st.metric("Aproveitamento", f"{aa['pct']}%")
    st.metric("Jogos / V-E-D",  f"{aa['played']} / {aa['wins']}-{aa['draws']}-{aa['losses']}")
    st.metric("Gols (Pro/Contra)", f"{aa['gf']} / {aa['ga']}")

st.divider()

# ── H2H ─────────────────────────────────────────────────────────────
st.subheader("Historico de Confrontos Diretos (H2H)")
st.markdown(h2h_trend_message(h2h, home_name, away_name))

if h2h["total_games"] > 0:
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Vitorias {home_name}", h2h["team1_wins"])
    c2.metric("Empates",              h2h["draws"])
    c3.metric(f"Vitorias {away_name}", h2h["team2_wins"])

    fig_pie = go.Figure(go.Pie(
        labels=[home_name, "Empate", away_name],
        values=[h2h["team1_wins"], h2h["draws"], h2h["team2_wins"]],
        marker_colors=["#4CAF50", "#FFC107", "#F44336"],
        hole=0.4,
    ))
    fig_pie.update_layout(template="plotly_dark", height=260, margin=dict(t=10, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

    if not h2h["summary_df"].empty:
        sdf = h2h["summary_df"].copy()
        sdf["Data"]   = sdf["date"].apply(format_date_br)
        sdf["Placar"] = sdf.apply(
            lambda r: f"{r['home_team']}  {int(r['home_goals'])} x {int(r['away_goals'])}  {r['away_team']}",
            axis=1,
        )
        sdf["Resultado"] = sdf["result_team1"].map({
            "W": f"Vitoria {home_name}",
            "L": f"Vitoria {away_name}",
            "D": "Empate",
        })
        st.dataframe(
            sdf[["Data", "Placar", "Resultado"]],
            use_container_width=True, hide_index=True,
        )
else:
    st.info("Nenhum confronto direto encontrado nos registros disponíveis.")

st.divider()

# ── Desfalques ────────────────────────────────────────────────────────
st.subheader("Desfalques")
col_hi, col_ai = st.columns(2)
with col_hi:
    st.markdown(f"**{home_name}**")
    if home_injuries is not None and not home_injuries.empty:
        st.warning(f"{len(home_injuries)} desfalque(s)")
        st.dataframe(home_injuries[["player_name", "reason"]].rename(
            columns={"player_name": "Jogador", "reason": "Motivo"}),
            use_container_width=True, hide_index=True)
    else:
        if using_fd and not using_api:
            st.info("Lesoes disponiveis apenas com API-Football.")
        else:
            st.success("Sem desfalques registrados")
with col_ai:
    st.markdown(f"**{away_name}**")
    if away_injuries is not None and not away_injuries.empty:
        st.warning(f"{len(away_injuries)} desfalque(s)")
        st.dataframe(away_injuries[["player_name", "reason"]].rename(
            columns={"player_name": "Jogador", "reason": "Motivo"}),
            use_container_width=True, hide_index=True)
    else:
        if using_fd and not using_api:
            st.info("Lesoes disponiveis apenas com API-Football.")
        else:
            st.success("Sem desfalques registrados")

st.divider()

# ── Mercados de Aposta (Poisson + Dixon-Coles) ───────────────────────
st.subheader("💰 Mercados de Aposta")
if dc_params:
    n_m = dc_params.get("n_matches", 0)
    rho_v = dc_params.get("rho", -0.13)
    ha_v  = dc_params.get("home_adv", 1.25)
    st.caption(
        f"🔬 Modelo MLE Dixon-Coles calibrado com {n_m} jogos da temporada | "
        f"rho={rho_v:.3f} | home_adv={ha_v:.3f}"
    )
else:
    st.caption("📊 Modelo de médias ponderadas (dados insuficientes para MLE)")

try:
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
    ph  = report.prob_home_win
    pd_ = report.prob_draw
    pa  = report.prob_away_win
    lh  = round(report.home_lambda, 2)
    la  = round(report.away_lambda, 2)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Vitória {home_name}", f"{ph*100:.1f}%", f"Odd justa: {1/ph:.2f}" if ph > 0 else "")
    c2.metric("Empate",               f"{pd_*100:.1f}%", f"Odd justa: {1/pd_:.2f}" if pd_ > 0 else "")
    c3.metric(f"Vitória {away_name}", f"{pa*100:.1f}%", f"Odd justa: {1/pa:.2f}" if pa > 0 else "")

    st.markdown(f"**Gols esperados:** {home_name} **{lh}** × **{la}** {away_name}")

    matrix = report.score_matrix

    def fmt(p):
        return f"{p * 100:.1f}%"

    def odd_s(p):
        return f"{1/p:.2f}" if p > 0.01 else "—"

    col_a, col_b = st.columns(2)

    with col_a:
        # Ambas Marcam
        p_yes, p_no = calc_btts(matrix)
        st.markdown("**⚽ Ambas Marcam (BTTS)**")
        st.dataframe(pd.DataFrame({
            "Opção": ["Sim", "Não"],
            "Prob.": [fmt(p_yes), fmt(p_no)],
            "Odd Justa": [odd_s(p_yes), odd_s(p_no)],
        }), use_container_width=True, hide_index=True)

        # Over/Under
        st.markdown("**📈 Total de Gols**")
        ou_data = []
        for line in [0.5, 1.5, 2.5, 3.5]:
            ov, un = calc_over_under(matrix, line)
            ou_data.append({"Mercado": f"Over {line}", "Prob.": fmt(ov), "Odd": odd_s(ov)})
            ou_data.append({"Mercado": f"Under {line}", "Prob.": fmt(un), "Odd": odd_s(un)})
        st.dataframe(pd.DataFrame(ou_data), use_container_width=True, hide_index=True)

        # Escanteios estimativa
        avg_h = home_form.get("avg_gf") or 1.2
        avg_a = away_form.get("avg_gf") or 1.0
        c_est = round(5.0 + avg_h * 1.8 + 4.8 + avg_a * 1.6, 1)
        p_oc  = min(0.75, max(0.25, (c_est - 9.5) / 6.0 + 0.5))
        st.markdown(f"**🚩 Escanteios** *(est. ~{c_est:.1f}/jogo)*")
        st.dataframe(pd.DataFrame({
            "Mercado":   ["Over 9.5", "Under 9.5", "Over 11.5", "Under 11.5"],
            "Prob. Est": [fmt(p_oc), fmt(1-p_oc),
                          fmt(max(0.1, p_oc-0.25)),
                          fmt(min(0.9, 1-max(0.1, p_oc-0.25)))],
        }), use_container_width=True, hide_index=True)

    with col_b:
        # Dupla Chance
        dc = calc_double_chance(ph, pd_, pa)
        st.markdown("**🔀 Dupla Chance**")
        st.dataframe(pd.DataFrame({
            "Opção": ["1X (Casa/Emp)", "12 (Casa/Fora)", "X2 (Emp/Fora)"],
            "Prob.": [fmt(dc["1X"]), fmt(dc["12"]), fmt(dc["X2"])],
            "Odd Justa": [odd_s(dc["1X"]), odd_s(dc["12"]), odd_s(dc["X2"])],
        }), use_container_width=True, hide_index=True)

        # Gols por time
        oh05, uh05 = calc_team_over_under(matrix, "home", 0.5)
        oh15, uh15 = calc_team_over_under(matrix, "home", 1.5)
        oa05, ua05 = calc_team_over_under(matrix, "away", 0.5)
        oa15, ua15 = calc_team_over_under(matrix, "away", 1.5)
        st.markdown("**🎯 Gols por Time**")
        st.dataframe(pd.DataFrame({
            "Mercado": [f"{home_name} O0.5", f"{home_name} O1.5",
                        f"{away_name} O0.5", f"{away_name} O1.5"],
            "Prob.":   [fmt(oh05), fmt(oh15), fmt(oa05), fmt(oa15)],
            "Odd":     [odd_s(oh05), odd_s(oh15), odd_s(oa05), odd_s(oa15)],
        }), use_container_width=True, hide_index=True)

        # Cartões estimativa
        h2h_games = h2h.get("total_games", 0) if h2h else 0
        cards_est = round(3.2 + (0.5 if h2h_games >= 3 else 0.0), 1)
        p_oc2     = min(0.72, max(0.28, (cards_est - 2.5) / 3.0 + 0.3))
        st.markdown(f"**🟨 Cartões** *(est. ~{cards_est:.1f}/jogo)*")
        st.dataframe(pd.DataFrame({
            "Mercado":   ["Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"],
            "Prob. Est": [fmt(p_oc2), fmt(1-p_oc2),
                          fmt(max(0.15, p_oc2-0.22)),
                          fmt(min(0.85, 1-max(0.15, p_oc2-0.22)))],
        }), use_container_width=True, hide_index=True)

    # ── Picks por nível de risco ─────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Recomendações de Aposta")
    st.caption("Picks gerados pelo modelo Poisson + Dixon-Coles. Escanteios e cartões são estimativas.")

    _stars = lambda n: "⭐" * n + "☆" * (5 - n)
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

    # Placares mais prováveis
    if report.top_scores:
        st.markdown("---")
        st.markdown("**🎲 Placares Mais Prováveis**")
        sc_cols = st.columns(len(report.top_scores[:5]))
        for i, (score_str, pct) in enumerate(report.top_scores[:5]):
            sc_cols[i].metric(score_str, f"{pct:.1f}%")

except Exception as e:
    st.info(f"Análise de apostas indisponível: {e}")

st.caption("Fontes: ESPN / API-Football | Modelo: Poisson + Dixon-Coles | ⚠️ Uso informativo apenas")
