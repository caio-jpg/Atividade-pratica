"""Conexão com o MongoDB (dados geoespaciais em GeoJSON)."""

import os

from pymongo import GEOSPHERE, MongoClient
from pymongo.errors import PyMongoError

try:  # carrega o .env na execução local (no Docker as variáveis vêm do compose)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


class MongoDBConnection:
    def __init__(self):
        self.client = None
        self.db = None

    def connect(self) -> bool:
        try:
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
            db_name = os.getenv("MONGO_DB_NAME", "geo_analytics")
            self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command("ping")  # valida a conexão de verdade
            self.db = self.client[db_name]
            print(f"✅ MongoDB conectado ({db_name})")
            return True
        except PyMongoError as e:
            print(f"❌ Erro ao conectar no MongoDB: {e}")
            return False

    def get_collection(self, collection_name):
        if self.db is None:
            self.connect()
        return self.db[collection_name]

    def create_geospatial_index(self, collection_name, field="geometry"):
        """Cria índice 2dsphere (necessário para $near/$geoNear)."""
        collection = self.get_collection(collection_name)
        collection.create_index([(field, GEOSPHERE)])
        print(f"✅ Índice 2dsphere em {collection_name}.{field}")

    def close(self):
        if self.client:
            self.client.close()


# Instância global
mongo_conn = MongoDBConnection()
