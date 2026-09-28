"""
db_utils.py — Acesso a dados do OpenF1 Data Explorer (Persistência Poliglota).

Toda a lógica de conexão e de consultas fica aqui; o streamlit_app.py só
chama estas funções.

  MongoDB (leitura)  -> openf1_data: sessions, drivers, laps
                        dados brutos, volumosos e semiestruturados (populados
                        pelo f1_data_collector.py).
  SQLite  (escrita)  -> analysis_reports.db, tabela race_analysis
                        resumos estruturados e agregados gerados pela análise.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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


# ===========================================================================
# SQLite (SQLAlchemy) — persistência dos resumos de análise
# ===========================================================================
SQLITE_URL = os.getenv("SQLITE_URL", "sqlite:///analysis_reports.db")

Base = declarative_base()


class RaceAnalysis(Base):
    """Tabela race_analysis: uma linha por piloto em cada análise gerada."""
    __tablename__ = "race_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(Integer, nullable=False, index=True)
    session_name = Column(String(255), nullable=False)
    driver_number = Column(Integer, nullable=False)
    driver_name = Column(String(255), nullable=False)
    team_name = Column(String(255))
    fastest_lap = Column(Float)
    fastest_lap_number = Column(Integer)
    average_lap_time = Column(Float)
    total_laps = Column(Integer, nullable=False)
    consistency_std_dev = Column(Float)
    analysis_timestamp = Column(DateTime, nullable=False, default=datetime.now)


_engine = create_engine(SQLITE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_sqlite() -> None:
    """Cria o arquivo analysis_reports.db e a tabela race_analysis, se não existirem."""
    Base.metadata.create_all(_engine)


def compute_driver_metrics(laps: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula as métricas agregadas por piloto a partir das voltas (vindas do MongoDB):

      - fastest_lap          : menor lap_duration
      - average_lap_time     : média de lap_duration (voltas com tempo registrado)
      - total_laps           : nº de voltas completadas (com tempo registrado)
      - consistency_std_dev  : desvio padrão de lap_duration EXCLUINDO voltas de
                               saída dos boxes (is_pit_out_lap = True), voltas de
                               entrada nos boxes (a volta imediatamente anterior a
                               uma volta de saída) e a volta 1 (largada).
    """
    registros = []
    for numero, grupo in laps.groupby("driver_number"):
        g = grupo.sort_values("lap_number")
        validas = g.dropna(subset=["lap_duration"])
        validas = validas[validas["lap_duration"] > 0]

        out_laps = set(g.loc[g.get("is_pit_out_lap", False) == True, "lap_number"])  # noqa: E712
        in_laps = {n - 1 for n in out_laps}
        excluir = out_laps | in_laps | {1}
        ritmo = validas[~validas["lap_number"].isin(excluir)]["lap_duration"]

        if validas.empty:
            fastest = avg = None
            fastest_n = None
        else:
            idx = validas["lap_duration"].idxmin()
            fastest = float(validas.loc[idx, "lap_duration"])
            fastest_n = int(validas.loc[idx, "lap_number"])
            avg = float(validas["lap_duration"].mean())

        registros.append({
            "driver_number": int(numero),
            "fastest_lap": round(fastest, 3) if fastest is not None else None,
            "fastest_lap_number": fastest_n,
            "average_lap_time": round(avg, 3) if avg is not None else None,
            "total_laps": int(len(validas)),
            "consistency_std_dev": round(float(ritmo.std()), 3) if len(ritmo) > 1 else None,
            "pit_stops": len(out_laps),
        })
    return pd.DataFrame(registros)


def save_analysis(rows: List[Dict]) -> int:
    """Grava as linhas de resumo na tabela race_analysis. Retorna quantas foram salvas."""
    init_sqlite()
    agora = datetime.now()
    campos = {c.name for c in RaceAnalysis.__table__.columns} - {"id"}
    with SessionLocal() as s:
        s.add_all([RaceAnalysis(**{k: v for k, v in r.items() if k in campos}, analysis_timestamp=agora)
                   for r in rows])
        s.commit()
    return len(rows)


def load_analysis_history() -> pd.DataFrame:
    """Lê todo o histórico da tabela race_analysis (mais recente primeiro)."""
    init_sqlite()
    with _engine.connect() as conn:
        return pd.read_sql("SELECT * FROM race_analysis ORDER BY analysis_timestamp DESC, id", conn)


def delete_analysis(ids: List[int]) -> int:
    """Remove análises do histórico pelos ids."""
    init_sqlite()
    with SessionLocal() as s:
        n = s.query(RaceAnalysis).filter(RaceAnalysis.id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        s.commit()
    return n
