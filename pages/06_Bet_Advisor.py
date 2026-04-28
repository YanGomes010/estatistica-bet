"""
Pagina: Bet Advisor
Recomendacao de apostas baseada em modelo estatistico (Poisson + Dixon-Coles).
AVISO LEGAL: Ferramenta informativa. Aposte com responsabilidade.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

st.set_page_config(page_title="Bet Advisor | Football Analytics", page_icon="⚡", layout="wide")

from config import COMPETITIONS, DEFAULT_SEASON, FORM_GAMES, H2H_GAMES, get_current_season
from src.utils.helpers import competition_options, season_options, check_api_configured
from src.fetchers.api_football import get_fetcher
from src.fetchers.football_data_org import get_fd_season
from src.fetchers.fbref import get_fbref
from src.analytics.form import compute_form, compute_home_away_split
from src.analytics.h2h import compute_h2h
from src.analytics.advanced import compute_xg_stats
from src.analytics.betting import generate_betting_report, BettingReport, MarketTip, build_score_matrix

# CSS
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d0f1a; }
[data-testid="stSidebar"]          { background: #111320; }
.stat-card {
    background: #13152a; border: 1px solid #1e2240;
    border-radius: 10px; padding: 14px 16px; margin: 4px 0;
}
.stat-label { font-size: 0.7rem; color: #666; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px; }
.stat-value { font-size: 1.4rem; font-weight: 800; color: #fff; }
.stat-sub   { font-size: 0.8rem; color: #888; margin-top: 2px; }
.form-badge-W { display:inline-block;background:#388E3C;color:white;
    padding:3px 7px;border-radius:5px;font-weight:800;font-size:0.8rem;margin:1px;}
.form-badge-D { display:inline-block;background:#F57F17;color:white;
    padding:3px 7px;border-radius:5px;font-weight:800;font-size:0.8rem;margin:1px;}
.form-badge-L { display:inline-block;background:#C62828;color:white;
    padding:3px 7px;border-radius:5px;font-weight:800;font-size:0.8rem;margin:1px;}
.team-header {
    font-size: 1.4rem; font-weight: 800; color: #fff;
    border-bottom: 2px solid #252840; padding-bottom: 8px; margin-bottom: 12px;
}
.pick-top {
    background: linear-gradient(135deg,#0a1f0a,#122a12);
    border: 2px solid #43A047; border-radius: 14px; padding: 22px;
}
.pick-card {
    background: #13152a; border-left: 3px solid #43A047;
    border-radius: 8px; padding: 14px; margin: 4px 0;
}
.disclaimer {
    background:#1a0808; border:1px solid #b71c1c; border-radius:8px;
    padding:10px 14px; font-size:0.78rem; color:#ef9a9a; margin:10px 0;
}
</style>
""", unsafe_allow_html=True)

# SIDEBAR
with st.sidebar:
    st.header("⚙️ Configuracoes")
    comp_options  = competition_options()
    comp_labels   = [x[0] for x in comp_options]
    comp_keys     = [x[1] for x in comp_options]
    selected_label  = st.selectbox("Competicao", comp_labels)
    competition_key = comp_keys[comp_labels.index(selected_label)]
    comp_cur_szn    = get_current_season(competition_key)
    seasons         = season_options(competition_key)
    default_szn_idx = seasons.index(comp_cur_szn) if comp_cur_szn in seasons else 0
    season          = st.selectbox("Temporada", seasons, index=default_szn_idx)
    st.divider()
    st.markdown("**Parametros do Modelo**")
    form_n   = st.slider("Jogos de forma", 3, 10, FORM_GAMES)
    h2h_n    = st.slider("Historico H2H", 5, 20, H2H_GAMES)
    show_all = st.checkbox("Mostrar todos os mercados", value=False)
    st.divider()
    force_refresh = st.button("🔄 Atualizar dados")
    st.markdown("""
    <div class="disclaimer">
    ⚠️ <b>AVISO:</b> Apostas envolvem risco financeiro real. Esta analise e puramente informativa.
    Aposte com responsabilidade. Proibido para menores de 18 anos.
    </div>""", unsafe_allow_html=True)

