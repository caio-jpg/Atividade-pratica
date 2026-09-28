"""
Smart City Dashboard (Streamlit).

Executar a partir da pasta smart_city:
    streamlit run dashboard/app.py
"""

import os
import sys
from datetime import date, datetime, time, timedelta

import requests
import streamlit as st

# Permite "from components..." tanto localmente quanto no Docker
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.analytics import render_analytics  # noqa: E402
from components.map_view import render_map  # noqa: E402
from components.restaurants import render_restaurants  # noqa: E402

st.set_page_config(page_title="Smart City Dashboard", page_icon="🏙️", layout="wide",
                   initial_sidebar_state="expanded")

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")
CENTRO_PADRAO = (-23.5505, -46.6333)  # São Paulo (lat, lon)

# ---------------------------------------------------------------------------
# Estado dos filtros (chaves dos widgets). Uma view carregada é aplicada ANTES
# de os widgets serem criados, senão o Streamlit não permite alterar o valor.
# ---------------------------------------------------------------------------
DEFAULTS = {
    "f_categories": [],
    "f_use_radius": False,
    "f_radius": 1000,
    "f_lat": CENTRO_PADRAO[0],
    "f_lon": CENTRO_PADRAO[1],
    "f_date_from": date.today() - timedelta(days=365),
    "f_date_to": date.today(),
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

if "view_to_load" in st.session_state:
    filtros = st.session_state.pop("view_to_load")
    for k in DEFAULTS:
        if k in filtros and filtros[k] is not None:
            valor = filtros[k]
            if k in ("f_date_from", "f_date_to"):
                valor = date.fromisoformat(valor)
            st.session_state[k] = valor


# ---------------------------------------------------------------------------
# Acesso à API
# ---------------------------------------------------------------------------
def api_get(path, **params):
    try:
        r = requests.get(f"{API_URL}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state["api_error"] = str(e)
        return None


@st.cache_data(ttl=60)
def fetch_categories():
    return api_get("/categories") or []


@st.cache_data(ttl=30)
def fetch_filtered(categories, date_from, date_to, near):
    """Chama POST /spatial-data/query com categorias, datas e (opcional) raio."""
    body = {
        "categories": list(categories) or None,
        "date_from": datetime.combine(date_from, time.min).isoformat() if date_from else None,
        "date_to": datetime.combine(date_to, time.max).isoformat() if date_to else None,
        "limit": 5000,
    }
    if near:
        lon, lat, raio = near
        body.update({"query_type": "near", "coordinates": [lon, lat], "max_distance": raio})
    try:
        r = requests.post(f"{API_URL}/spatial-data/query", json=body, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.session_state["api_error"] = str(e)
        return []


@st.cache_data(ttl=60)
def fetch_analytics():
    return api_get("/analytics/aggregated") or {}


def filtros_atuais():
    """Filtros serializáveis em JSON (datas em ISO) para salvar no SQLite."""
    f = {k: st.session_state[k] for k in DEFAULTS}
    f["f_date_from"] = f["f_date_from"].isoformat() if f["f_date_from"] else None
    f["f_date_to"] = f["f_date_to"].isoformat() if f["f_date_to"] else None
    return f


# Verifica a API antes de tudo
if api_get("/categories") is None:
    st.error(f"❌ Não foi possível acessar a API em `{API_URL}`. Inicie o backend "
             f"(`uvicorn backend.main:app --reload`).\n\n{st.session_state.get('api_error', '')}")
    st.stop()

categories = fetch_categories()

# ==================== SIDEBAR ====================
with st.sidebar:
    st.title("🏙️ Smart City")
    st.subheader("🔍 Filtros")

    st.multiselect("Categorias", [c["name"] for c in categories], key="f_categories",
                   help="Vazio = todas")

    st.checkbox("Filtrar por raio a partir de um ponto", key="f_use_radius")
    if st.session_state.f_use_radius:
        c1, c2 = st.columns(2)
        c1.number_input("Latitude", key="f_lat", format="%.4f", step=0.001)
        c2.number_input("Longitude", key="f_lon", format="%.4f", step=0.001)
        st.slider("Raio de busca (metros)", 100, 10000, step=100, key="f_radius")

    c1, c2 = st.columns(2)
    c1.date_input("Data inicial", key="f_date_from")
    c2.date_input("Data final", key="f_date_to")

    st.markdown("---")
    st.subheader("💾 Visualizações")
    with st.form("salvar_view", clear_on_submit=True):
        nome_view = st.text_input("Nome da visualização")
        if st.form_submit_button("Salvar visualização atual"):
            if not nome_view.strip():
                st.error("Digite um nome para a visualização")
            else:
                try:
                    r = requests.post(f"{API_URL}/dashboard-views",
                                      json={"name": nome_view.strip(), "filters": filtros_atuais()}, timeout=10)
                    r.raise_for_status()
                    st.success(f"Visualização '{nome_view}' salva!")
                except requests.RequestException as e:
                    st.error(f"Erro ao salvar: {e}")

    views = api_get("/dashboard-views") or []
    if not views:
        st.caption("Nenhuma visualização salva.")
    for view in views:
        c1, c2 = st.columns([4, 1])
        if c1.button(f"📂 {view['name']}", key=f"load_{view['id']}", width="stretch"):
            st.session_state["view_to_load"] = view["filters"]
            st.rerun()
        if c2.button("🗑️", key=f"del_{view['id']}"):
            requests.delete(f"{API_URL}/dashboard-views/{view['id']}", timeout=10)
            st.rerun()

# ==================== DADOS FILTRADOS ====================
near = None
if st.session_state.f_use_radius:
    near = (st.session_state.f_lon, st.session_state.f_lat, st.session_state.f_radius)

dados = fetch_filtered(tuple(st.session_state.f_categories), st.session_state.f_date_from,
                       st.session_state.f_date_to, near)

with st.sidebar:
    st.markdown("---")
    st.metric("Total de itens filtrados", len(dados))
    for cat in st.session_state.f_categories:
        st.metric(cat.title(), sum(1 for d in dados if d["category"] == cat))

# ==================== MAIN ====================
st.title("📊 Dashboard de Cidade Inteligente")
st.caption("MongoDB (GeoJSON + índice 2dsphere) para os dados espaciais · SQLite para categorias, "
           "visualizações salvas e auditoria.")

tab1, tab2, tab3 = st.tabs(["🗺️ Mapa Interativo", "📈 Analytics", "🍔 Restaurantes"])

with tab1:
    if dados:
        centro = (st.session_state.f_lat, st.session_state.f_lon) if near else CENTRO_PADRAO
        render_map(dados, categories, centro=centro, raio=near[2] if near else None)
    else:
        st.info("Nenhum dado encontrado com os filtros selecionados. Rodou `python scripts/seed_data.py`?")

with tab2:
    if dados:
        render_analytics(dados, fetch_analytics())
    else:
        st.info("Nenhum dado disponível para análise.")

with tab3:
    render_restaurants(API_URL)
