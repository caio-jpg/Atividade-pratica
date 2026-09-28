# Exercício 2 — ETL do Cartola FC → MongoDB

Script: `cartola_etl.py`. Banco: `cartola_fc_db`.

## Como executar

```bash
pip install -r requirements.txt
cp .env.example .env      # coloque aqui as credenciais do MongoDB
python cartola_etl.py
```

Agendamento (cron, a cada 30 min):

```cron
*/30 * * * * cd /caminho/Ex02_CartolaFC && /usr/bin/python3 cartola_etl.py >> etl.log 2>&1
```

No Windows, use o Agendador de Tarefas apontando para `python.exe cartola_etl.py`.

## Análise da resposta da API (`/atletas/mercado`)

| Chave | Tipo | Conteúdo |
|---|---|---|
| `atletas` | **lista** | Um objeto por atleta: `atleta_id`, `nome`, `apelido`, `foto`, `clube_id`, `posicao_id`, `status_id`, `preco_num`, `variacao_num`, `pontos_num`, `media_num`, `jogos_num`, `rodada_id`, `scout` {DS, SG, G, A...} |
| `clubes` | **objeto** indexado pelo id (`"262": {...}`) | `id`, `nome`, `abreviacao`, `nome_fantasia`, `escudos` {60x60, 45x45, 30x30} |
| `posicoes` | objeto | 1=Goleiro, 2=Lateral, 3=Zagueiro, 4=Meia, 5=Atacante, 6=Técnico |
| `status` | objeto | **Status dos atletas**: 2=Dúvida, 3=Suspenso, 5=Contundido, 6=Nulo, 7=Provável |

⚠️ O `status` desse endpoint **não** é o status do mercado. Os campos do exemplo do enunciado
(`rodada_atual`, `status_mercado`, `fechamento`) vêm de **`/mercado/status`**. Por isso o script
consulta os dois endpoints. Se `/mercado/status` falhar, ele grava um documento de fallback com o
objeto `status` original.

## Funções (conforme o enunciado)

| Função | O que faz |
|---|---|
| `conectar_mongodb()` | Lê o `.env`, faz `ping` e retorna `db` |
| `buscar_dados_mercado()` | GET com `raise_for_status()`; em erro registra no log e encerra com `sys.exit(1)` |
| `processar_e_gravar_dados(db, dados)` | **Clubes:** `UpdateOne(..., upsert=True)` com `_id` = id do clube. **Atletas:** `delete_many({})` + `insert_many()` com `timestamp_coleta`. **Mercado:** limpa e insere o status mais recente |

Transformações extras nos atletas: `posicao_abreviacao` e `status_nome` (vindos dos dicionários
`posicoes`/`status`), `foto` com `FORMATO` trocado por `220x220`, e `scout: null` convertido em `{}`.

## Consultas de exemplo (mongosh)

```js
use cartola_fc_db
db.mercado_rodada_atual.findOne()
// 10 atletas prováveis mais valorizados na rodada
db.atletas_rodada_atual.find({ status_id: 7 }, { apelido: 1, preco_num: 1, variacao_num: 1 }).sort({ variacao_num: -1 }).limit(10)
// média de pontos por clube (join com clubes)
db.atletas_rodada_atual.aggregate([
  { $match: { jogos_num: { $gt: 0 } } },
  { $group: { _id: "$clube_id", media: { $avg: "$media_num" }, atletas: { $sum: 1 } } },
  { $lookup: { from: "clubes_rodada_atual", localField: "_id", foreignField: "_id", as: "clube" } },
  { $project: { clube: { $first: "$clube.nome" }, media: { $round: ["$media", 2] }, atletas: 1 } },
  { $sort: { media: -1 } }
])
```