# HEADER
st.markdown(
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">'
    '<span style="font-size:2.2rem">⚡</span>'
    '<div><h1 style="margin:0;color:#fff">Bet Advisor</h1>'
    '<p style="margin:0;color:#666;font-size:0.85rem">Modelo Poisson + Dixon-Coles • Dados reais ESPN / API-Football</p></div>'
    '</div>', unsafe_allow_html=True
)

# API CHECK
if not any(check_api_configured().values()):
    st.error("Configure suas chaves de API no arquivo `.env`.")
    st.stop()

fetcher = get_fetcher()
fbref   = get_fbref()
comp    = COMPETITIONS[competition_key]

# SELECAO DE TIMES
@st.cache_data(ttl=3600, show_spinner=False)
def load_teams(comp_key, szn):
    return fetcher.get_teams(comp_key, szn)

@st.cache_data(ttl=3600, show_spinner=False)
def load_standings(comp_key, szn):
    try:
        return fetcher.get_standings(comp_key, szn)
    except Exception:
        return pd.DataFrame()

with st.spinner("Carregando times..."):
    try:
        teams_df     = load_teams(competition_key, season)
        standings_df = load_standings(competition_key, season)
    except Exception as e:
        st.error(f"Erro ao carregar times: {e}")
        st.stop()

if teams_df is None or teams_df.empty:
    st.warning("Nenhum time encontrado para esta competicao/temporada.")
    st.stop()

team_map   = dict(zip(teams_df["team_name"], teams_df["team_id"]))
team_names = sorted(team_map.keys())

st.markdown("---")
col_t1, col_mid, col_t2 = st.columns([5, 1, 5])
with col_t1:
    home_name = st.selectbox("🏠 Mandante", team_names, index=0)
with col_mid:
    st.markdown("<div style='text-align:center;margin-top:26px;font-size:2rem;color:#FFC107'>⚡</div>", unsafe_allow_html=True)
with col_t2:
    away_opts = [t for t in team_names if t != home_name]
    away_name = st.selectbox("✈️ Visitante", away_opts, index=min(1, len(away_opts)-1))

home_id = team_map[home_name]
away_id = team_map[away_name]

analyze_btn = st.button("🔮 Gerar Analise de Apostas", type="primary", use_container_width=True)

if not analyze_btn:
    st.markdown("---")
    with st.expander("ℹ️ Como funciona o modelo?"):
        st.markdown("""
**Modelo de Poisson com ajuste Dixon-Coles**
Calcula a distribuicao de probabilidade para cada placar (0-0 ate 8-8),
corrigindo placares baixos que o Poisson puro subestima.

| Componente | Peso |
|---|---|
| Forma recente (ultimos 5 jogos) | 30% |
| xG medio (FBref/StatsBomb) | 25% |
| Desempenho casa/fora | 20% |
| Historico H2H | 15% |
| Desempenho na temporada | 10% |

Score de Confianca (0-100): apenas mercados com confianca >= 35% sao recomendados.
        """)
    st.stop()

# CARREGA DADOS
bar = st.progress(0, text="Carregando dados...")
try:
    bar.progress(15, "Buscando jogos da temporada...")
    fixtures_df = fetcher.get_fixtures(competition_key, season, force_refresh=force_refresh)

    bar.progress(30, "Buscando confrontos diretos...")
    h2h_df = fetcher.get_h2h(home_id, away_id, last=h2h_n)

    bar.progress(45, "Verificando desfalques...")
    home_inj_df = fetcher.get_injuries(home_id, season)
    away_inj_df = fetcher.get_injuries(away_id, season)

    bar.progress(60, "Buscando dados de xG...")
    xg_df = fbref.get_season_xg(competition_key, season)

    bar.progress(80, "Calculando probabilidades...")
    home_form = compute_form(fixtures_df, home_id, form_n)
    away_form = compute_form(fixtures_df, away_id, form_n)
    home_ha   = compute_home_away_split(fixtures_df, home_id)
    away_ha   = compute_home_away_split(fixtures_df, away_id)
    home_xg   = compute_xg_stats(xg_df, home_name)
    away_xg   = compute_xg_stats(xg_df, away_name)
    h2h       = compute_h2h(h2h_df, home_id, away_id)

    def get_standing(tid):
        if standings_df.empty:
            return None
        row = standings_df[standings_df["team_id"] == tid]
        return row.iloc[0].to_dict() if not row.empty else None

    home_standing = get_standing(home_id)
    away_standing = get_standing(away_id)
    n_home_inj = len(home_inj_df) if home_inj_df is not None else 0
    n_away_inj = len(away_inj_df) if away_inj_df is not None else 0

    report = generate_betting_report(
        home_name=home_name, away_name=away_name,
        home_form=home_form, away_form=away_form,
        home_ha=home_ha, away_ha=away_ha,
        home_xg=home_xg, away_xg=away_xg,
        h2h=h2h,
        home_standings=home_standing, away_standings=away_standing,
        home_injuries=n_home_inj, away_injuries=n_away_inj,
    )
    bar.progress(100, "Analise concluida!")
    bar.empty()
