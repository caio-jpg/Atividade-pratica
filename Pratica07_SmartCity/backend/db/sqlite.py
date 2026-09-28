"""Conexão com o SQLite (metadados, visualizações salvas e auditoria)."""

import os
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    icon = Column(String(50))
    color = Column(String(20))


class DashboardView(Base):
    __tablename__ = "dashboard_views"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    filters = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    action = Column(String(50), nullable=False)
    details = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SQLiteConnection:
    def __init__(self):
        self.engine = None
        self.SessionLocal = None

    def connect(self) -> bool:
        try:
            db_path = os.getenv("SQLITE_DB_PATH", "data/smart_city.db")
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            self.engine = create_engine(
                f"sqlite:///{db_path}", echo=False,
                connect_args={"check_same_thread": False},  # FastAPI usa várias threads
            )
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine,
                                             expire_on_commit=False)
            print(f"✅ SQLite conectado ({db_path})")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"❌ Erro ao conectar no SQLite: {e}")
            return False

    def get_session(self):
        if self.SessionLocal is None:
            self.connect()
        return self.SessionLocal()

    @contextmanager
    def session_scope(self):
        """Abre uma sessão, faz commit/rollback e SEMPRE fecha (evita vazamento)."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Instância global
sqlite_conn = SQLiteConnection()
