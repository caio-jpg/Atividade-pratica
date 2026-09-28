# Exercícios de MongoDB: soluções

Cada pasta tem o código, `requirements.txt`, `.env` / `.env.example` e um `README.md` com os passos para rodar.

| Pasta | Enunciado | Entrega principal |
|---|---|---|
| `Ex01_OpenF1_Coletor` | Exercício Prático 01: OpenF1 → MongoDB | `f1_data_collector.py` (idempotente, upsert por chave única) |
| `Ex02_CartolaFC` | Exercício 2: dados do Cartola FC | `cartola_etl.py` (ETL agendável com cron) |
| `Ex03_GeoJSON_UBS` | Exercício 03: georreferenciamento com GeoJSON | `ubs_geo_etl.py` (dados.gov.br → GeoJSON → 2dsphere) e `consultas_geo.py` |
| `Pratica04_OpenF1_Data_Explorer` | Prática 04: consultas MongoDB com Streamlit | `streamlit_app.py` e `db_utils.py` |
| `Pratica05_Persistencia_Poliglota` | Prática 05: MongoDB + SQLite | Prática 04 + resumo gravado em `analysis_reports.db` e aba de histórico |
| `Pratica07_SmartCity` | Prática 07: Smart City (FastAPI + Streamlit + MongoDB + SQLite) | Projeto corrigido, importação de `restaurantes.json` e consultas geoespaciais |

## Ordem sugerida

1. Suba um MongoDB: `docker run -d -p 27017:27017 --name mongo mongo:7`, ou use o Atlas.
2. Rode o **Ex01**: `python f1_data_collector.py 9157`. Ele popula o banco `openf1_data` usado nas Práticas 04 e 05.
3. Rode as **Práticas 04 e 05**: `streamlit run streamlit_app.py`.
4. **Ex02**, **Ex03** e **Prática 07** são independentes.

## ⚠️ Atenção: `session_key` do enunciado da OpenF1

O enunciado usa `session_key=9159` como "GP da Itália 2023 (Monza)". Na API atual, **9159 é o Treino
Livre 2 de Singapura**. A **corrida de Monza 2023 é `9157`** (meeting 1218), e esse é o padrão usado aqui.
