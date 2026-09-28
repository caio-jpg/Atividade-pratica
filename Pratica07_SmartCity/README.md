# 🏙️ Smart City Dashboard (Prática 07)

Dashboard analítico e geoespacial com **banco duplo**:

| Banco | Guarda | Recursos usados |
|---|---|---|
| **MongoDB** `geo_analytics` | `spatial_data` (pontos/polígonos GeoJSON) e `restaurantes` (2.050 docs do `restaurantes.json`) | índice `2dsphere`, `$geoNear`, `$geoWithin`, `$geoIntersects`, aggregation |
| **SQLite** `data/smart_city.db` | `categories`, `dashboard_views` (filtros salvos), `audit_logs` | SQLAlchemy |

Componentes: **FastAPI** (backend) · **Streamlit + Folium + Plotly** (dashboard) · Docker Compose.

## 🚀 Opção 1 — Execução local

```bash
cd Pratica07_SmartCity
pip install -r requirements.txt
cp .env.example .env
```

**1. Iniciar o MongoDB** (qualquer um):

```bash
docker run -d --name smart_city_mongo -p 27017:27017 mongo:7.0
# ou: mongod --dbpath ./mongo-data
```

**2. Popular os bancos**

```bash
python scripts/seed_data.py            # categorias (SQLite) + 88 itens geoespaciais em São Paulo (MongoDB)
python scripts/import_restaurantes.py  # importa data/restaurantes.json -> collection restaurantes
```

**3. Iniciar o backend**

```bash
uvicorn backend.main:app --reload --port 8000
```

**4. Iniciar o dashboard** (em outro terminal, na mesma pasta)

```bash
streamlit run dashboard/app.py
```

**Acessar:** Dashboard em <http://localhost:8501> · API Docs (Swagger) em <http://localhost:8000/docs>

## 🐳 Opção 2 — Docker Compose

```bash
docker compose up -d --build
docker compose exec backend python scripts/seed_data.py
docker compose exec backend python scripts/import_restaurantes.py
```

Dashboard em <http://localhost:8501> · API em <http://localhost:8000>

## 📊 Uso do dashboard

- **Filtros (sidebar):**
  - Categorias.
  - Raio de busca em metros a partir de um ponto (lat/lon). Usa `$geoNear` e desenha o círculo no mapa.
  - Intervalo de datas (filtra o campo `timestamp`).
- **🗺️ Mapa interativo:** pontos e polígonos coloridos pela cor da categoria (vinda do SQLite). Clique num item para ver os detalhes.
- **📈 Analytics:** distribuição por categoria, top categorias, evolução mensal, tabela e download em CSV.
- **🍔 Restaurantes:**
  - Busca por proximidade com distância em km e filtros de tipo, aberto/fechado e nota mínima.
  - Mapa e tabela dos resultados.
  - Gráficos por tipo de cozinha (com a nota média) e por UF.
- **💾 Salvar visualizações:** configure os filtros, digite um nome e clique em *Salvar*. Os filtros vão para o SQLite. Clique em 📂 para recarregar a visualização ou em 🗑️ para apagar.

## 🔌 API Endpoints (`/api/v1`)

```bash
# ---- MongoDB: dados geoespaciais ----
GET    /spatial-data?category=hospital&limit=100
POST   /spatial-data                         # cria item GeoJSON
GET    /spatial-data/{id}
DELETE /spatial-data/{id}
POST   /spatial-data/query                   # consulta combinada (exemplos abaixo)
GET    /analytics/aggregated                 # contagem por categoria e por mês

# ---- MongoDB: restaurantes ----
GET    /restaurantes?tipo=Pizza&aberto=true&rating_min=8&estado=SP&limit=20
GET    /restaurantes/near?lon=-46.63&lat=-23.55&max_km=500&tipo=Burgers&limit=10   # $geoNear
GET    /restaurantes/raio?lon=-46.63&lat=-23.55&raio_km=1000                        # $geoWithin/$centerSphere
GET    /restaurantes/stats                                                          # aggregation

# ---- SQLite ----
GET    /categories                POST /categories
GET    /dashboard-views           POST /dashboard-views      DELETE /dashboard-views/{id}
GET    /audit-logs?limit=50
```

Exemplos de `POST /spatial-data/query`:

