"""
Pagina: Classificacao
Tabela de classificacao com suporte a grupos (Libertadores, Champions, etc).
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(
    page_title="Classificacao | Football Analytics",
    page_icon="📊",
    layout="wide",
)

from config import COMPETITIONS, COMPETITION_GROUPS, get_current_season
from src.fetchers.api_football import get_fetcher
from src.fetchers.football_data_org import FD_FREE_COMPETITIONS, FD_PAID_ONLY, get_fd_season
from src.utils.helpers import check_api_configured

# CSS
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d0f1a; }
[data-testid="stSidebar"]          { background: #111320; }
.pos-badge {
    display: inline-block; width: 26px; height: 26px; border-radius: 6px;
    text-align: center; line-height: 26px; font-weight: 700; font-size: 0.85rem;
}
.pos-cl      { background: rgba(33,150,243,0.25); color: #64b5f6; }
.pos-qualif  { background: rgba(76,175,80,0.20);  color: #81c784; }
.pos-euro    { background: rgba(255,152,0,0.20);  color: #ffb74d; }
.pos-rel     { background: rgba(244,67,54,0.20);  color: #ef9a9a; }
.pos-normal  { background: rgba(255,255,255,0.05); color: #aaa;   }
.form-w { background:#4CAF50;color:white;padding:1px 6px;border-radius:4px;
          font-weight:700;font-size:0.75rem;margin:1px; }
.form-d { background:#FF9800;color:white;padding:1px 6px;border-radius:4px;
          font-weight:700;font-size:0.75rem;margin:1px; }
.form-l { background:#F44336;color:white;padding:1px 6px;border-radius:4px;
          font-weight:700;font-size:0.75rem;margin:1px; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### Filtros")
    api_status = check_api_configured()
    using_fd = not (api_status.get("api_football", False)) and api_status.get("football_data", False)

    available = []
    for key, comp in COMPETITIONS.items():
        if using_fd and key in FD_PAID_ONLY:
            continue
        if using_fd and key not in FD_FREE_COMPETITIONS:
            continue
        available.append((f"{comp['flag']} {comp['name']}", key))

    if not available:
        available = [(f"{c['flag']} {c['name']}", k) for k, c in COMPETITIONS.items()]

    labels = [x[0] for x in available]
    keys   = [x[1] for x in available]

    sel_label  = st.selectbox("Competicao", labels)
    comp_key   = keys[labels.index(sel_label)]
    comp       = COMPETITIONS[comp_key]

    default_szn = get_fd_season(comp_key) if using_fd else get_current_season(comp_key)
    seasons = sorted(comp.get("seasons_available", list(range(2020, 2029))), reverse=True)
    if default_szn not in seasons:
        seasons = [default_szn] + seasons
    season = st.selectbox("Temporada", seasons, index=seasons.index(default_szn))

    force = st.button("Atualizar")

    if using_fd and comp_key in FD_PAID_ONLY:
        st.error("Esta competicao requer API-Football.")

# API check
if not any(api_status.values()):
    st.error("Configure suas chaves de API no `.env`.")
    st.stop()

fetcher = get_fetcher()

st.markdown(f"# 📊 {comp['flag']} {comp['name']}")
st.caption(f"Temporada {season} · Cache: 12h")

with st.spinner("Carregando classificacao..."):
    try:
        df = fetcher.get_standings(comp_key, season, force_refresh=force)
    except PermissionError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        err_str = str(e)
        if "HTTPError" in err_str or "403" in err_str or "RetryError" in err_str or "404" in err_str:
            st.error("Esta competicao nao esta disponivel no plano gratuito.")
        else:
            st.error(f"Erro ao carregar classificacao: {err_str}")
        st.stop()

if df is None or df.empty:
    st.warning("Dados nao disponiveis para esta competicao/temporada.")
    st.stop()

# Detecta grupos (Libertadores tem 8, Champions tem 8, etc.)
has_groups = "group" in df.columns and df["group"].nunique() > 1

# KPIs
leader = df.sort_values("points", ascending=False).iloc[0]
bottom = df.sort_values("points", ascending=False).iloc[-1]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Lider",            leader["team_name"])
c2.metric("Pontos (1)",       int(leader["points"]))
c3.metric("Jogos disputados", int(leader["played"]))
c4.metric("Gols (1)",         int(leader["goals_for"]))
c5.metric("Ultimo",           bottom["team_name"])

st.markdown("---")

# Configuracoes de zona por competicao
zone_config = {
    "premier_league": {"cl":4, "euro":5, "rel":3},
    "la_liga":        {"cl":4, "euro":6, "rel":3},
    "bundesliga":     {"cl":4, "euro":6, "rel":3},
    "serie_a_it":     {"cl":4, "euro":7, "rel":3},
    "ligue_1":        {"cl":3, "euro":5, "rel":3},
    "brasileirao_a":  {"cl":0, "euro":6, "rel":4},
    "champions_league": {"cl":0, "euro":0, "rel":0},
    "libertadores":   {"cl":0, "euro":0, "rel":0},
}
zc_default = zone_config.get(comp_key, {"cl": 4, "euro": 6, "rel": 3})


def get_row_style(pos, n_rows, zc):
    if zc["cl"] > 0 and pos <= zc["cl"]:
        return "pos-cl", "rgba(33,150,243,0.06)"
    if zc["euro"] > 0 and pos <= zc["euro"]:
        return "pos-euro", "rgba(255,152,0,0.05)"
    if zc["rel"] > 0 and pos > n_rows - zc["rel"]:
        return "pos-rel", "rgba(244,67,54,0.06)"
    return "pos-normal", ""


def fmt_form(form_str):
    if not form_str:
        return ""
    parts = []
    for c in str(form_str)[-5:]:
        css = {"W": "form-w", "D": "form-d", "L": "form-l"}.get(c.upper(), "")
        parts.append(f'<span class="{css}">{c.upper()}</span>' if css else c)
    return " ".join(parts)


TABLE_HEADER = (
    '<table style="width:100%;border-collapse:collapse;font-size:0.85rem">'
    '<thead><tr style="border-bottom:2px solid #252840">'
    '<th style="padding:7px 5px;color:#555;text-align:center">Pos</th>'
    '<th style="padding:7px 5px;color:#555;text-align:left">Time</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">J</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">V</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">E</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">D</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">GP</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">GC</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">SG</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">Pts</th>'
    '<th style="padding:7px 5px;color:#555;text-align:center">Forma</th>'
    '</tr></thead><tbody>'
)


def render_table(group_df, zc):
    rows_html = []
    n = len(group_df)
    for _, row in group_df.iterrows():
        pos = int(row["position"])
        pos_class, row_bg = get_row_style(pos, n, zc)
        form_html = fmt_form(str(row.get("form", "")))
        gd = int(row["goal_diff"])
        sg = f"{gd:+d}"
        sg_color = "#81c784" if gd > 0 else "#ef9a9a" if gd < 0 else "#aaa"
        rows_html.append(
            f'<tr style="border-bottom:1px solid #1a1d2e;background:{row_bg}">'
            f'<td style="padding:6px 5px;text-align:center"><span class="pos-badge {pos_class}">{pos}</span></td>'
            f'<td style="padding:6px 5px"><b style="color:#eee">{row["team_name"]}</b></td>'
            f'<td style="padding:6px 5px;text-align:center;color:#aaa">{int(row["played"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:#81c784">{int(row["won"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:#ffb74d">{int(row["drawn"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:#ef9a9a">{int(row["lost"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:#aaa">{int(row["goals_for"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:#aaa">{int(row["goals_against"])}</td>'
            f'<td style="padding:6px 5px;text-align:center;color:{sg_color}">{sg}</td>'
            f'<td style="padding:6px 5px;text-align:center"><b style="color:#fff">{int(row["points"])}</b></td>'
            f'<td style="padding:6px 8px">{form_html}</td>'
            f'</tr>'
        )
    return TABLE_HEADER + "".join(rows_html) + "</tbody></table>"


# Renderizacao: grupos ou tabela unica
if has_groups:
    groups = df["group"].unique()
    for i in range(0, len(groups), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j >= len(groups):
                break
            g = groups[i + j]
            gdf = df[df["group"] == g].sort_values("points", ascending=False).reset_index(drop=True)
            gdf["position"] = range(1, len(gdf) + 1)
            with col:
                st.markdown(
                    f'<div style="font-size:1rem;font-weight:700;color:#64b5f6;'
                    f'border-left:3px solid #64b5f6;padding-left:8px;margin:16px 0 6px">{g}</div>',
                    unsafe_allow_html=True
                )
                zc_group = {"cl": 2, "euro": 0, "rel": 0}
                st.markdown(render_table(gdf, zc_group), unsafe_allow_html=True)

    st.markdown("")
    st.markdown(
        '<div style="font-size:0.78rem;color:#666;margin-top:12px">'
        '<span style="color:#64b5f6">●</span> Top 2 de cada grupo avancam'
        '</div>',
        unsafe_allow_html=True
    )
else:
    zc = zc_default
    st.markdown(render_table(df, zc), unsafe_allow_html=True)
    st.markdown("")
    legend_items = []
    if zc["cl"] > 0:
        legend_items.append('<span style="color:#64b5f6">●</span> Champions League')
    if zc["euro"] > 0:
        legend_items.append('<span style="color:#ffb74d">●</span> Classificacao continental')
    if zc["rel"] > 0:
        legend_items.append('<span style="color:#ef9a9a">●</span> Rebaixamento')
    if legend_items:
        st.markdown(
            '<div style="font-size:0.78rem;color:#666;display:flex;gap:16px">'
            + " &nbsp; ".join(legend_items) + "</div>",
            unsafe_allow_html=True,
        )

st.markdown("---")

with st.expander("Ver grafico de pontos"):
    top10 = df.sort_values("points", ascending=False).head(10)
    fig = go.Figure(go.Bar(
        x=top10["team_name"],
        y=top10["points"].astype(int),
        marker=dict(
            color=top10["points"].astype(int),
            colorscale=[[0,"#1e2138"],[0.5,"#3d43ff"],[1,"#7c83ff"]],
        ),
        text=top10["points"].astype(int),
        textposition="outside",
        textfont=dict(color="#aaa"),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=320,
        margin=dict(t=20, b=20),
        xaxis=dict(tickangle=-30, color="#666"),
        yaxis=dict(color="#666", gridcolor="#1a1d2e"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.caption("Fonte: ESPN / API-Football / football-data.org · Atualizacao a cada 12h")
