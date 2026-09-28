"""
ubs_geo_etl.py
==============
Exercício 03 — Georreferenciamento com MongoDB e GeoJSON.

Pipeline ETL:
  1. EXTRAÇÃO   : baixa o CSV de Unidades Básicas de Saúde (UBS) do portal de
                  dados abertos do Governo Federal (dados.gov.br) com `requests`.
  2. TRATAMENTO : lê com `pandas`, identifica as colunas de latitude/longitude,
                  corrige tipos, remove coordenadas inválidas/fora do Brasil e
                  duplicatas, e converte para GeoDataFrame (`geopandas`, EPSG:4326).
  3. CARGA      : grava cada UBS como um *Feature* GeoJSON no MongoDB (`pymongo`),
                  com upsert pelo código CNES (idempotente) e índice `2dsphere`.
  Também exporta o resultado em um arquivo `.geojson`.

Uso:
    python ubs_geo_etl.py                    # baixa da URL configurada no .env
    python ubs_geo_etl.py --arquivo ubs.csv  # usa um CSV já baixado manualmente

Se a URL mudar (o próprio enunciado avisa), procure "UBS CSV" em dados.gov.br,
copie o link do recurso e coloque em UBS_CSV_URL no .env — ou baixe o arquivo
pelo navegador e use --arquivo.
"""

import argparse
import io
import json
import logging
import os
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests
from dotenv import load_dotenv
from pymongo import GEOSPHERE, ASCENDING, MongoClient, UpdateOne
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
load_dotenv()

UBS_CSV_URL = os.getenv(
    "UBS_CSV_URL",
    "https://repositorio.dados.gov.br/saude/unidades-saude/unidade-basica-saude/ubs.csv",
)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "dados_abertos_geo")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "ubs")
PASTA_DADOS = os.getenv("PASTA_DADOS", "dados")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
BATCH_SIZE = 1000

# Retângulo envolvente do território brasileiro (validação das coordenadas)
BRASIL_LAT = (-34.0, 5.5)
BRASIL_LON = (-74.5, -28.5)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ubs_etl")


# ---------------------------------------------------------------------------
# 1. EXTRAÇÃO
# ---------------------------------------------------------------------------
def baixar_csv(url: str, destino: str) -> str:
    """Baixa o CSV em streaming (arquivo grande) e salva localmente."""
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    log.info("Baixando %s ...", url)
    with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT,
                      headers={"User-Agent": "Mozilla/5.0 (ETL academico)"}) as resp:
        resp.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    log.info("Arquivo salvo em %s (%.1f MB)", destino, os.path.getsize(destino) / 1e6)
    return destino


