"""
Gera restaurantes fictícios (Faker pt_BR) em data/restaurantes.json.

    python scripts/gerar_restaurantes.py                         # igual ao original: coordenadas
                                                                 # aleatórias no mundo todo
    python scripts/gerar_restaurantes.py --centro -23.5505 -46.6333 --raio-km 15
                                                                 # coordenadas ao redor de São Paulo
"""
import argparse
import json
import math
import os
import random
from datetime import datetime, timezone
from faker import Faker

fake = Faker(['pt_BR'])

# Listas de apoio para variação dos dados
TYPES = [
    "Chicken", "Meat", "Fast Food", "Sandwiches", 
    "Burgers", "Grilled", "Oriental", "Pizza", 
    "Japonesa", "Italiana", "Mexicana", "Doces & Bolos"
]

TITLES_BASE = [
    "Burger King", "KFC", "Food Circles", "Dinware Dines Out",
    "Windmills", "Sabor Express", "Cantina Bella", "Pizza Corner",
    "Sushi House", "Taco Shack", "Churrascaria Primo", "Bistro Urban"
]

images = [
    "http://res.cloudinary.com/simpleview/image/upload/v1438123960/clients/grandrapids/file_bcf11a47-7451-464f-8c4d-c9d3e85e9146.png",
    "http://vignette1.wikia.nocookie.net/ridiculoushist/images/b/b8/KFC_logo.png",
    "http://blogs.delawareonline.com/secondhelpings/files/2011/09/DDO-logo.png",
    "http://www.windmills-cafe.com/default/assets/File/Windmills-rest&cater-vector.png",
    "http://img.zanda.com/item/96060060000053/1024x768/Burger_King_Logo.png"
]

def ponto_aleatorio(centro, raio_km):
    """Sorteia [lon, lat] uniformemente num círculo de raio_km ao redor de centro=(lat, lon)."""
    if centro is None:
        return [float(fake.longitude()), float(fake.latitude())]
    lat0, lon0 = centro
    r = raio_km * math.sqrt(random.random())
    ang = random.uniform(0, 2 * math.pi)
    dlat = (r * math.cos(ang)) / 111.32
    dlon = (r * math.sin(ang)) / (111.32 * math.cos(math.radians(lat0)))
    return [round(lon0 + dlon, 6), round(lat0 + dlat, 6)]


def generate_restaurants(count=2050, centro=None, raio_km=15, saida="data/restaurantes.json"):
    restaurants = []
    
    for i in range(1, count + 1):
        title = f"{random.choice(TITLES_BASE)} {fake.city_suffix()}"
        slug = title.lower().replace(" ", "")
        
        doc = {
            "_id": f"res{i}",
            "title": title,
            "image": random.choice(images),
            "minCharge": f"{random.randint(5, 30)}.00 LE",
            "deliveryFee": round(random.uniform(0.0, 15.0), 2),
            "rating": round(random.uniform(1.0, 10.0), 1),
            "titlMC": f"{slug}MenuCat",
            "url_menucat": f"https://gist.github.com/omar94hamza/{fake.md5()}/raw/{fake.sha1()}/{slug}.json",
            "type": random.sample(TYPES, k=random.randint(1, 3)),
            "isOpen": random.choice([True, False]),
            "phone": fake.phone_number(),
            "reviewsCount": random.randint(10, 500),
            "address": {
                "street": fake.street_address(),
                "neighborhood": fake.bairro(),
                "city": fake.city(),
                "state": fake.state_abbr(),
                "zipCode": fake.postcode(),
                "location": {
                    "type": "Point",
                    "coordinates": ponto_aleatorio(centro, raio_km)
                }
            },
            "createdAt": {"$date": datetime.now(timezone.utc).isoformat()}
        }
        restaurants.append(doc)

    # Exporta no formato JSON array
    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(restaurants, f, ensure_ascii=False, indent=2)

    print(f"Sucesso! {count} documentos gerados em '{saida}'.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quantidade", type=int, default=2050)
    ap.add_argument("--centro", type=float, nargs=2, metavar=("LAT", "LON"))
    ap.add_argument("--raio-km", type=float, default=15)
    ap.add_argument("--saida", default="data/restaurantes.json")
    a = ap.parse_args()
    generate_restaurants(a.quantidade, tuple(a.centro) if a.centro else None, a.raio_km, a.saida)