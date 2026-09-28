"""
db_utils.py — Camada de acesso ao MongoDB do OpenF1 Data Explorer.

Toda a lógica de conexão e de consultas fica aqui; o streamlit_app.py só
chama estas funções. Lê exclusivamente dados já existentes no banco
`openf1_data` (populado pelo f1_data_collector.py) — ingestão está fora do escopo.

Collections usadas: sessions, drivers, laps.
"""

import os
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "openf1_data")


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------
def get_mongo_client(uri: str = MONGO_URI) -> MongoClient:
    """Cria o cliente e valida a conexão (lança exceção se o banco estiver fora)."""
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


def get_db(client: MongoClient) -> Database:
    return client[MONGO_DB_NAME]


# ---------------------------------------------------------------------------
# Consultas — sessions
# ---------------------------------------------------------------------------
def get_available_years(db: Database) -> List[int]:
    """Anos distintos presentes na collection sessions (mais recente primeiro)."""
    return sorted((int(y) for y in db.sessions.distinct("year") if y is not None), reverse=True)


def get_sessions_by_year(db: Database, year: int, session_name: Optional[str] = None) -> List[Dict]:
    """Sessões de um ano (opcionalmente só 'Race'), ordenadas pela data."""
    query = {"year": int(year)}
    if session_name:
        query["session_name"] = session_name
    projection = {"_id": 0, "session_key": 1, "session_name": 1, "session_type": 1, "location": 1,
                  "country_name": 1, "circuit_short_name": 1, "date_start": 1, "meeting_key": 1, "year": 1}
    return list(db.sessions.find(query, projection).sort("date_start", 1))


def get_session_details(db: Database, session_key: int) -> Optional[Dict]:
    return db.sessions.find_one({"session_key": int(session_key)}, {"_id": 0})


# ---------------------------------------------------------------------------
# Consultas — drivers
# ---------------------------------------------------------------------------
def get_drivers_from_session(db: Database, session_key: int) -> List[Dict]:
    """Pilotos da sessão, ordenados por equipe e número."""
    projection = {"_id": 0, "driver_number": 1, "full_name": 1, "broadcast_name": 1,
                  "name_acronym": 1, "team_name": 1, "team_colour": 1}
    return list(db.drivers.find({"session_key": int(session_key)}, projection)
                .sort([("team_name", 1), ("driver_number", 1)]))


# ---------------------------------------------------------------------------
# Consultas — laps
# ---------------------------------------------------------------------------
def get_laps_for_drivers(db: Database, session_key: int, driver_numbers: List[int]) -> pd.DataFrame:
    """Voltas dos pilotos selecionados em um DataFrame."""
    query = {"session_key": int(session_key), "driver_number": {"$in": [int(n) for n in driver_numbers]}}
    projection = {"_id": 0, "driver_number": 1, "lap_number": 1, "lap_duration": 1, "is_pit_out_lap": 1,
                  "duration_sector_1": 1, "duration_sector_2": 1, "duration_sector_3": 1,
                  "st_speed": 1, "date_start": 1}
    df = pd.DataFrame(list(db.laps.find(query, projection).sort([("driver_number", 1), ("lap_number", 1)])))
    return df


# ---------------------------------------------------------------------------
# Validação da ingestão (público-alvo: engenheiros de dados)
# ---------------------------------------------------------------------------
def get_ingestion_stats(db: Database, session_key: int) -> Dict:
    """Contagens e verificação de duplicatas das voltas de uma sessão."""
    sk = int(session_key)
    dup = list(db.laps.aggregate([
        {"$match": {"session_key": sk}},
        {"$group": {"_id": {"d": "$driver_number", "l": "$lap_number"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$count": "duplicadas"},
    ]))
    return {
        "pilotos": db.drivers.count_documents({"session_key": sk}),
        "voltas": db.laps.count_documents({"session_key": sk}),
        "voltas_sem_tempo": db.laps.count_documents({"session_key": sk, "lap_duration": None}),
        "duplicadas": dup[0]["duplicadas"] if dup else 0,
    }