```bash
# Hospitais e postes num raio de 3 km da Praça da Sé
curl -X POST localhost:8000/api/v1/spatial-data/query -H "Content-Type: application/json" \
  -d '{"categories":["hospital","iluminacao"],"query_type":"near","coordinates":[-46.6333,-23.5505],"max_distance":3000}'

# Tudo que está DENTRO de um polígono
curl -X POST localhost:8000/api/v1/spatial-data/query -H "Content-Type: application/json" \
  -d '{"query_type":"within","geometry":{"type":"Polygon","coordinates":[[[-46.7,-23.6],[-46.6,-23.6],[-46.6,-23.5],[-46.7,-23.5],[-46.7,-23.6]]]}}'

# Zonas que CRUZAM uma linha (ex.: trajeto de uma avenida)
curl -X POST localhost:8000/api/v1/spatial-data/query -H "Content-Type: application/json" \
  -d '{"query_type":"intersects","geometry":{"type":"LineString","coordinates":[[-46.70,-23.55],[-46.58,-23.55]]}}'
```

Consultas equivalentes no `mongosh`:

```js
use geo_analytics
db.restaurantes.find({ "address.location": { $near: { $geometry: { type: "Point", coordinates: [-46.63, -23.55] }, $maxDistance: 500000 } } }).limit(5)
db.restaurantes.aggregate([{ $unwind: "$type" }, { $group: { _id: "$type", total: { $sum: 1 }, nota: { $avg: "$rating" } } }, { $sort: { total: -1 } }])
```

## 📁 Estrutura do projeto

```
Pratica07_SmartCity/
├── backend/
│   ├── main.py              # FastAPI + ciclo de vida (conexões e índices 2dsphere)
│   ├── api/routes.py        # rotas MongoDB, restaurantes e SQLite
│   ├── db/mongodb.py        # conexão MongoDB
│   ├── db/sqlite.py         # modelos SQLAlchemy + session_scope
│   └── models/              # schemas Pydantic
├── dashboard/
│   ├── app.py               # Streamlit
│   └── components/          # map_view.py, analytics.py, restaurants.py
├── scripts/
│   ├── seed_data.py            # dados de exemplo (São Paulo)
│   ├── import_restaurantes.py  # restaurantes.json -> MongoDB
│   └── gerar_restaurantes.py   # gerador Faker (agora com --centro/--raio-km)
├── data/restaurantes.json
├── docker-compose.yml  Dockerfile.backend  Dockerfile.dashboard
└── requirements.txt  .env.example
```

## 🔧 O que foi corrigido no projeto original

| Problema | Correção |
|---|---|
| Arquivos `requeriments.txt`, `Dockerfile.*.txt` e `docker-compose.yml.yaml` não eram achados pelo Docker | Renomeados para os nomes padrão |
| Dashboard quebrava com `ModuleNotFoundError: dashboard` ao rodar `streamlit run dashboard/app.py` | Import ajustado |
| A pasta `dashboard/pages/` virava páginas extras (vazias) no menu do Streamlit | Renomeada para `components/` |
| `API_URL` fixo no código, ignorando a variável do Docker Compose | Passa a ler `os.getenv("API_URL")` |
| Filtros de **raio** e **data** apareciam na tela mas não eram aplicados | Agora usam `POST /spatial-data/query` (`$geoNear` + `timestamp`) |
| Filtro padrão "últimos 30 dias" escondia quase todos os dados do seed (datas espalhadas em 365 dias) | Padrão passou a ser 365 dias |
| **Salvar visualização** travava: `date` não é serializável em JSON e `st.session_state.view_name = ''` gera exceção | Datas salvas em ISO; salvamento feito dentro de `st.form` |
| **Carregar visualização** não atualizava os widgets | Os filtros são aplicados antes de os widgets serem criados |
| Rotas SQLite retornavam objetos ORM sem `from_attributes` (erro de validação no Pydantic v2) | `ConfigDict(from_attributes=True)` |
| Sessões SQLite nunca eram fechadas | `session_scope()` com commit, rollback e close |
| Categoria duplicada gerava erro 500 | Agora retorna 409 |
| `.dict()` (depreciado no Pydantic v2) | Trocado por `.model_dump(mode="json")` |
| Legenda do mapa sempre com "🟢" | Mostra a cor real de cada categoria |
| Versões fixas antigas (ex.: `pandas==2.2.0`) não instalam em Python ≥ 3.13 | Versões mínimas (`>=`) |
| Não havia integração com `restaurantes.json` | Script de importação, índice 2dsphere, 4 rotas e aba no dashboard |

## ⚠️ Sobre os dados de restaurantes

O `gerar_restaurantes.py` original usa `fake.latitude()` e `fake.longitude()`, que sorteiam pontos
**no mundo inteiro**, mesmo com endereços brasileiros. Por isso a busca por proximidade precisa de
raios grandes (centenas ou milhares de km). Para gerar restaurantes perto de São Paulo, coerentes
com o mapa da cidade:

```bash
python scripts/gerar_restaurantes.py --centro -23.5505 -46.6333 --raio-km 15
python scripts/import_restaurantes.py --limpar
```
