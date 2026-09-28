"""
streamlit_app.py — OpenF1 Data Explorer com Persistência Poliglota (Prática 05).

  • MongoDB (openf1_data)  : leitura dos dados brutos de sessões, pilotos e voltas
  • SQLite (analysis_reports.db) : gravação e leitura dos resumos de análise (race_analysis)

Executar:  streamlit run streamlit_app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo.errors import PyMongoError

import db_utils

st.set_page_config(page_title="OpenF1 Data Explorer", page_icon="🏎️", layout="wide")


# ---------------------------------------------------------------------------
# Conexões e consultas com cache
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Conectando ao MongoDB...")
def conectar():
    return db_utils.get_mongo_client()


try:
    DB = db_utils.get_db(conectar())
except PyMongoError as exc:
    st.error(f"❌ Não foi possível conectar ao MongoDB. Verifique o MONGO_URI no arquivo .env.\n\n{exc}")
    st.stop()

db_utils.init_sqlite()  # cria analysis_reports.db / race_analysis se não existirem


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
    return (d.get("full_name") or d.get("broadcast_name") or str(d["driver_number"])).title()


# ---------------------------------------------------------------------------
# Cabeçalho e sidebar
# ---------------------------------------------------------------------------
st.title("🏎️ OpenF1 Data Explorer")
st.caption("Persistência poliglota: **MongoDB** para os dados brutos de corrida · "
           "**SQLite** para os resumos de análise.")

with st.sidebar:
    st.header("Filtros da sessão")
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
    mapa_sessoes = {rotulo_sessao(s): s for s in lista_sessoes}
    rotulo = st.selectbox("Selecione a Corrida", list(mapa_sessoes))
    sessao_sel = mapa_sessoes[rotulo]
    session_key = sessao_sel["session_key"]
    st.caption(f"session_key = `{session_key}`")

aba_analise, aba_historico = st.tabs(["📊 Análise da Sessão (MongoDB)", "📜 Histórico de Análises (SQLite)"])


# ===========================================================================
# ABA 1 — Leitura no MongoDB + geração do resumo (escrita no SQLite)
# ===========================================================================
def render_analise():
    sessao = db_utils.get_session_details(DB, session_key) or {}
    st.subheader(f"📍 {sessao.get('location', '')} {sessao.get('year', '')} — {sessao.get('session_name', '')}")
    c1, c2, c3 = st.columns(3)
    c1.metric("País", sessao.get("country_name", "N/A"))
    c2.metric("Circuito", sessao.get("circuit_short_name", "N/A"))
    c3.metric("Data", str(sessao.get("date_start", "N/A"))[:10])

    lista_pilotos = pilotos(session_key)
    if not lista_pilotos:
        st.warning("Nenhum piloto encontrado para esta sessão na collection `drivers`.")
        return
    info_piloto = {d["driver_number"]: d for d in lista_pilotos}
    opcoes = {f"{nome_piloto(d)} #{d['driver_number']} ({d.get('team_name') or 'N/A'})": d["driver_number"]
              for d in lista_pilotos}
    escolhidos = st.multiselect("Selecione os pilotos para comparar:", list(opcoes), default=list(opcoes)[:2])
    if not escolhidos:
        st.info("Selecione ao menos um piloto.")
        return

    numeros = tuple(opcoes[n] for n in escolhidos)
    df = voltas(session_key, numeros)
    if df.empty:
        st.warning("Não há voltas registradas para os pilotos selecionados.")
        return
    df["piloto"] = df["driver_number"].map(lambda n: nome_piloto(info_piloto[n]))

    # --- Gráfico ------------------------------------------------------------
    st.subheader("📈 Duração de cada volta")
    fig = px.line(
        df.dropna(subset=["lap_duration"]).sort_values(["piloto", "lap_number"]),
        x="lap_number", y="lap_duration", color="piloto", markers=True,
        labels={"lap_number": "Volta", "lap_duration": "Duração da volta (s)", "piloto": "Piloto"},
    )
    fig.update_layout(hovermode="x unified", height=480)
    st.plotly_chart(fig, width="stretch")

    # --- Dados brutos -------------------------------------------------------
    with st.expander("📋 Ver dados brutos das voltas (MongoDB)"):
        colunas = [c for c in ["piloto", "driver_number", "lap_number", "lap_duration", "is_pit_out_lap",
                               "duration_sector_1", "duration_sector_2", "duration_sector_3"] if c in df]
        st.dataframe(df[colunas].sort_values(["piloto", "lap_number"]), width="stretch", hide_index=True)

    # --- Resumo -> SQLite ---------------------------------------------------
    st.divider()
    st.subheader("💾 Resumo da análise → SQLite")
    st.caption("Calcula métricas agregadas sobre os dados brutos do MongoDB e grava o resultado "
               "na tabela `race_analysis` do banco relacional `analysis_reports.db`.")

    if st.button("🚀 Gerar Resumo da Análise", type="primary"):
        metricas = db_utils.compute_driver_metrics(df)
        linhas = []
        for m in metricas.to_dict("records"):
            d = info_piloto[m["driver_number"]]
            linhas.append({
                **m,
                "session_key": int(session_key),
                "session_name": rotulo,
                "driver_name": nome_piloto(d),
                "team_name": d.get("team_name"),
            })
        try:
            n = db_utils.save_analysis(linhas)
            st.session_state["ultimo_resumo"] = pd.DataFrame(linhas)
            st.success(f"✅ {n} registro(s) gravado(s) na tabela race_analysis (SQLite).")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Erro ao gravar no SQLite: {exc}")

    if "ultimo_resumo" in st.session_state:
        r = st.session_state["ultimo_resumo"]
        st.dataframe(
            r[["driver_name", "team_name", "fastest_lap", "fastest_lap_number", "average_lap_time",
               "total_laps", "consistency_std_dev", "pit_stops"]].rename(columns={
                "driver_name": "Piloto", "team_name": "Equipe", "fastest_lap": "Volta mais rápida (s)",
                "fastest_lap_number": "Nº da volta", "average_lap_time": "Tempo médio (s)",
                "total_laps": "Voltas", "consistency_std_dev": "Consistência (desvio padrão, s)",
                "pit_stops": "Paradas"}),
            width="stretch", hide_index=True,
        )
        st.caption("Consistência = desvio padrão dos tempos, sem a volta 1 e sem as voltas de entrada/saída dos boxes. "
                   "Quanto menor, mais constante o ritmo.")


with aba_analise:
    render_analise()


# ===========================================================================
# ABA 2 — Histórico lido do SQLite
# ===========================================================================
with aba_historico:
    st.subheader("📜 Histórico de Análises")
    st.caption("Leitura direta da tabela `race_analysis` no SQLite — os dados persistem entre execuções.")
    hist = db_utils.load_analysis_history()
    if hist.empty:
        st.info("Nenhuma análise salva ainda. Gere um resumo na aba de análise.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Registros salvos", len(hist))
        m2.metric("Sessões analisadas", hist["session_key"].nunique())
        m3.metric("Pilotos analisados", hist["driver_name"].nunique())

        filtro = st.multiselect("Filtrar por sessão:", sorted(hist["session_name"].unique()))
        vis = hist[hist["session_name"].isin(filtro)] if filtro else hist
        st.dataframe(vis, width="stretch", hide_index=True)
        st.download_button("⬇️ Exportar histórico (CSV)", vis.to_csv(index=False).encode("utf-8"),
                           file_name="race_analysis.csv", mime="text/csv")

        with st.expander("🗑️ Remover registros"):
            ids = st.multiselect("IDs para remover:", vis["id"].tolist())
            if st.button("Remover selecionados", disabled=not ids):
                db_utils.delete_analysis(ids)
                st.rerun()