except Exception as e:
    bar.empty()
    st.error(f"Erro ao processar analise: {e}")
    st.exception(e)
    st.stop()

# DISCLAIMER
st.markdown("""
<div class="disclaimer">
⚠️ <b>AVISO:</b> Analise baseada em modelo estatistico. Resultados passados nao garantem resultados futuros.
Aposte apenas o que pode perder. Jogo responsavel: <b>0800 722 3898</b>
</div>""", unsafe_allow_html=True)

# HEADER DO CONFRONTO
p_h = report.prob_home_win * 100
p_d = report.prob_draw * 100
p_a = report.prob_away_win * 100
fav_h = p_h >= p_d and p_h >= p_a
fav_a = p_a >= p_h and p_a >= p_d

st.markdown(f"""
<div style="background:linear-gradient(135deg,#0d0f1e,#161830);border:1px solid #252840;
border-radius:16px;padding:28px;margin:12px 0;text-align:center">
  <div style="font-size:0.85rem;color:#555;margin-bottom:12px">{comp['flag']} {comp['name']} • {season}</div>
  <div style="display:flex;justify-content:center;align-items:center;gap:24px;flex-wrap:wrap">
    <div style="text-align:right;min-width:160px">
      <div style="font-size:1.8rem;font-weight:900;color:#fff">{home_name}</div>
      <div style="color:#4CAF50;font-size:0.9rem">🏠 Mandante {'⭐' if fav_h else ''}</div>
      <div style="font-size:2.5rem;font-weight:900;color:#4CAF50;margin-top:4px">{p_h:.0f}%</div>
    </div>
    <div style="text-align:center;min-width:100px">
      <div style="font-size:0.8rem;color:#555;margin-bottom:6px">Gols esperados</div>
      <div style="font-size:2rem;font-weight:900;color:#FFC107">{report.home_lambda:.1f} — {report.away_lambda:.1f}</div>
      <div style="font-size:1.1rem;color:#888;margin-top:6px">Empate</div>
      <div style="font-size:2rem;font-weight:900;color:#FFC107">{p_d:.0f}%</div>
    </div>
    <div style="text-align:left;min-width:160px">
      <div style="font-size:1.8rem;font-weight:900;color:#fff">{away_name}</div>
      <div style="color:#F44336;font-size:0.9rem">✈️ Visitante {'⭐' if fav_a else ''}</div>
      <div style="font-size:2.5rem;font-weight:900;color:#F44336;margin-top:4px">{p_a:.0f}%</div>
    </div>
  </div>
  <div style="display:flex;border-radius:6px;overflow:hidden;height:16px;margin-top:16px">
    <div style="width:{p_h:.1f}%;background:#4CAF50;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:white;font-weight:700">{p_h:.0f}%</div>
    <div style="width:{p_d:.1f}%;background:#FFC107;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:black;font-weight:700">{p_d:.0f}%</div>
    <div style="width:{p_a:.1f}%;background:#F44336;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:white;font-weight:700">{p_a:.0f}%</div>
  </div>
</div>
""", unsafe_allow_html=True)

# TOP PICKS
st.markdown("### ⚡ Melhores Apostas")
if report.warnings:
    for w in report.warnings:
        st.warning(w)

if not report.top_picks:
    st.info("Nenhuma aposta com confianca suficiente. Aguarde mais dados.")