def ler_csv(caminho: str) -> pd.DataFrame:
    """
    Lê o CSV tentando as codificações mais comuns dos portais do governo
    (UTF-8 e Latin-1) e detectando o separador automaticamente (',' ou ';').
    Todas as colunas entram como texto; os tipos são tratados depois.
    """
    with open(caminho, "rb") as f:
        bruto = f.read()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    primeira_linha = texto.splitlines()[0]
    sep = ";" if primeira_linha.count(";") > primeira_linha.count(",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, keep_default_na=False)
    log.info("CSV lido: %d linhas, %d colunas (encoding=%s, sep='%s')",
             len(df), len(df.columns), encoding, sep)
    return df


# ---------------------------------------------------------------------------
# 2. TRATAMENTO
# ---------------------------------------------------------------------------
def _normalizar_nome(col: str) -> str:
    """'Nome do Estabelecimento' -> 'nome_do_estabelecimento' (sem acentos)."""
    s = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode()
    return "_".join(s.strip().lower().replace("-", " ").split())


def _achar_coluna(colunas, candidatos) -> Optional[str]:
    for c in colunas:
        if any(c == cand or c.endswith(cand) or c.startswith(cand) for cand in candidatos):
            return c
    return None


def _para_float(serie: pd.Series) -> pd.Series:
    """Converte texto para número aceitando vírgula decimal ('-23,55' -> -23.55)."""
    return pd.to_numeric(serie.str.strip().str.replace(",", ".", regex=False), errors="coerce")


def tratar_dados(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Limpa o DataFrame e devolve um GeoDataFrame de pontos em WGS84."""
    df = df.rename(columns={c: _normalizar_nome(c) for c in df.columns})

    col_lat = _achar_coluna(df.columns, ["vlr_latitude", "latitude", "lat"])
    col_lon = _achar_coluna(df.columns, ["vlr_longitude", "longitude", "lon", "lng"])
    if not col_lat or not col_lon:
        raise ValueError(f"Colunas de latitude/longitude não encontradas: {list(df.columns)}")
    log.info("Coordenadas: latitude='%s', longitude='%s'", col_lat, col_lon)

    # Limpeza de texto: remove espaços extras
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    df["latitude"] = _para_float(df[col_lat])
    df["longitude"] = _para_float(df[col_lon])
    total = len(df)

    # Remove coordenadas vazias, zeradas ou fora do Brasil
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]
    df = df[df["latitude"].between(*BRASIL_LAT) & df["longitude"].between(*BRASIL_LON)]

    # Remove duplicatas pelo código CNES (identificador oficial do estabelecimento)
    col_cnes = _achar_coluna(df.columns, ["cod_cnes", "cnes", "co_cnes"])
    if col_cnes:
        df = df.drop_duplicates(subset=[col_cnes])
        df = df.rename(columns={col_cnes: "cod_cnes"})
    else:
        df = df.drop_duplicates(subset=["latitude", "longitude"])
    log.info("Tratamento: %d válidas de %d linhas (%d descartadas)", len(df), total, total - len(df))

    gdf = gpd.GeoDataFrame(
        df.drop(columns=[c for c in (col_lat, col_lon) if c not in ("latitude", "longitude")]),
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",  # WGS84 — o sistema exigido pelo índice 2dsphere
    )
    return gdf


def gdf_para_features(gdf: gpd.GeoDataFrame) -> list:
    """
    Converte o GeoDataFrame em uma lista de Features GeoJSON:
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {...}}
    """
    geojson = json.loads(gdf.to_json(drop_id=True))
    return geojson["features"]


# ---------------------------------------------------------------------------
# 3. CARGA
# ---------------------------------------------------------------------------
def conectar_mongodb():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    log.info("Conectado ao MongoDB (%s.%s)", MONGO_DB_NAME, MONGO_COLLECTION)
    return client[MONGO_DB_NAME]


def gravar_mongodb(db, features: list) -> None:
    """Upsert de cada Feature (chave: properties.cod_cnes) e criação dos índices."""
    col = db[MONGO_COLLECTION]
    agora = datetime.now(timezone.utc)
    ops, inseridos, atualizados = [], 0, 0

    for feat in features:
        feat["properties"]["atualizado_em"] = agora
        cnes = feat["properties"].get("cod_cnes")
        filtro = {"properties.cod_cnes": cnes} if cnes else {"geometry": feat["geometry"]}
        ops.append(UpdateOne(filtro, {"$set": feat}, upsert=True))
        if len(ops) >= BATCH_SIZE:
            r = col.bulk_write(ops, ordered=False)
            inseridos += r.upserted_count
            atualizados += r.modified_count
            ops = []
    if ops:
        r = col.bulk_write(ops, ordered=False)
        inseridos += r.upserted_count
        atualizados += r.modified_count

    # Índice geoespacial: obrigatório para $near / $geoNear, acelera $geoWithin
    col.create_index([("geometry", GEOSPHERE)], name="geometry_2dsphere")
    col.create_index([("properties.cod_cnes", ASCENDING)], name="cod_cnes")
    col.create_index([("properties.dsc_cidade", ASCENDING)], name="cidade")
    log.info("MongoDB: %d inseridos, %d atualizados. Total na collection: %d",
             inseridos, atualizados, col.count_documents({}))


def exportar_geojson(features: list, caminho: str) -> None:
    """Salva um FeatureCollection em disco (útil para abrir no QGIS/geojson.io)."""
    fc = {"type": "FeatureCollection", "features": features}
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, default=str)
    log.info("GeoJSON exportado: %s", caminho)


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ETL de UBS (dados.gov.br) -> GeoJSON -> MongoDB")
    parser.add_argument("--arquivo", help="CSV local (pula o download)")
    parser.add_argument("--url", default=UBS_CSV_URL, help="URL do CSV no portal de dados abertos")
    args = parser.parse_args()

    caminho_csv = args.arquivo
    if not caminho_csv:
        caminho_csv = os.path.join(PASTA_DADOS, "ubs.csv")
        try:
            baixar_csv(args.url, caminho_csv)
        except requests.RequestException as exc:
            if os.path.exists(caminho_csv):
                log.warning("Download falhou (%s). Usando cópia local %s", exc, caminho_csv)
            else:
                log.error("Download falhou: %s. Baixe o CSV manualmente e use --arquivo.", exc)
                sys.exit(1)

    try:
        df = ler_csv(caminho_csv)
        gdf = tratar_dados(df)
        features = gdf_para_features(gdf)
        exportar_geojson(features, os.path.join(PASTA_DADOS, "ubs.geojson"))
        db = conectar_mongodb()
        gravar_mongodb(db, features)
    except (ValueError, PyMongoError) as exc:
        log.error("Falha no ETL: %s", exc)
        sys.exit(1)
    log.info("ETL concluído com sucesso.")


if __name__ == "__main__":
    main()
