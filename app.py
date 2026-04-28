"""
app.py - Football Analytics | Entrypoint
Execute com: streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Football Analytics",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS global
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0d0f1a; }
[data-testid="stSidebar"]          { background: #111320; border-right: 1px solid #1e2035; }
h1,h2,h3 { color: #ffffff !important; }
hr { border-color: #1e2035 !important; }
</style>
""", unsafe_allow_html=True)

pg = st.navigation(
    [
        st.Page("pages/01_Classificacao.py",    title="Classificação",    icon="📊"),
        st.Page("pages/02_Analise_Time.py",     title="Análise de Time",  icon="🔍"),
        st.Page("pages/03_Confronto_Direto.py", title="Confronto Direto", icon="⚔️"),
        st.Page("pages/04_Proximos_Jogos.py",   title="Próximos Jogos",   icon="📅"),
    ],
    position="sidebar",
)
pg.run()
