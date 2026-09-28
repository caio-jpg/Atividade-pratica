"""
streamlit_app.py — OpenF1 Data Explorer (Prática 04).

Interface Streamlit que traduz as seleções do usuário em consultas MongoDB
sobre o banco `openf1_data` (sessions, drivers, laps).

Executar:  streamlit run streamlit_app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo.errors import PyMongoError

import db_utils

st.set_page_config(page_title="OpenF1 Data Explorer", page_icon="🏎️", layout="wide")


# ---------------------------------------------------------------------------
# Conexão (uma vez por processo) e consultas com cache
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Conectando ao MongoDB...")
def conectar():
    return db_utils.get_mongo_client()


try:
    DB = db_utils.get_db(conectar())
except PyMongoError as exc:
    st.error(f"❌ Não foi possível conectar ao MongoDB. Verifique o MONGO_URI no arquivo .env.\n\n{exc}")
    st.stop()


@st.cache_data(ttl=300)
def anos():
    return db_utils.get_available_years(DB)


@st.cache_data(ttl=300)
def sessoes(ano, somente_corridas):
    return db_utils.get_sessions_by_year(DB, ano, "Race" if somente_corridas else None)


@st.cache_data(ttl=300)
def pilotos(session_key):
    return db_utils.get_drivers_from_session(DB, session_key)


@st.cache_data(ttl=300)
def voltas(session_key, numeros):
    return db_utils.get_laps_for_drivers(DB, session_key, list(numeros))


def rotulo_sessao(s):
    data = str(s.get("date_start", ""))[:10]
    return f"{s.get('country_name', '?')} · {s.get('location', '?')} — {s.get('session_name', '')} ({data})"


def nome_piloto(d):
    nome = (d.get("full_name") or d.get("broadcast_name") or str(d["driver_number"])).title()
    return f"{nome} #{d['driver_number']} ({d.get('team_name') or 'Equipe N/A'})"


# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------
st.title("🏎️ OpenF1 Data Explorer")
st.caption("Exploração interativa do banco MongoDB `openf1_data` — sessões, pilotos e voltas.")

# ---------------------------------------------------------------------------
# Sidebar — seleção de contexto
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filtros")
    lista_anos = anos()
    if not lista_anos:
        st.warning("A collection `sessions` está vazia. Rode antes o `f1_data_collector.py`.")
        st.stop()
    ano = st.selectbox("Selecione o Ano", lista_anos)
    somente_corridas = st.toggle("Somente corridas (Race)", value=True)

    lista_sessoes = sessoes(ano, somente_corridas)
    if not lista_sessoes:
        st.warning("Nenhuma sessão encontrada para esse filtro.")
        st.stop()
    mapa_sessoes = {rotulo_sessao(s): s["session_key"] for s in lista_sessoes}
    rotulo = st.selectbox("Selecione a Corrida", list(mapa_sessoes))
    session_key = mapa_sessoes[rotulo]
    st.caption(f"session_key = `{session_key}`")

# ---------------------------------------------------------------------------
# Detalhes da sessão
# ---------------------------------------------------------------------------
sessao = db_utils.get_session_details(DB, session_key) or {}
st.subheader(f"📍 {sessao.get('location', '')} {sessao.get('year', '')} — {sessao.get('session_name', '')}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("País", sessao.get("country_name", "N/A"))
c2.metric("Circuito", sessao.get("circuit_short_name", "N/A"))
c3.metric("Data", str(sessao.get("date_start", "N/A"))[:10])
c4.metric("Tipo", sessao.get("session_type", "N/A"))

with st.expander("🧪 Validação da ingestão (contagens e duplicatas)"):
    stats = db_utils.get_ingestion_stats(DB, session_key)
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Pilotos", stats["pilotos"])
    v2.metric("Voltas", stats["voltas"])
    v3.metric("Voltas sem tempo", stats["voltas_sem_tempo"])
    v4.metric("Voltas duplicadas", stats["duplicadas"])
    if stats["duplicadas"] == 0:
        st.success("Nenhuma duplicata (session_key + driver_number + lap_number).")
    else:
        st.error("Existem voltas duplicadas — verifique o coletor.")

st.divider()

# ---------------------------------------------------------------------------
# Seleção de pilotos
# ---------------------------------------------------------------------------
st.subheader("👥 Comparativo de pilotos")
lista_pilotos = pilotos(session_key)
if not lista_pilotos:
    st.warning("Nenhum piloto encontrado para esta sessão na collection `drivers`.")
    st.stop()

mapa_pilotos = {nome_piloto(d): d["driver_number"] for d in lista_pilotos}
selecionados = st.multiselect("Selecione os pilotos:", list(mapa_pilotos), default=list(mapa_pilotos)[:2])
if not selecionados:
    st.info("Selecione ao menos um piloto.")
    st.stop()

numeros = tuple(mapa_pilotos[n] for n in selecionados)
df = voltas(session_key, numeros)
if df.empty:
    st.warning("Não há voltas registradas para os pilotos selecionados.")
    st.stop()

numero_para_nome = {v: k.split(" #")[0] for k, v in mapa_pilotos.items()}
df["piloto"] = df["driver_number"].map(numero_para_nome)
df_validas = df.dropna(subset=["lap_duration"])

# ---------------------------------------------------------------------------
# Gráfico de desempenho
# ---------------------------------------------------------------------------
st.subheader("📈 Tempo de volta por volta")
fig = px.line(
    df_validas.sort_values(["piloto", "lap_number"]),
    x="lap_number", y="lap_duration", color="piloto", markers=True,
    labels={"lap_number": "Volta", "lap_duration": "Duração da volta (s)", "piloto": "Piloto"},
)
fig.update_layout(hovermode="x unified", height=500)
st.plotly_chart(fig, width="stretch")
st.caption("Picos no gráfico costumam indicar paradas nos boxes, Safety Car ou incidentes.")

# Métricas rápidas por piloto (leitura, sem gravar)
resumo = (df_validas.groupby("piloto")["lap_duration"]
          .agg(volta_mais_rapida="min", media="mean", voltas="count").round(3).reset_index())
st.dataframe(resumo, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Dados brutos
# ---------------------------------------------------------------------------
with st.expander("📋 Ver tabela de dados"):
    colunas = [c for c in ["piloto", "driver_number", "lap_number", "lap_duration", "duration_sector_1",
                           "duration_sector_2", "duration_sector_3", "is_pit_out_lap", "st_speed"] if c in df]
    st.dataframe(df[colunas].sort_values(["piloto", "lap_number"]), width="stretch", hide_index=True)
    st.download_button("⬇️ Baixar CSV", df[colunas].to_csv(index=False).encode("utf-8"),
                       file_name=f"voltas_{session_key}.csv", mime="text/csv")
