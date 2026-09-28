"""
f1_data_collector.py
====================
Exercício Prático 01 — Coletor de Dados da OpenF1 para MongoDB.

Coleta dados da API REST OpenF1 (https://api.openf1.org/v1) e grava no MongoDB
(banco `openf1_data`), nas collections:

    /sessions -> sessions   (chave única: session_key)
    /drivers  -> drivers    (chave única: session_key + driver_number)
    /laps     -> laps       (chave única: session_key + driver_number + lap_number)

Toda gravação usa update_one(..., upsert=True). Por isso o script é
idempotente: pode ser executado quantas vezes quiser sem duplicar documentos.

Uso:
    python f1_data_collector.py                 # usa SESSION_KEYS do .env (padrão 9157)
    python f1_data_collector.py 9157 9165       # coleta uma ou mais sessões informadas

OBSERVAÇÃO sobre a sessão de demonstração:
    O enunciado cita session_key=9159 / meeting_key=1219 como "GP da Itália 2023
    (Monza)". Na API OpenF1 atual, 9159 é o Treino Livre 2 do GP de Singapura
    (meeting 1219). A CORRIDA de Monza 2023 é session_key=9157 (meeting_key=1218),
    que é o valor padrão abaixo. Para usar exatamente o valor do enunciado,
    defina SESSION_KEYS=9159 no arquivo .env.
"""

import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, UpdateOne
from pymongo.database import Database
from pymongo.errors import BulkWriteError, PyMongoError

# ---------------------------------------------------------------------------
# Configuração (tudo configurável via .env — nada "hardcoded" no meio do código)
# ---------------------------------------------------------------------------
load_dotenv()

MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "openf1_data")
OPENF1_BASE_URL: str = os.getenv("OPENF1_BASE_URL", "https://api.openf1.org/v1").rstrip("/")
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
# Uma ou mais sessões separadas por vírgula. 9157 = Corrida do GP da Itália 2023 (Monza).
SESSION_KEYS: List[int] = [
    int(s) for s in os.getenv("SESSION_KEYS", "9157").split(",") if s.strip()
]

# Mapeamento endpoint -> (collection, chaves únicas)
COLLECTIONS_CONFIG: Dict[str, Dict[str, Any]] = {
    "sessions": {"collection": "sessions", "unique_keys": ["session_key"]},
    "drivers": {"collection": "drivers", "unique_keys": ["session_key", "driver_number"]},
    "laps": {"collection": "laps", "unique_keys": ["session_key", "driver_number", "lap_number"]},
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("f1_collector")


# ---------------------------------------------------------------------------
# 1. Conexão com MongoDB
# ---------------------------------------------------------------------------
_db_cache: Optional[Database] = None


def get_database(uri: str = MONGO_URI, db_name: str = MONGO_DB_NAME) -> Database:
    """
    Lê a string de conexão (MONGO_URI do .env), abre o cliente MongoDB,
    valida a conexão com um 'ping' e devolve o objeto `db`.

    A conexão é reaproveitada (cache) nas chamadas seguintes.
    Também cria índices únicos que reforçam, no próprio banco, a regra de
    "sem duplicatas" (além do upsert feito no código).
    """
    global _db_cache
    if _db_cache is not None:
        return _db_cache
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except PyMongoError as exc:
        log.error("Falha ao conectar no MongoDB (%s): %s", uri, exc)
        raise SystemExit(1)

    db = client[db_name]
    log.info("Conectado ao MongoDB — banco '%s'", db_name)

    for cfg in COLLECTIONS_CONFIG.values():
        keys = [(k, ASCENDING) for k in cfg["unique_keys"]]
        index_name = "uq_" + "_".join(cfg["unique_keys"])
        try:
            if index_name not in db[cfg["collection"]].index_information():
                db[cfg["collection"]].create_index(keys, unique=True, name=index_name)
        except PyMongoError as exc:  # índice pode já existir com outro nome
            log.warning("Não foi possível criar índice em %s: %s", cfg["collection"], exc)
    _db_cache = db
    return db


# ---------------------------------------------------------------------------
# 2. Busca de dados da API
# ---------------------------------------------------------------------------
def fetch_data(endpoint: str, params: Optional[dict] = None) -> list:
    """
    Faz um GET em {OPENF1_BASE_URL}/{endpoint} com os parâmetros informados
    e retorna a lista de resultados (a OpenF1 sempre responde com uma lista JSON).

    - Tenta até MAX_RETRIES vezes em caso de erro de rede, HTTP 429 (limite de
      requisições) ou 5xx, com espera crescente entre as tentativas.
    - Em erro definitivo, registra no log e devolve lista vazia, para o fluxo
      principal decidir o que fazer.
    """
    url = f"{OPENF1_BASE_URL}/{endpoint.strip('/')}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params or {}, timeout=REQUEST_TIMEOUT)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            if response.status_code == 404:  # OpenF1 responde 404 quando não há dados
                log.warning("Nenhum dado em %s com %s", endpoint, params)
                return []
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):  # respostas de erro vêm como objeto
                log.warning("Resposta inesperada de %s: %s", endpoint, data)
                return []
            log.info("GET /%s %s -> %d registros", endpoint, params, len(data))
            return data
        except (requests.RequestException, ValueError) as exc:
            wait = 2 ** attempt
            log.warning("Tentativa %d/%d falhou em /%s: %s", attempt, MAX_RETRIES, endpoint, exc)
            if attempt < MAX_RETRIES:
                time.sleep(wait)
    log.error("Desistindo de /%s após %d tentativas.", endpoint, MAX_RETRIES)
    return []


