# Exercício Prático 01 — Coletor OpenF1 → MongoDB

Coleta `/sessions`, `/drivers` e `/laps` da API OpenF1 e grava no banco `openf1_data`
(collections `sessions`, `drivers`, `laps`) usando `update_one(..., upsert=True)`
(enviado em lote com `bulk_write`) → **idempotente**, sem duplicatas.

| Collection | Chave única |
|---|---|
| sessions | `session_key` |
| drivers | `session_key + driver_number` |
| laps | `session_key + driver_number + lap_number` |

Além do upsert, o script cria **índices únicos** com essas chaves (proteção extra no banco).

## Como executar

```bash
pip install -r requirements.txt
cp .env.example .env          # ajuste MONGO_URI se usar Atlas
python f1_data_collector.py              # coleta as sessões de SESSION_KEYS (.env)
python f1_data_collector.py 9157 9165    # ou informe as sessões na linha de comando
```

Rode duas vezes: na segunda execução o log mostra `inseridos=0` e a contagem total não muda.

## ⚠️ Sobre a sessão de demonstração

O enunciado diz `session_key=9159 / meeting_key=1219` = "GP da Itália 2023 (Monza)".
Na API OpenF1 atual:

- `9159` = **Practice 2 do GP de Singapura** (meeting 1219)
- `9157` = **Race do GP da Itália 2023, Monza** (meeting 1218) ← padrão usado aqui

Se o professor quiser exatamente 9159, basta `SESSION_KEYS=9159` no `.env`.

## Estrutura do código

| Função | Responsabilidade |
|---|---|
| `get_database()` | Lê `MONGO_URI` do `.env`, faz `ping`, cria índices únicos e retorna `db` |
| `fetch_data(endpoint, params) -> list` | GET na API com timeout, retry (429/5xx) e tratamento de erro |
| `save_to_collection(data, collection_name, unique_keys)` | Upsert por chave única, devolve resumo inseridos/atualizados |
| `collect_session()` / `main()` | Fluxo: sessão → pilotos → voltas |

Consultas úteis para validar no `mongosh`:

```js
use openf1_data
db.sessions.find({ session_key: 9157 })
db.drivers.find({ session_key: 9157 }, { full_name: 1, team_name: 1, driver_number: 1 })
db.laps.countDocuments({ session_key: 9157 })
// prova de que não há duplicatas:
db.laps.aggregate([{ $group: { _id: { s: "$session_key", d: "$driver_number", l: "$lap_number" }, n: { $sum: 1 } } }, { $match: { n: { $gt: 1 } } }])
```
