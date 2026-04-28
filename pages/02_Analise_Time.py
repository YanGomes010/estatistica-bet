"""
Pagina: Analise de Time
Forma recente, desempenho casa/fora, stats avancadas, lesoes.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Analise de Time | Football Analytics",
    page_icon="magnifying_glass",
    layout="wide",
)

# CSS dark
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d0f1a; }
[data-testid="stSidebar"]          { background: #111320; }
.metric-card {
    background: #151728; border: 1px solid #252840;
    border-radius: 10px; padding: 14px 16px; margin: 4px 0;
}
</style>
""", unsafe_allow_html=True)

from config import COMPETITIONS, FORM_GAMES, get_current_season
from src.utils.helpers import check_api_configured, format_date_br
from src.fetchers.api_football import get_fetcher
from src.fetchers.football_data_org import FD_FREE_COMPETITIONS, FD_PAID_ONLY, get_fd_season
from src.analytics.form import compute_form, compute_home_away_split, form_string_html

# ── API check ──────────────────────────────────────────────────────
api_status = check_api_configured()
using_fd   = api_status.get("football_data") and not api_status.get("api_football")
using_api  = api_status.get("api_football")

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Configuracoes")

    # Filtra competicoes disponiveis para a API ativa
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
    # Default: Premier League ou primeiro disponivel
    default_idx = next((i for i, k in enumerate(keys) if k == "premier_league"), 0)

    sel_label = st.selectbox("Competicao", labels, index=default_idx)
    comp_key  = keys[labels.index(sel_label)]
    comp      = COMPETITIONS[comp_key]

    # Temporada
    if using_fd and not using_api:
        default_szn = get_fd_season(comp_key)
    else:
        default_szn = get_current_season(comp_key)

    seasons = sorted(comp.get("seasons_available", list(range(2020, 2028))), reverse=True)
    if default_szn not in seasons:
        seasons = [default_szn] + seasons
    season = st.selectbox("Temporada", seasons, index=seasons.index(default_szn))

    form_n       = st.slider("Jogos para forma recente", 3, 10, FORM_GAMES)
    force_refresh = st.button("Atualizar dados")

# ── Verificacoes ────────────────────────────────────────────────────
st.markdown("# Analise de Time")

if not any(api_status.values()):
    st.error("Configure suas chaves de API no `.env`.")
    st.stop()

if using_fd and not using_api and comp_key in FD_PAID_ONLY:
    st.error(f"**{comp['name']}** nao esta disponivel no plano gratuito do football-data.org.")
    st.info("Para acessar **Brasileirao** e **Libertadores**, configure `RAPIDAPI_KEY` no `.env` e `PRIMARY_API=api_football`.")
    st.stop()

fetcher = get_fetcher()

# ── Carrega times ───────────────────────────────────────────────────
with st.spinner("Carregando lista de times..."):
    try:
        teams_df = fetcher.get_teams(comp_key, season, force_refresh=force_refresh)
    except Exception as e:
        err_str = str(e)
        if "403" in err_str or "HTTPError" in err_str or "RetryError" in err_str:
            st.error("Acesso negado. Esta competicao nao esta disponivel no seu plano gratuito.")
            st.info("Configure `RAPIDAPI_KEY` no `.env` e `PRIMARY_API=api_football`.")
        else:
            st.error(f"Erro ao carregar times: {err_str}")
        st.stop()

if teams_df is None or teams_df.empty:
    st.warning("Nenhum time encontrado. Tente outra competicao ou clique em 'Atualizar dados'.")
    st.info("Dica: Competicoes gratuitas disponiveis: Premier League, La Liga, Bundesliga, Serie A Italiana, Ligue 1, Champions League, Europa League.")
    st.stop()

# ── Selecao de time ─────────────────────────────────────────────────
team_names = sorted(teams_df["team_name"].tolist())
team_map   = dict(zip(teams_df["team_name"], teams_df["team_id"]))

col_t, col_s = st.columns([3, 1])
with col_t:
    selected_team = st.selectbox(f"Time ({comp['flag']} {comp['name']} {season})", team_names)
team_id = team_map[selected_team]

st.divider()

