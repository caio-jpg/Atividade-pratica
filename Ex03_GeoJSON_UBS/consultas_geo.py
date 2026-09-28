"""
consultas_geo.py
================
Demonstra consultas geoespaciais sobre a collection de UBS gravada pelo
ubs_geo_etl.py (índice 2dsphere no campo `geometry`).

Uso:
    python consultas_geo.py                          # ponto padrão: Praça da Sé (SP)
    python consultas_geo.py -23.5505 -46.6333 3      # latitude longitude raio_km
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "dados_abertos_geo")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "ubs")
RAIO_TERRA_KM = 6378.1


def nome(doc):
    p = doc.get("properties", {})
    return p.get("nom_estab") or p.get("nome") or p.get("cod_cnes")


def main():
    lat = float(sys.argv[1]) if len(sys.argv) > 1 else -23.5505
    lon = float(sys.argv[2]) if len(sys.argv) > 2 else -46.6333
    raio_km = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    ponto = {"type": "Point", "coordinates": [lon, lat]}  # GeoJSON: [longitude, latitude]

    col = MongoClient(MONGO_URI)[MONGO_DB_NAME][MONGO_COLLECTION]
    print(f"Collection '{MONGO_COLLECTION}': {col.count_documents({})} UBS")
    print(f"Ponto de referência: lat={lat}, lon={lon} | raio={raio_km} km\n")

    # 1) $near — UBS mais próximas, ordenadas por distância, até o raio informado
    print("1) $near — 5 UBS mais próximas dentro do raio:")
    for d in col.find({"geometry": {"$near": {"$geometry": ponto, "$maxDistance": raio_km * 1000}}}).limit(5):
        print("   -", nome(d), "|", d["properties"].get("dsc_endereco", ""))

    # 2) $geoNear (aggregation) — mesma ideia, mas devolvendo a distância calculada
    print("\n2) $geoNear — distância exata em metros:")
    pipeline = [
        {"$geoNear": {"near": ponto, "distanceField": "distancia_m", "maxDistance": raio_km * 1000,
                      "spherical": True}},
        {"$limit": 5},
        {"$project": {"_id": 0, "nome": "$properties.nom_estab", "distancia_m": {"$round": ["$distancia_m", 0]}}},
    ]
    try:
        for d in col.aggregate(pipeline):
            print(f"   - {d.get('nome')}: {d['distancia_m']:.0f} m")
    except Exception:  # $round só existe no MongoDB >= 4.2
        pipeline[-1] = {"$project": {"_id": 0, "nome": "$properties.nom_estab", "distancia_m": 1}}
        for d in col.aggregate(pipeline):
            print(f"   - {d.get('nome')}: {d['distancia_m']:.0f} m")

    # 3) $geoWithin + $centerSphere — contagem dentro de um círculo (raio em radianos)
    qtd = col.count_documents({"geometry": {"$geoWithin": {
        "$centerSphere": [[lon, lat], raio_km / RAIO_TERRA_KM]}}})
    print(f"\n3) $geoWithin/$centerSphere — {qtd} UBS num raio de {raio_km} km")

    # 4) $geoWithin + Polygon — UBS dentro de um retângulo (~0,1° ao redor do ponto)
    d = 0.05
    poligono = {"type": "Polygon", "coordinates": [[
        [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]
    ]]}
    qtd = col.count_documents({"geometry": {"$geoWithin": {"$geometry": poligono}}})
    print(f"4) $geoWithin/Polygon — {qtd} UBS no retângulo de ~11 km x 11 km")

    # 5) Agregação comum — top 5 cidades com mais UBS
    print("\n5) Top 5 cidades com mais UBS:")
    for c in col.aggregate([
        {"$group": {"_id": "$properties.dsc_cidade", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}}, {"$limit": 5},
    ]):
        print(f"   - {c['_id']}: {c['total']}")


if __name__ == "__main__":
    main()
