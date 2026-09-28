import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import random
from backend.db.mongodb import mongo_conn
from backend.db.sqlite import sqlite_conn, Category

def seed_categories():
    """Popular categorias no SQLite"""
    print("📝 Criando categorias...")
    
    categories = [
        Category(name="alagamento", description="Pontos de alagamento", icon="water", color="#1f77b4"),
        Category(name="iluminacao", description="Postes de iluminação", icon="lightbulb", color="#ff7f0e"),
        Category(name="risco", description="Zonas de risco", icon="warning", color="#d62728"),
        Category(name="parque", description="Parques e áreas verdes", icon="tree", color="#2ca02c"),
        Category(name="hospital", description="Hospitais e postos de saúde", icon="hospital", color="#9467bd")
    ]
    
    novas = 0
    with sqlite_conn.session_scope() as session:
        for cat in categories:
            if not session.query(Category).filter(Category.name == cat.name).first():
                session.add(cat)
                novas += 1
    print(f"✅ {novas} categorias novas ({len(categories) - novas} já existiam)")

def seed_spatial_data():
    """Popular dados geoespaciais no MongoDB"""
    print("📍 Criando dados geoespaciais...")
    collection = mongo_conn.get_collection("spatial_data")
    
    # Limpar dados existentes
    collection.delete_many({})
    
    # Coordenadas base (São Paulo - exemplo)
    base_lat = -23.5505
    base_lon = -46.6333
    
    data_points = []
    
    # Pontos de alagamento (polígonos)
    for i in range(15):
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        
        # Criar polígono pequeno (quadrado de ~100m)
        size = 0.001
        polygon_coords = [
            [lon - size, lat - size],
            [lon + size, lat - size],
            [lon + size, lat + size],
            [lon - size, lat + size],
            [lon - size, lat - size]
        ]
        
        data_points.append({
            "name": f"Alagamento {i+1}",
            "category": "alagamento",
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_coords]
            },
            "properties": {
                "severity": random.choice(["baixa", "média", "alta", "crítica"]),
                "last_occurrence": (datetime.utcnow() - timedelta(days=random.randint(1, 365))).isoformat()
            },
            "timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 365))
        })
    
    # Postes de iluminação (pontos)
    for i in range(50):
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        
        data_points.append({
            "name": f"Poste {i+1}",
            "category": "iluminacao",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "status": random.choice(["funcionando", "quebrado", "manutenção"]),
                "power": random.choice(["LED", "Vapor Sódio", "Fluorescente"])
            },
            "timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 365))
        })
    
    # Zonas de risco (polígonos)
    for i in range(8):
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        
        # Polígono maior
        size = 0.003
        polygon_coords = [
            [lon - size, lat - size],
            [lon + size, lat - size],
            [lon + size * 0.8, lat + size],
            [lon - size * 0.8, lat + size],
            [lon - size, lat - size]
        ]
        
        data_points.append({
            "name": f"Zona de Risco {i+1}",
            "category": "risco",
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_coords]
            },
            "properties": {
                "risk_level": random.choice(["baixo", "médio", "alto"]),
                "type": random.choice(["deslizamento", "inundação", "desmoronamento"])
            },
            "timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 365))
        })
    
    # Parques (polígonos)
    for i in range(5):
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        
        size = 0.005
        polygon_coords = [
            [lon - size, lat - size],
            [lon + size, lat - size],
            [lon + size, lat + size],
            [lon - size, lat + size],
            [lon - size, lat - size]
        ]
        
        data_points.append({
            "name": f"Parque {i+1}",
            "category": "parque",
            "geometry": {
                "type": "Polygon",
                "coordinates": [polygon_coords]
            },
            "properties": {
                "area_hectares": round(random.uniform(1, 10), 2),
                "facilities": random.sample(["playground", "pista", "banheiros", "estacionamento"], 2)
            },
            "timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 365))
        })
    
    # Hospitais (pontos)
    for i in range(10):
        lat = base_lat + random.uniform(-0.05, 0.05)
        lon = base_lon + random.uniform(-0.05, 0.05)
        
        data_points.append({
            "name": f"Hospital {i+1}",
            "category": "hospital",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "type": random.choice(["público", "privado", "misto"]),
                "beds": random.randint(50, 500),
                "emergency": random.choice([True, False])
            },
            "timestamp": datetime.utcnow() - timedelta(days=random.randint(1, 365))
        })
    
    # Inserir no MongoDB
    result = collection.insert_many(data_points)
    print(f"✅ {len(result.inserted_ids)} pontos geoespaciais criados")

def main():
    print("🌱 Iniciando seed de dados...")
    
    # Conectar bancos
    if not mongo_conn.connect():
        sys.exit(1)
    mongo_conn.create_geospatial_index("spatial_data", "geometry")
    sqlite_conn.connect()
    
    # Popular dados
    seed_categories()
    seed_spatial_data()
    
    print("✅ Seed concluído com sucesso!")

if __name__ == "__main__":
    main()