# ---------------------------------------------------------------------------
# 3. Armazenamento em MongoDB
# ---------------------------------------------------------------------------
def save_to_collection(data: list, collection_name: str, unique_keys: list,
                       db: Optional[Database] = None) -> dict:
    """
    Insere ou atualiza cada documento de `data` na collection indicada,
    usando os campos de `unique_keys` como filtro do update_one(upsert=True).

    As operações são enviadas em lote (bulk_write de UpdateOne), que é
    equivalente a chamar update_one(..., upsert=True) documento a documento,
    porém muito mais rápido para as milhares de voltas de uma corrida.

    `db` é opcional: se não for informado, usa a conexão de get_database().
    Retorna um resumo com a quantidade de inseridos / atualizados / ignorados.
    """
    db = db if db is not None else get_database()
    summary = {"inserted": 0, "updated": 0, "skipped": 0}
    if not data:
        log.info("[%s] nada para gravar.", collection_name)
        return summary

    operations = []
    for doc in data:
        # Documentos sem alguma das chaves únicas são ignorados (evita chave nula)
        if any(doc.get(k) is None for k in unique_keys):
            summary["skipped"] += 1
            continue
        filtro = {k: doc[k] for k in unique_keys}
        operations.append(UpdateOne(filtro, {"$set": doc}, upsert=True))

    if not operations:
        return summary

    try:
        result = db[collection_name].bulk_write(operations, ordered=False)
        summary["inserted"] = result.upserted_count
        summary["updated"] = result.modified_count
    except BulkWriteError as exc:
        log.error("[%s] erro parcial na gravação: %s", collection_name, exc.details.get("writeErrors", [])[:3])
    except PyMongoError as exc:
        log.error("[%s] erro no MongoDB: %s", collection_name, exc)

    log.info(
        "[%s] inseridos=%d atualizados=%d ignorados=%d (total na collection: %d)",
        collection_name, summary["inserted"], summary["updated"], summary["skipped"],
        db[collection_name].count_documents({}),
    )
    return summary


# ---------------------------------------------------------------------------
# 4. Execução principal
# ---------------------------------------------------------------------------
def collect_session(session_key: int) -> None:
    """Fluxo completo de uma sessão: sessions -> drivers -> laps."""
    params = {"session_key": session_key}

    # 4.1 Dados da sessão
    sessions = fetch_data("sessions", params)
    if not sessions:
        log.error("Sessão %s não encontrada na API. Pulando.", session_key)
        return
    s = sessions[0]
    log.info(
        "Sessão %s: %s — %s (%s) %s",
        session_key, s.get("session_name"), s.get("location"), s.get("country_name"), s.get("year"),
    )
    cfg = COLLECTIONS_CONFIG["sessions"]
    save_to_collection(sessions, cfg["collection"], cfg["unique_keys"])

    # 4.2 Pilotos da sessão
    drivers = fetch_data("drivers", params)
    cfg = COLLECTIONS_CONFIG["drivers"]
    save_to_collection(drivers, cfg["collection"], cfg["unique_keys"])

    # 4.3 Voltas da sessão
    laps = fetch_data("laps", params)
    cfg = COLLECTIONS_CONFIG["laps"]
    save_to_collection(laps, cfg["collection"], cfg["unique_keys"])


def main() -> None:
    session_keys = [int(a) for a in sys.argv[1:]] or SESSION_KEYS
    log.info("=== Coletor OpenF1 -> MongoDB | sessões: %s ===", session_keys)
    get_database()  # conecta (e falha cedo, se o MongoDB estiver fora)
    for key in session_keys:
        collect_session(key)
    log.info("=== Coleta finalizada ===")


if __name__ == "__main__":
    main()
