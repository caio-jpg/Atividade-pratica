"""
cartola_etl.py
==============
Exercício 2 — Coletar e Armazenar Dados do Cartola FC (ETL em Python).

Extrai dados da API (não oficial) do Cartola FC, transforma e carrega no
MongoDB, banco `cartola_fc_db`, nas collections:

    mercado_rodada_atual  -> status do mercado a cada coleta
    atletas_rodada_atual  -> lista completa de atletas da rodada atual
    clubes_rodada_atual   -> clubes (upsert usando o id do clube como _id)

Pronto para agendamento (cron / Agendador de Tarefas). Exemplo de cron,
a cada 30 minutos:
    */30 * * * * cd /caminho/Ex02_CartolaFC && /usr/bin/python3 cartola_etl.py >> etl.log 2>&1

Observação importante sobre a API:
    Em https://api.cartola.globo.com/atletas/mercado a chave "status" é o
    DICIONÁRIO DE STATUS DOS ATLETAS (2=Dúvida, 7=Provável, ...), e não o status
    do mercado. As informações do mercado mostradas no exemplo do enunciado
    (rodada_atual, status_mercado, fechamento...) vêm do endpoint
    https://api.cartola.globo.com/mercado/status. Por isso o script consulta os
    dois: o primeiro para atletas/clubes e o segundo para o status do mercado.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pymongo.operations import UpdateOne

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cartola_fc_db")
CARTOLA_API_BASE = os.getenv("CARTOLA_API_BASE", "https://api.cartola.globo.com").rstrip("/")
URL_ATLETAS_MERCADO = f"{CARTOLA_API_BASE}/atletas/mercado"
URL_MERCADO_STATUS = f"{CARTOLA_API_BASE}/mercado/status"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

COL_MERCADO = "mercado_rodada_atual"
COL_ATLETAS = "atletas_rodada_atual"
COL_CLUBES = "clubes_rodada_atual"

# A API às vezes recusa requisições sem User-Agent de navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cartola_etl")


# ---------------------------------------------------------------------------
# Módulo de Conexão
# ---------------------------------------------------------------------------
def conectar_mongodb() -> Database:
    """Lê as credenciais do .env, conecta ao MongoDB e retorna o objeto `db`."""
    log.info("Conectando ao MongoDB...")
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")  # força a conexão agora (falha rápido)
    except PyMongoError as exc:
        log.error("Falha ao conectar no MongoDB: %s", exc)
        sys.exit(1)
    log.info("Conectado ao banco '%s'.", MONGO_DB_NAME)
    return client[MONGO_DB_NAME]


# ---------------------------------------------------------------------------
# Módulo de Extração
# ---------------------------------------------------------------------------
def _get_json(url: str) -> Dict[str, Any]:
    """GET com verificação de status code; em falha registra o erro e encerra."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        log.error("Erro HTTP ao acessar %s: %s", url, exc)
    except requests.exceptions.RequestException as exc:
        log.error("Erro de conexão ao acessar %s: %s", url, exc)
    except ValueError as exc:
        log.error("Resposta de %s não é um JSON válido: %s", url, exc)
    log.error("Execução interrompida de forma controlada.")
    sys.exit(1)


