# Prática 05 — Persistência Poliglota (MongoDB + SQLite)

Mesma aplicação da Prática 04, agora com um segundo banco:

| Banco | Uso | Por quê |
|---|---|---|
| **MongoDB** `openf1_data` | Leitura de `sessions`, `drivers`, `laps` | Dados brutos, numerosos e semiestruturados |
| **SQLite** `analysis_reports.db` | Escrita/leitura da tabela `race_analysis` | Resumos estruturados, pequenos e relacionais |

## Como executar

```bash
pip install -r requirements.txt
python ../Ex01_OpenF1_Coletor/f1_data_collector.py 9157    # popula o MongoDB
streamlit run streamlit_app.py
```

O arquivo `analysis_reports.db` e a tabela `race_analysis` são criados automaticamente
(SQLAlchemy `create_all`).

## Fluxo do usuário

1. Ano **2023** → corrida **Italy · Monza — Race**.
2. Pilotos **Charles Leclerc** e **Carlos Sainz**: aparecem o gráfico e os dados brutos, lidos do MongoDB.
3. **"Gerar Resumo da Análise"** calcula as métricas e grava uma linha por piloto no SQLite.
4. A aba **"Histórico de Análises"** lê a tabela `race_analysis` e mostra tudo num `st.dataframe`, com filtro por sessão, exportação CSV e remoção de registros.

## Métricas (`db_utils.compute_driver_metrics`)

| Coluna | Cálculo |
|---|---|
| `fastest_lap` | `min(lap_duration)` (e `fastest_lap_number`) |
| `average_lap_time` | `mean(lap_duration)` das voltas com tempo |
| `total_laps` | voltas completadas (com tempo registrado) |
| `consistency_std_dev` | desvio padrão **sem** a volta 1, as voltas de saída dos boxes (`is_pit_out_lap = true`) e as voltas de entrada (a anterior a cada saída) |

## Tabela `race_analysis`

`id, session_key, session_name, driver_number, driver_name, team_name, fastest_lap,
fastest_lap_number, average_lap_time, total_laps, consistency_std_dev, analysis_timestamp`

```bash
sqlite3 analysis_reports.db "SELECT driver_name, fastest_lap, consistency_std_dev FROM race_analysis ORDER BY analysis_timestamp DESC;"
```

## Correções em relação ao código do .zip

- **Nomes dos pilotos:** o histórico guardava só o número (`driver_name="16"`). Agora o nome vem da collection `drivers`, junto com o número e a equipe.
- **`seed_db.py` removido:** ele apagava as collections e gravava dados fictícios, inclusive com `session_key 9159` marcado como "Brazil". Os dados agora vêm do coletor real.
- **Volta de entrada nos boxes:** a consistência antes excluía só a volta de saída. Agora exclui também a de entrada e a volta 1, como pede o enunciado ("excluindo voltas de entrada e saída").
- **Variável de ambiente:** o `.env` usava `MONGODB_URI`, e o resto dos exercícios usa `MONGO_URI`. Padronizei como `MONGO_URI`.
