# Exercício 03 — Georreferenciamento com MongoDB e GeoJSON (UBS)

Solução em Python que **extrai** o cadastro de Unidades Básicas de Saúde (UBS) do portal
dados.gov.br, **trata** os dados com pandas/geopandas e **persiste** cada UBS como um
*Feature* GeoJSON no MongoDB, com índice **2dsphere**.

## Passo 1: encontrar os dados abertos

1. Acesse <https://dados.gov.br> e busque **"Unidades Básicas de Saúde"** ou **"UBS CSV"**.
2. No conjunto de dados, abra a aba **Recursos** e escolha o arquivo **CSV**. Ele tem as colunas
   `vlr_latitude`, `vlr_longitude`, `cod_cnes`, `nom_estab`, `dsc_endereco`, `dsc_bairro`, `dsc_cidade`…
3. Copie o link de download para `UBS_CSV_URL` no `.env`. O padrão já aponta para
   `repositorio.dados.gov.br/.../ubs.csv`. Se o portal bloquear o download automático, baixe
   pelo navegador e rode com `--arquivo`.

## Passo 2: configurar o ambiente

- **MongoDB:** Community Server local (`mongodb://localhost:27017`) ou MongoDB Atlas. Com Docker:
  `docker run -d -p 27017:27017 --name mongo mongo:7`
- **Python:**
  ```bash
  pip install -r requirements.txt
  cp .env.example .env
  ```

## Passo 3: executar

```bash
python ubs_geo_etl.py                      # baixa, trata, grava no MongoDB e exporta dados/ubs.geojson
python ubs_geo_etl.py --arquivo ubs.csv    # usando um CSV baixado manualmente
python consultas_geo.py -23.5505 -46.6333 2   # consultas geoespaciais (lat, lon, raio em km)
```

## O que o tratamento faz (`tratar_dados`)

| Etapa | Detalhe |
|---|---|
| Codificação | Tenta UTF-8 e depois Latin-1; o separador (`,` ou `;`) é detectado automaticamente |
| Colunas | Nomes normalizados (minúsculas, sem acento); lat/lon localizadas automaticamente |
| Tipos | Coordenadas convertidas para `float`, aceitando vírgula decimal |
| Limpeza | Remove coordenadas vazias, `0,0` e pontos fora do retângulo do Brasil |
| Duplicatas | Removidas pelo `cod_cnes` |
| Geo | `gpd.points_from_xy` → GeoDataFrame em **EPSG:4326 (WGS84)**, o sistema exigido pelo `2dsphere` |

## Formato gravado no MongoDB

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [-46.6333, -23.5505] },
  "properties": { "cod_cnes": "2077485", "nom_estab": "UBS ...", "dsc_cidade": "São Paulo", "...": "..." }
}
```

> A ordem das coordenadas no GeoJSON é **[longitude, latitude]**.

A carga usa `UpdateOne(..., upsert=True)` com a chave `properties.cod_cnes`, então pode ser
reexecutada sem duplicar dados. Índices criados: `geometry` (2dsphere), `properties.cod_cnes`
e `properties.dsc_cidade`.

## Consultas geoespaciais (`consultas_geo.py`)

| Nº | Operador | Pergunta respondida |
|---|---|---|
| 1 | `$near` | Quais são as UBS mais próximas de mim, até X km? |
| 2 | `$geoNear` (aggregation) | Idem, com a distância em metros |
| 3 | `$geoWithin` + `$centerSphere` | Quantas UBS existem num raio de X km? |
| 4 | `$geoWithin` + `Polygon` | Quantas UBS existem dentro de uma área? |
| 5 | `$group` | Quais cidades têm mais UBS? |

Equivalente no `mongosh`:

```js
use dados_abertos_geo
db.ubs.find({ geometry: { $near: { $geometry: { type: "Point", coordinates: [-46.6333, -23.5505] }, $maxDistance: 2000 } } }).limit(5)
```