# ── Carrega fixtures ────────────────────────────────────────────────
with st.spinner(f"Carregando dados de {selected_team}..."):
    try:
        fixtures_df = fetcher.get_fixtures(comp_key, season, force_refresh=force_refresh)
    except Exception as e:
        err_str = str(e)
        if "403" in err_str or "HTTPError" in err_str or "RetryError" in err_str:
            st.error("Acesso negado ao buscar jogos desta competicao.")
        else:
            st.error(f"Erro: {err_str}")
        st.stop()

    try:
        injuries_df = fetcher.get_injuries(team_id, season)
    except Exception:
        injuries_df = pd.DataFrame()

# ── Forma recente ────────────────────────────────────────────────────
st.subheader(f"Forma Recente - Ultimos {form_n} Jogos")

form = compute_form(fixtures_df, team_id, form_n)

if form["played"] == 0:
    st.info("Nenhum jogo encontrado para este time na temporada selecionada.")
else:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Vitorias",       form["wins"])
    c2.metric("Empates",        form["draws"])
    c3.metric("Derrotas",       form["losses"])
    c4.metric("Aproveitamento", f"{form['pct']}%")
    c5.metric("Saldo de Gols",  f"{form['goal_diff']:+d}")

    st.markdown(f"**Forma:** {form_string_html(form['form_string'])}", unsafe_allow_html=True)

    if not form["form_df"].empty:
        fd = form["form_df"].copy()
        fd["Data"]      = fd["date"].apply(format_date_br)
        fd["Local"]     = fd["is_home"].map({True: "Casa", False: "Fora"})
        fd["Resultado"] = fd["result"].map({"W": "Vitoria", "D": "Empate", "L": "Derrota"})
        fd["Placar"]    = fd.apply(
            lambda r: f"{r['home_team']}  {int(r['gf'] if r['is_home'] else r['ga'])} x "
                      f"{int(r['ga'] if r['is_home'] else r['gf'])}  {r['away_team']}", axis=1
        )
        st.dataframe(
            fd[["Data", "Local", "Placar", "Resultado"]],
            use_container_width=True, hide_index=True,
        )

st.divider()

# ── Mandante vs Visitante ────────────────────────────────────────────
st.subheader("Desempenho: Mandante vs. Visitante")
home_away = compute_home_away_split(fixtures_df, team_id)
h = home_away["home"]
a = home_away["away"]

col_h, col_a = st.columns(2)
with col_h:
    st.markdown("**Como Mandante**")
    st.metric("Jogos",          h["played"])
    st.metric("V / E / D",     f"{h['wins']} / {h['draws']} / {h['losses']}")
    st.metric("Aproveitamento", f"{h['pct']}%")
    st.metric("Gols: Pro/Contra", f"{h['gf']} / {h['ga']}  (SG {int(h['gd']):+d})")

with col_a:
    st.markdown("**Como Visitante**")
    st.metric("Jogos",          a["played"])
    st.metric("V / E / D",     f"{a['wins']} / {a['draws']} / {a['losses']}")
    st.metric("Aproveitamento", f"{a['pct']}%")
    st.metric("Gols: Pro/Contra", f"{a['gf']} / {a['ga']}  (SG {int(a['gd']):+d})")

if h["played"] > 0 or a["played"] > 0:
    fig = go.Figure(data=[
        go.Bar(name="Vitorias",  x=["Casa", "Fora"], y=[h["wins"],   a["wins"]],   marker_color="#4CAF50"),
        go.Bar(name="Empates",   x=["Casa", "Fora"], y=[h["draws"],  a["draws"]],  marker_color="#FFC107"),
        go.Bar(name="Derrotas",  x=["Casa", "Fora"], y=[h["losses"], a["losses"]], marker_color="#F44336"),
    ])
    fig.update_layout(
        barmode="group", template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=300, margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Lesoes ────────────────────────────────────────────────────────────
st.subheader("Desfalques")

if injuries_df is not None and not injuries_df.empty:
    st.warning(f"{len(injuries_df)} jogador(es) indisponivel(is)")
    st.dataframe(
        injuries_df[["player_name", "reason"]].rename(
            columns={"player_name": "Jogador", "reason": "Motivo"}
        ),
        use_container_width=True, hide_index=True,
    )
else:
    if using_fd and not using_api:
        st.info("Dados de lesoes disponiveis apenas com API-Football (RapidAPI).")
    else:
        st.success("Nenhum desfalque registrado no momento.")

st.caption("Fontes: football-data.org / API-Football")
