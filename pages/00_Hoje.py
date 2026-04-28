"""
Página: Hoje & Esta Semana
Jogos do dia e da semana com indicações rápidas de apostas.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

st.set_page_config(
    page_title="Hoje | Football Analytics",
    page_icon="📅",
    layout="wide",
)

from config import TIMEZONE
from src.fetchers.api_football import get_fetcher
from src.fetchers.football_data_org import FD_STATUS_MAP, FD_FREE_COMPETITIONS
from src.utils.helpers import check_api_configured

# ── CSS da página ──────────────────────────────────────────────────
st.markdown("""
<style>
.match-card {
    background: #1a1d2e;
    border-radius: 12px;
    padding: 14px 18px;
    margin: 6px 0;
    border: 1px solid #2a2d3e;
    transition: border-color 0.2s;
}
.match-card:hover { border-color: #4a4d6e; }
.match-card-live {
    background: #1e1a10;
    border: 1px solid #ff6b00;
    animation: pulse-border 2s infinite;
}
@keyframes pulse-border {
    0%,100% { border-color: #ff6b00; }
    50%      { border-color: #ff9800; }
}
.match-time   { font-size: 0.85rem; color: #888; min-width: 52px; }
.match-team   { font-size: 1rem; font-weight: 600; color: #eee; }
.match-score  { font-size: 1.3rem; font-weight: 800; color: #fff;
                background: #252838; border-radius: 8px;
                padding: 4px 12px; min-width: 64px; text-align: center; }
.match-vs     { font-size: 0.9rem; color: #666; min-width: 32px; text-align: center; }
.live-badge   { background: #ff4444; color: white; font-size: 0.65rem;
                font-weight: 700; padding: 2px 7px; border-radius: 10px;
                letter-spacing: 1px; }
.comp-badge   { font-size: 0.7rem; color: #888; margin-top: 3px; }
.bet-pill     { display: inline-block; font-size: 0.72rem; font-weight: 600;
                padding: 2px 8px; border-radius: 10px; margin: 2px 2px 0 0; }
.bet-green  { background: rgba(76,175,80,0.2);  color: #81c784; border: 1px solid #4CAF50; }
.bet-yellow { background: rgba(255,193,7,0.2);  color: #ffd54f; border: 1px solid #FFC107; }
.bet-blue   { background: rgba(33,150,243,0.2); color: #64b5f6; border: 1px solid #2196F3; }
.day-header { font-size: 1.1rem; font-weight: 700; color: #ccc;
              padding: 10px 0 6px; border-bottom: 1px solid #2a2d3e; margin-bottom: 8px; }
.no-games   { color: #555; font-style: italic; padding: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ── Funções auxiliares ─────────────────────────────────────────────
tz_br = pytz.timezone(TIMEZONE)

def local_time(dt) -> str:
    if pd.isna(dt):
        return "--:--"
    try:
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz_br).strftime("%H:%M")
    except Exception:
        return "--:--"

def local_date(dt) -> str:
    try:
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz_br).strftime("%Y-%m-%d")
    except Exception:
        return str(dt)[:10]

def status_display(status: str):
    icon, label = FD_STATUS_MAP.get(status, ("⚪", status))
    return icon, label

def quick_bet_tips(row) -> list:
    """Gera dicas rápidas baseadas em dados simples disponíveis no jogo."""
    tips = []
    h = row.get("home_team", "")
    a = row.get("away_team", "")
    comp = row.get("competition_name", row.get("competition", ""))
    tips.append(("blue", f"Confira análise completa"))
    return tips

def render_match_card(row, show_tips: bool = True):
    status = row.get("status", "")
    icon, label = status_display(status)
    is_live = status in ("IN_PLAY", "PAUSED")
    is_finished = status == "FINISHED"

    home = row.get("home_team", "—")
    away = row.get("away_team", "—")
    hg = row.get("home_goals")
    ag = row.get("away_goals")
    comp = row.get("competition_name", row.get("competition", ""))
    t = local_time(row.get("date"))

    card_class = "match-card-live" if is_live else "match-card"

    if is_finished or is_live:
        score_html = (
            f'<span class="match-score">'
            f'{int(hg) if hg is not None else "?"} '
            f'- '
            f'{int(ag) if ag is not None else "?"}'
            f'</span>'
        )
    else:
        score_html = f'<span class="match-vs">vs</span>'

    live_html = '<span class="live-badge">AO VIVO</span>' if is_live else ""

    html = f"""
    <div class="{card_class}">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span class="match-time">{t}</span>
        <span class="match-team" style="text-align:right;flex:1">{home}</span>
        {score_html}
        <span class="match-team" style="flex:1">{away}</span>
        <span style="font-size:0.8rem;color:#666;min-width:80px;text-align:right">
          {icon} {label} {live_html}
        </span>
      </div>
      <div class="comp-badge">{comp}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ── SIDEBAR ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filtros")
    days_range  = st.slider("Dias a mostrar", 1, 14, 7)
    force_ref   = st.button("Atualizar dados")

    st.markdown("---")
    st.markdown("**Competições disponíveis (plano grátis)**")
    from config import COMPETITIONS
    avail_comps = {k: COMPETITIONS[k] for k in FD_FREE_COMPETITIONS if k in COMPETITIONS}
    selected_comps = []
    for key, comp in avail_comps.items():
        if st.checkbox(f"{comp['flag']} {comp['name']}", value=True, key=f"c_{key}"):
            selected_comps.append(FD_FREE_COMPETITIONS[key])

    st.markdown("---")
    st.caption("Brasileirão não está no plano gratuito do football-data.org. "
               "Para acessar, configure API-Football (RapidAPI) no .env")

# ── Verificações ───────────────────────────────────────────────────
st.markdown("# 📅 Jogos da Semana")

if not any(check_api_configured().values()):
    st.error("Configure suas chaves de API no arquivo `.env`")
    st.stop()

fetcher = get_fetcher()
now_br  = datetime.now(tz_br)
today   = now_br.strftime("%Y-%m-%d")
end     = (now_br + timedelta(days=days_range - 1)).strftime("%Y-%m-%d")

# ── Carrega jogos ─────────────────────────────────────────────────
with st.spinner("Carregando jogos..."):
    try:
        df = fetcher.get_matches_by_date(
            date_from=today,
            date_to=end,
            competitions=selected_comps if selected_comps else None,
            force_refresh=force_ref,
        )
    except Exception as e:
        st.error(f"Erro ao carregar jogos: {e}")
        st.stop()

if df.empty:
    st.info("Nenhum jogo encontrado para o período selecionado.")
    st.stop()

# ── Converte datas para fuso local ────────────────────────────────
df["date_local"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
df["day_str"]    = df["date_local"].apply(local_date)
df = df.sort_values("date_local")

# ── Métricas rápidas ──────────────────────────────────────────────
live_games = df[df["status"].isin(("IN_PLAY", "PAUSED"))]
today_games = df[df["day_str"] == today]
finished_today = today_games[today_games["status"] == "FINISHED"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Jogos hoje",       len(today_games))
c2.metric("Ao vivo agora",    len(live_games),  delta="🔴" if len(live_games) else None)
c3.metric("Encerrados hoje",  len(finished_today))
c4.metric("Total na semana",  len(df))

st.markdown("---")

# ── Jogos ao vivo – destaque ──────────────────────────────────────
if not live_games.empty:
    st.markdown("## 🔴 Ao Vivo Agora")
    for _, row in live_games.iterrows():
        render_match_card(row)
    st.markdown("---")

# ── Agrupa por dia ────────────────────────────────────────────────
days = sorted(df["day_str"].unique())
days_labels = {
    today: "Hoje",
    (now_br + timedelta(days=1)).strftime("%Y-%m-%d"): "Amanhã",
}

for day in days:
    day_games = df[df["day_str"] == day].copy()
    if day_games.empty:
        continue

    # Label do dia
    try:
        dt_obj = datetime.strptime(day, "%Y-%m-%d")
        pt_days = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
        weekday_pt = pt_days[dt_obj.weekday()]
        day_label = days_labels.get(day, f"{weekday_pt}, {dt_obj.strftime('%d/%m')}")
    except Exception:
        day_label = day

    n_games = len(day_games)
    live_today = day_games[day_games["status"].isin(("IN_PLAY","PAUSED"))]
    live_indicator = " 🔴" if not live_today.empty else ""

    st.markdown(f"""
    <div class="day-header">{day_label}{live_indicator} &nbsp;
      <span style="font-size:0.8rem;color:#666;font-weight:400">{n_games} jogos</span>
    </div>
    """, unsafe_allow_html=True)

    # Agrupa por competição dentro do dia
    comps_in_day = day_games["competition_name"].fillna(day_games["competition"]).unique()

    for comp_name in comps_in_day:
        comp_games = day_games[
            (day_games["competition_name"].fillna(day_games["competition"])) == comp_name
        ].sort_values("date_local")

        st.markdown(f"**{comp_name}**")
        for _, row in comp_games.iterrows():
            render_match_card(row)

    st.markdown("")

# ── Quick link para bet advisor ───────────────────────────────────
st.markdown("---")
st.info("Para análise detalhada com probabilidades e recomendações de apostas, "
        "acesse a página **Bet Advisor** no menu lateral.")