else:
    best = report.top_picks[0]
    cc = "#4CAF50" if best.confidence >= 65 else "#FF9800" if best.confidence >= 45 else "#F44336"
    stars = "⭐" * best.star_rating
    st.markdown(f"""
    <div class="pick-top">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
        <div>
          <div style="font-size:0.7rem;color:#81c784;text-transform:uppercase;letter-spacing:1px">
            🏆 MELHOR APOSTA • {best.market}
          </div>
          <div style="font-size:2.2rem;font-weight:900;color:#fff;margin:6px 0;line-height:1.1">{best.pick}</div>
          <div style="font-size:1.6rem;color:#4CAF50;font-weight:700">{best.probability*100:.1f}%</div>
          <div style="color:#FFC107;font-size:0.95rem;margin-top:4px">Odd justa: <b>{best.odds_fair:.2f}</b></div>
        </div>
        <div style="text-align:center;background:rgba(0,0,0,0.3);border-radius:12px;padding:16px 24px">
          <div style="font-size:2rem">{stars}</div>
          <div style="font-size:3rem;font-weight:900;color:{cc};line-height:1">{best.confidence}</div>
          <div style="font-size:0.7rem;color:#aaa;text-transform:uppercase">confianca / 100</div>
          <div style="background:#1a1a1a;border-radius:4px;height:6px;margin-top:8px">
            <div style="width:{best.confidence}%;background:{cc};height:100%;border-radius:4px"></div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if len(report.top_picks) > 1:
        st.markdown("<div style='margin-top:12px;margin-bottom:6px;color:#888;font-size:0.85rem'>Outras apostas recomendadas</div>", unsafe_allow_html=True)
        pick_cols = st.columns(min(4, len(report.top_picks)-1))
        for i, tip in enumerate(report.top_picks[1:]):
            cc2 = "#4CAF50" if tip.confidence >= 65 else "#FF9800" if tip.confidence >= 45 else "#9E9E9E"
            with pick_cols[i % len(pick_cols)]:
                st.markdown(f"""
                <div class="pick-card" style="border-left-color:{cc2}">
                  <div style="font-size:0.65rem;color:#666;text-transform:uppercase;letter-spacing:1px">{tip.market}</div>
                  <div style="font-size:1.05rem;font-weight:700;color:#fff;margin:4px 0">{tip.pick}</div>
                  <div style="color:{cc2};font-weight:700;font-size:1.1rem">{tip.probability*100:.1f}%</div>
                  <div style="color:#FFC107;font-size:0.8rem">Odd: {tip.odds_fair:.2f}</div>
                  <div style="color:#555;font-size:0.7rem;margin-top:4px">Confianca: {tip.confidence}/100 {"⭐"*tip.star_rating}</div>
                </div>""", unsafe_allow_html=True)

st.markdown("---")

# BASE DA ANALISE — visual moderno
st.markdown("### 📋 Base da Analise")
tab_form, tab_h2h, tab_xg, tab_inj = st.tabs(["📈 Forma & Casa/Fora", "⚔️ H2H", "📐 xG & Ataque", "🏥 Desfalques"])

def form_badges(fs):
    if not fs:
        return '<span style="color:#555">Sem dados</span>'
    html = ""
    for c in str(fs)[-5:]:
        css = {"W":"form-badge-W","D":"form-badge-D","L":"form-badge-L"}.get(c.upper(),"")
        html += f'<span class="{css}">{c.upper()}</span>' if css else c
    return html

def stat_row(label, value, sub="", color="#fff"):
    sub_html = f'<br><span style="color:#555;font-size:0.75rem">{sub}</span>' if sub else ""
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:8px 0;border-bottom:1px solid #1a1d2e">'
        f'<span style="color:#666;font-size:0.8rem">{label}</span>'
        f'<span style="color:{color};font-weight:700;font-size:0.95rem">{value}{sub_html}</span>'
        f'</div>'
    )

with tab_form:
    cL, cR = st.columns(2)
    with cL:
        ha_h  = home_ha.get("home", {})
        fs_h  = home_form.get("form_string","")
        pct_h = home_form.get("pct", 0)
        st.markdown(f"""
        <div class="stat-card">
          <div class="team-header">🏠 {home_name}</div>
          <div style="margin-bottom:10px">
            <div class="stat-label">Forma recente</div>
            <div style="margin-top:4px">{form_badges(fs_h)}</div>
          </div>
          {stat_row("V / E / D", f"{home_form.get('wins',0)} / {home_form.get('draws',0)} / {home_form.get('losses',0)}")}
          {stat_row("Aproveitamento geral", f"{pct_h:.0f}%", color="#4CAF50" if pct_h>=60 else "#FF9800" if pct_h>=40 else "#F44336")}
          {stat_row("Gols/jogo (pro/contra)", f"{home_form.get('avg_gf',0):.1f} / {home_form.get('avg_ga',0):.1f}")}
          {stat_row("Como mandante", f"{ha_h.get('pct',0):.0f}% ({ha_h.get('wins',0)}V {ha_h.get('draws',0)}E {ha_h.get('losses',0)}D)")}
          {stat_row("Gols em casa/jogo", f"{ha_h.get('avg_gf',0):.1f} pro · {ha_h.get('avg_ga',0):.1f} contra")}
        </div>""", unsafe_allow_html=True)
    with cR:
        ha_a  = away_ha.get("away", {})
        fs_a  = away_form.get("form_string","")
        pct_a = away_form.get("pct", 0)
        st.markdown(f"""
        <div class="stat-card">
          <div class="team-header">✈️ {away_name}</div>
          <div style="margin-bottom:10px">
            <div class="stat-label">Forma recente</div>
            <div style="margin-top:4px">{form_badges(fs_a)}</div>
          </div>
          {stat_row("V / E / D", f"{away_form.get('wins',0)} / {away_form.get('draws',0)} / {away_form.get('losses',0)}")}
          {stat_row("Aproveitamento geral", f"{pct_a:.0f}%", color="#4CAF50" if pct_a>=60 else "#FF9800" if pct_a>=40 else "#F44336")}
          {stat_row("Gols/jogo (pro/contra)", f"{away_form.get('avg_gf',0):.1f} / {away_form.get('avg_ga',0):.1f}")}
          {stat_row("Como visitante", f"{ha_a.get('pct',0):.0f}% ({ha_a.get('wins',0)}V {ha_a.get('draws',0)}E {ha_a.get('losses',0)}D)")}
          {stat_row("Gols fora/jogo", f"{ha_a.get('avg_gf',0):.1f} pro · {ha_a.get('avg_ga',0):.1f} contra")}
        </div>""", unsafe_allow_html=True)

    # Grafico comparativo
    st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
    cats  = ["Vitorias", "Empates", "Derrotas", "Gols pro/j", "Aproveit%/5"]
    hvals = [home_form.get("wins",0), home_form.get("draws",0), home_form.get("losses",0),
             home_form.get("avg_gf",0), home_form.get("pct",0)/20]
    avals = [away_form.get("wins",0), away_form.get("draws",0), away_form.get("losses",0),
             away_form.get("avg_gf",0), away_form.get("pct",0)/20]
    fig_c = go.Figure()
    fig_c.add_trace(go.Bar(name=home_name, x=cats, y=hvals, marker_color="#4CAF50"))
    fig_c.add_trace(go.Bar(name=away_name, x=cats, y=avals, marker_color="#2196F3"))
    fig_c.update_layout(barmode="group", template="plotly_dark", height=240,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        margin=dict(t=10,b=10), legend=dict(orientation="h",y=1.1),
                        font=dict(color="#888"))
    st.plotly_chart(fig_c, use_container_width=True)

with tab_h2h:
    if h2h.get("total_games", 0) == 0:
        st.info("Sem historico de confrontos diretos disponivel.")
    else:
        tot = h2h["total_games"]
        hw  = h2h["team1_wins"]
        dr  = h2h["draws"]
        aw  = h2h["team2_wins"]

        # Barra de dominancia
        pct_hw = hw/tot*100 if tot else 0
        pct_dr = dr/tot*100 if tot else 0
        pct_aw = aw/tot*100 if tot else 0
        st.markdown(f"""
        <div class="stat-card" style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span style="font-size:1.1rem;font-weight:800;color:#4CAF50">{home_name}: {hw}V</span>
            <span style="font-size:1.1rem;font-weight:800;color:#FFC107">Empates: {dr}</span>
            <span style="font-size:1.1rem;font-weight:800;color:#F44336">{away_name}: {aw}V</span>
          </div>
          <div style="display:flex;border-radius:6px;overflow:hidden;height:12px">
            <div style="width:{pct_hw:.1f}%;background:#4CAF50"></div>
            <div style="width:{pct_dr:.1f}%;background:#FFC107"></div>
            <div style="width:{pct_aw:.1f}%;background:#F44336"></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:0.75rem;color:#666">
            <span>{pct_hw:.0f}%</span><span>{pct_dr:.0f}%</span><span>{pct_aw:.0f}%</span>
          </div>
        </div>""", unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total de jogos", tot)
        m2.metric("Media de gols", h2h.get("avg_goals_per_game", 0))
        m3.metric("BTTS %", f"{h2h.get('btts_pct',0)}%")
        m4.metric("Over 2.5 %", f"{h2h.get('over25_pct',0)}%")

        if not h2h["summary_df"].empty:
            st.markdown("<div style='margin-top:12px;color:#888;font-size:0.8rem'>Ultimos confrontos</div>", unsafe_allow_html=True)
            sdf = h2h["summary_df"].head(8).copy()
            sdf["Jogo"] = sdf.apply(
                lambda r: f"{r['home_team']}  {int(r['home_goals'])}×{int(r['away_goals'])}  {r['away_team']}", axis=1)
            sdf["Venc"] = sdf["result_team1"].map({
                "W": f"✅ {home_name}", "L": f"✅ {away_name}", "D": "🟡 Empate"})
            st.dataframe(sdf[["Jogo","Venc"]].rename(columns={"Venc":"Resultado"}),
                         use_container_width=True, hide_index=True)

with tab_xg:
    cxL, cxR = st.columns(2)
    with cxL:
        st.markdown(f"""
        <div class="stat-card">
          <div class="team-header">🏠 {home_name}</div>
          {stat_row("xG medio a favor", f"{home_xg.get('avg_xgf',0):.2f}" if home_xg.get('played',0)>0 else "N/D")}
          {stat_row("xG medio contra", f"{home_xg.get('avg_xga',0):.2f}" if home_xg.get('played',0)>0 else "N/D")}
          {stat_row("Saldo xG", f"{home_xg.get('xgd',0):+.2f}" if home_xg.get('played',0)>0 else "N/D")}
          {stat_row("Eficiencia (G/xG)", f"{home_xg.get('xg_efficiency',0):.2f}" if home_xg.get('xg_efficiency') else "N/D")}
        </div>""", unsafe_allow_html=True)
    with cxR:
        st.markdown(f"""
        <div class="stat-card">
          <div class="team-header">✈️ {away_name}</div>
          {stat_row("xG medio a favor", f"{away_xg.get('avg_xgf',0):.2f}" if away_xg.get('played',0)>0 else "N/D")}
          {stat_row("xG medio contra", f"{away_xg.get('avg_xga',0):.2f}" if away_xg.get('played',0)>0 else "N/D")}
          {stat_row("Saldo xG", f"{away_xg.get('xgd',0):+.2f}" if away_xg.get('played',0)>0 else "N/D")}
          {stat_row("Eficiencia (G/xG)", f"{away_xg.get('xg_efficiency',0):.2f}" if away_xg.get('xg_efficiency') else "N/D")}
        </div>""", unsafe_allow_html=True)
    if home_xg.get("played",0) == 0:
        st.info("xG via FBref nao disponivel — o modelo usa gols reais como proxy (media de gols/jogo).")

with tab_inj:
    ci1, ci2 = st.columns(2)
    with ci1:
        st.markdown(f"**🏠 {home_name}**")
        if n_home_inj == 0:
            st.success("✅ Sem desfalques registrados")
        else:
            st.error(f"⚠️ {n_home_inj} desfalque(s)")
            if home_inj_df is not None and not home_inj_df.empty:
                st.dataframe(home_inj_df[["player_name","reason"]].rename(
                    columns={"player_name":"Jogador","reason":"Motivo"}),
                    use_container_width=True, hide_index=True)
    with ci2:
        st.markdown(f"**✈️ {away_name}**")
        if n_away_inj == 0:
            st.success("✅ Sem desfalques registrados")
        else:
            st.error(f"⚠️ {n_away_inj} desfalque(s)")
            if away_inj_df is not None and not away_inj_df.empty:
                st.dataframe(away_inj_df[["player_name","reason"]].rename(
                    columns={"player_name":"Jogador","reason":"Motivo"}),
                    use_container_width=True, hide_index=True)

st.markdown("---")

# MAPA DE PLACARES
st.markdown("### 🎯 Mapa de Probabilidade de Placares")
MAX = 6
score_data, annots = [], []
for ag in range(MAX, -1, -1):
    row = []
    for hg in range(MAX+1):
        p = report.score_matrix.get((hg, ag), 0) * 100
        row.append(round(p, 2))
    score_data.append(row)

fig_heat = go.Figure(go.Heatmap(
    z=score_data,
    x=[str(i) for i in range(MAX+1)],
    y=[str(i) for i in range(MAX, -1, -1)],
    colorscale="YlOrRd",
    text=[[f"{v:.1f}%" for v in row] for row in score_data],
    texttemplate="%{text}", textfont={"size":11},
    showscale=True,
    colorbar=dict(title="Prob %", thickness=12),
))
fig_heat.update_layout(
    template="plotly_dark", height=400,
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis_title=f"Gols {home_name} →",
    yaxis_title=f"← Gols {away_name}",
    margin=dict(t=20,b=40,l=40,r=20),
    font=dict(color="#888"),
)
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("**Placares mais provaveis:**")
sc_cols = st.columns(5)
for i, (score, pct) in enumerate(report.top_scores):
    with sc_cols[i]:
        border = "2px solid #FFC107" if i==0 else "1px solid #252840"
        tc = "#FFC107" if i==0 else "#fff"
        st.markdown(f"""
        <div style="background:#13152a;border:{border};border-radius:10px;
        padding:14px;text-align:center">
          <div style="font-size:1.5rem;font-weight:900;color:{tc}">{score}</div>
          <div style="font-size:1.1rem;color:#4CAF50;font-weight:700">{pct}%</div>
          {"<div style='font-size:0.65rem;color:#666'>mais provavel</div>" if i==0 else ""}
        </div>""", unsafe_allow_html=True)

# TODOS OS MERCADOS
if show_all:
    st.markdown("---")
    st.markdown("### 📊 Todos os Mercados")
    market_groups = {}
    for tip in report.markets:
        market_groups.setdefault(tip.market, []).append(tip)
    for mname, tips in market_groups.items():
        with st.expander(f"**{mname}**"):
            mcols = st.columns(min(len(tips), 3))
            for i, tip in enumerate(tips):
                cc3 = "#4CAF50" if tip.confidence >= 65 else "#FF9800" if tip.confidence >= 35 else "#555"
                with mcols[i % len(mcols)]:
                    st.markdown(f"""
                    <div style="background:#111;border-left:3px solid {cc3};
                    border-radius:6px;padding:12px;margin:4px 0">
                      <div style="font-weight:700;color:#fff">{tip.pick}</div>
                      <div style="color:{cc3};font-size:1.1rem">{tip.probability*100:.1f}%</div>
                      <div style="color:#FFC107;font-size:0.85rem">Odd: {tip.odds_fair:.2f}</div>
                      <div style="color:#555;font-size:0.75rem">Confianca: {tip.confidence}/100</div>
                    </div>""", unsafe_allow_html=True)

# QUALIDADE DOS DADOS
st.markdown("---")
qp = report.data_quality * 100
qc = "#4CAF50" if qp >= 70 else "#FF9800" if qp >= 40 else "#F44336"
ql = "Alta" if qp >= 70 else "Media" if qp >= 40 else "Baixa"
st.markdown(f"""
<div style="background:#111;border-radius:8px;padding:14px;display:flex;align-items:center;gap:16px">
  <div>
    <div style="font-size:0.7rem;color:#555;text-transform:uppercase">Qualidade dos dados</div>
    <div style="font-size:1.2rem;font-weight:700;color:{qc}">{ql} ({qp:.0f}%)</div>
  </div>
  <div style="flex:1;background:#222;border-radius:4px;height:8px">
    <div style="width:{qp}%;background:{qc};height:100%;border-radius:4px"></div>
  </div>
</div>""", unsafe_allow_html=True)

if report.warnings:
    for w in report.warnings:
        st.caption(w)

st.markdown("---")
st.caption("Motor: Poisson + Dixon-Coles (1997) | ESPN / API-Football / FBref | ⚠️ Uso exclusivamente informativo.")
o.")
