"""
Página: Administração do Cache
Inspeciona, limpa e gerencia o cache local.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Cache | Football Analytics", page_icon="💾", layout="wide")

from src.cache.cache_manager import get_cache

st.title("💾 Administração do Cache")
st.caption("Gerencie os dados em cache local (SQLite)")

cache = get_cache()

# ── Estatísticas gerais ──
st.subheader("📊 Estatísticas Gerais")
try:
    stats = cache.stats()
    if stats.empty:
        st.info("Cache vazio.")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de entradas", int(stats["total_entries"].sum()))
        col2.metric("Permanentes",       int(stats["permanent"].sum()))
        col3.metric("Válidas (com TTL)", int(stats["valid"].sum()))
        col4.metric("Expiradas",         int(stats["expired"].sum()))
        st.dataframe(stats, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"Erro: {e}")

st.divider()

# ── Ações ──
st.subheader("🛠️ Ações")
col_a, col_b, col_c = st.columns(3)

with col_a:
    if st.button("🗑️ Limpar entradas expiradas", use_container_width=True):
        n = cache.purge_expired()
        st.success(f"{n} entradas expiradas removidas.")

with col_b:
    category = st.selectbox(
        "Categoria para limpar",
        ["standings","fixtures","results","h2h","team_info","injuries","fbref_stats","live","players"]
    )
    if st.button(f"❌ Limpar '{category}'", use_container_width=True):
        cache.invalidate_category(category)
        st.success(f"Categoria '{category}' limpa.")

with col_c:
    if st.button("⚠️ Limpar TUDO (exceto resultados permanentes)", use_container_width=True):
        for cat in ["standings","fixtures","team_info","injuries","fbref_stats","live","players"]:
            cache.invalidate_category(cat)
        st.success("Cache de dados temporários limpo.")

st.divider()

# ── Listagem detalhada ──
st.subheader("📋 Entradas do Cache")
filter_cat = st.selectbox("Filtrar por categoria", ["Todas"] + [
    "standings","fixtures","results","h2h","team_info","injuries","fbref_stats","live","players"
])

try:
    entries = cache.list_entries(None if filter_cat == "Todas" else filter_cat)
    if entries.empty:
        st.info("Nenhuma entrada encontrada.")
    else:
        entries["size_kb"] = (entries["size_bytes"] / 1024).round(1)
        entries["expires_at"] = entries["expires_at"].dt.strftime("%Y-%m-%d %H:%M").fillna("♾️ Permanente")
        entries["created_at"] = entries["created_at"].dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(
            entries[["category","identifier","created_at","expires_at","hit_count","size_kb"]].rename(
                columns={"category":"Categoria","identifier":"ID","created_at":"Criado em",
                         "expires_at":"Expira em","hit_count":"Hits","size_kb":"Tamanho (KB)"}
            ),
            use_container_width=True, hide_index=True
        )
except Exception as e:
    st.error(f"Erro: {e}")