def buscar_dados_mercado() -> Dict[str, Any]:
    """
    Faz GET em /atletas/mercado e devolve o JSON decodificado
    (chaves principais: atletas, clubes, posicoes, status).

    Também consulta /mercado/status e anexa o resultado na chave
    "mercado_status" (é dele que saem rodada_atual, status_mercado e fechamento).
    Se só esse segundo endpoint falhar, o ETL continua sem ele.
    """
    log.info("Buscando dados na API: %s", URL_ATLETAS_MERCADO)
    dados = _get_json(URL_ATLETAS_MERCADO)

    try:
        resp = requests.get(URL_MERCADO_STATUS, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        dados["mercado_status"] = resp.json()
    except (requests.exceptions.RequestException, ValueError) as exc:
        log.warning("Não foi possível obter %s (%s). Seguindo sem ele.", URL_MERCADO_STATUS, exc)
        dados["mercado_status"] = None

    log.info(
        "API retornou %d atletas e %d clubes.",
        len(dados.get("atletas") or []), len(dados.get("clubes") or {}),
    )
    return dados


# ---------------------------------------------------------------------------
# Módulo de Transformação e Carga (ETL Core)
# ---------------------------------------------------------------------------
def _agora_iso() -> str:
    """Timestamp UTC no padrão ISO 8601, ex.: 2024-08-14T12:00:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def transformar_clube(clube: Dict[str, Any]) -> Dict[str, Any]:
    """Converte o clube da API para o formato da collection (id do clube vira _id)."""
    return {
        "_id": int(clube["id"]),
        "nome": clube.get("nome"),
        "abreviacao": clube.get("abreviacao"),
        "escudos": clube.get("escudos", {}),
        "nome_fantasia": clube.get("nome_fantasia") or clube.get("nome"),
    }


def transformar_atleta(atleta: Dict[str, Any], timestamp: str,
                       posicoes: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mantém todos os campos do atleta, garante tipos numéricos e acrescenta:
      - timestamp_coleta (ISO 8601)
      - posicao_abreviacao e status_nome (enriquecimento vindo dos dicionários
        'posicoes' e 'status' do próprio JSON, facilita as análises)
    """
    doc = dict(atleta)
    for campo in ("preco_num", "variacao_num", "pontos_num", "media_num"):
        if doc.get(campo) is not None:
            doc[campo] = float(doc[campo])
    doc["scout"] = doc.get("scout") or {}  # atletas sem scout vêm como null
    # a API costuma devolver a foto com "FORMATO" no lugar do tamanho
    if isinstance(doc.get("foto"), str):
        doc["foto"] = doc["foto"].replace("FORMATO", "220x220")
    pos = posicoes.get(str(doc.get("posicao_id")), {})
    st = status.get(str(doc.get("status_id")), {})
    doc["posicao_abreviacao"] = pos.get("abreviacao")
    doc["status_nome"] = st.get("nome")
    doc["timestamp_coleta"] = timestamp
    return doc


def montar_documento_mercado(dados_mercado: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
    """Monta o documento de status do mercado (formato do enunciado)."""
    ms = dados_mercado.get("mercado_status")
    if ms:
        doc = {
            "rodada_atual": ms.get("rodada_atual"),
            "status_mercado": ms.get("status_mercado"),  # 1 = Aberto, 2 = Fechado
            "aviso": ms.get("aviso", ""),
            "fechamento": ms.get("fechamento", {}),
            "temporada": ms.get("temporada"),
            "times_escalados": ms.get("times_escalados"),
        }
    else:
        # Fallback: sem /mercado/status, deduz a rodada pelos atletas e guarda o
        # objeto 'status' do /atletas/mercado, como pede literalmente o enunciado.
        atletas = dados_mercado.get("atletas") or []
        doc = {
            "rodada_atual": atletas[0].get("rodada_id") if atletas else None,
            "status_mercado": None,
            "aviso": "status do mercado indisponível nesta coleta",
            "fechamento": {},
            "status_atletas": dados_mercado.get("status", {}),
        }
    doc["timestamp_coleta"] = timestamp
    return doc


def processar_e_gravar_dados(db: Database, dados_mercado: Dict[str, Any]) -> None:
    """Separa clubes, atletas e status do JSON e grava cada um na sua collection."""
    timestamp = _agora_iso()

    # ---- Clubes: upsert usando o id como _id (sem duplicatas) --------------
    log.info("Gravando dados dos clubes...")
    clubes = dados_mercado.get("clubes") or {}
    operacoes: List[UpdateOne] = []
    for clube in clubes.values():
        doc = transformar_clube(clube)
        operacoes.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))
    if operacoes:
        res = db[COL_CLUBES].bulk_write(operacoes, ordered=False)
        log.info("Clubes: %d inseridos, %d atualizados.", res.upserted_count, res.modified_count)

    # ---- Atletas: limpa e insere a lista completa ---------------------------
    log.info("Gravando dados dos atletas...")
    posicoes = dados_mercado.get("posicoes") or {}
    status = dados_mercado.get("status") or {}
    atletas = [
        transformar_atleta(a, timestamp, posicoes, status)
        for a in (dados_mercado.get("atletas") or [])
    ]
    db[COL_ATLETAS].delete_many({})
    if atletas:
        db[COL_ATLETAS].insert_many(atletas)
        db[COL_ATLETAS].create_index("atleta_id")
        db[COL_ATLETAS].create_index("clube_id")
    log.info("Atletas: %d documentos inseridos.", len(atletas))

    # ---- Status do mercado: mantém apenas o mais recente --------------------
    log.info("Gravando status do mercado...")
    doc_mercado = montar_documento_mercado(dados_mercado, timestamp)
    db[COL_MERCADO].delete_many({})
    db[COL_MERCADO].insert_one(doc_mercado)
    log.info(
        "Mercado: rodada %s, status_mercado=%s.",
        doc_mercado.get("rodada_atual"), doc_mercado.get("status_mercado"),
    )


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("=== Início do ETL Cartola FC ===")
    db = conectar_mongodb()
    dados = buscar_dados_mercado()
    try:
        processar_e_gravar_dados(db, dados)
    except PyMongoError as exc:
        log.error("Erro ao gravar no MongoDB: %s", exc)
        sys.exit(1)
    log.info("Finalizado com sucesso.")
