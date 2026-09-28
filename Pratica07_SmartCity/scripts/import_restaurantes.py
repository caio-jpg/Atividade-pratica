"""
import_restaurantes.py
======================
Importa data/restaurantes.json (gerado por gerar_restaurantes.py) para a
collection `restaurantes` do MongoDB e cria os índices, incluindo o 2dsphere
em `address.location` (GeoJSON Point [longitude, latitude]).

Tratamentos aplicados:
  - "createdAt": {"$date": "..."} (formato Extended JSON) -> datetime real
  - "minCharge": "12.00 LE" -> também salvo como número em "minChargeNum"
  - coordenadas validadas (lon -180..180, lat -90..90); inválidas são descartadas
  - upsert pelo _id ("res1", "res2", ...) -> pode rodar várias vezes sem duplicar

Uso (na pasta smart_city):
    python scripts/import_restaurantes.py
    python scripts/import_restaurantes.py --arquivo outro.json --limpar
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, UpdateOne  # noqa: E402

from backend.db.mongodb import mongo_conn  # noqa: E402

COLLECTION = "restaurantes"
ARQUIVO_PADRAO = os.getenv("RESTAURANTES_JSON", os.path.join("data", "restaurantes.json"))


def converter(doc: dict):
    """Normaliza um documento do JSON. Retorna None se a localização for inválida."""
    created = doc.get("createdAt")
    if isinstance(created, dict) and "$date" in created:
        doc["createdAt"] = datetime.fromisoformat(created["$date"].replace("Z", "+00:00"))

    try:
        doc["minChargeNum"] = float(str(doc.get("minCharge", "")).split()[0])
    except (ValueError, IndexError):
        doc["minChargeNum"] = None

    loc = (doc.get("address") or {}).get("location") or {}
    coords = loc.get("coordinates") or []
    if loc.get("type") != "Point" or len(coords) != 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    doc["address"]["location"] = {"type": "Point", "coordinates": [lon, lat]}
    return doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arquivo", default=ARQUIVO_PADRAO)
    parser.add_argument("--limpar", action="store_true", help="apaga a collection antes de importar")
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        print(f"❌ Arquivo não encontrado: {args.arquivo}")
        sys.exit(1)
    with open(args.arquivo, encoding="utf-8") as f:
        dados = json.load(f)
    print(f"📄 {len(dados)} documentos lidos de {args.arquivo}")

    if not mongo_conn.connect():
        sys.exit(1)
    col = mongo_conn.get_collection(COLLECTION)
    if args.limpar:
        col.drop()
        print("🧹 Collection apagada")

    ops, invalidos = [], 0
    for doc in dados:
        doc = converter(doc)
        if doc is None:
            invalidos += 1
            continue
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))

    res = col.bulk_write(ops, ordered=False) if ops else None
    col.create_index([("address.location", GEOSPHERE)], name="location_2dsphere")
    col.create_index([("type", ASCENDING)], name="type")
    col.create_index([("rating", DESCENDING)], name="rating")
    col.create_index([("address.state", ASCENDING)], name="state")

    print(f"✅ Inseridos: {res.upserted_count if res else 0} | Atualizados: {res.modified_count if res else 0} "
          f"| Inválidos: {invalidos} | Total na collection: {col.count_documents({})}")
    print("✅ Índices:", ", ".join(col.index_information()))


if __name__ == "__main__":
    main()
