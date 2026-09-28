# Prática 04 — OpenF1 Data Explorer (Streamlit + MongoDB)

Interface web que transforma seleções em consultas MongoDB sobre o banco `openf1_data`
(populado pelo coletor do Exercício OpenF1).

| Arquivo | Papel |
|---|---|
| `streamlit_app.py` | Interface: filtros, métricas, gráfico, tabela |
| `db_utils.py` | Conexão e todas as consultas ao MongoDB |
| `requirements.txt` | Dependências |
| `.env` | `MONGO_URI` / `MONGO_DB_NAME` |

## Como executar

```bash
pip install -r requirements.txt
# 1) popular o banco (pasta do Exercício OpenF1):
python ../Ex01_OpenF1_Coletor/f1_data_collector.py 9157
# 2) abrir o app:
streamlit run streamlit_app.py
```

## Fluxo (estudo de caso: GP da Itália 2023)

1. Na sidebar, escolha o ano **2023** e a corrida **"Italy · Monza — Race"**. Aparecem as métricas de país, circuito e data.
2. Selecione **Charles Leclerc** e **Carlos Sainz**.
3. O gráfico de linhas mostra `lap_duration` × `lap_number`. Os picos são as paradas nos boxes.
4. Abra **"Ver tabela de dados"** para ver os valores exatos (também dá para baixar em CSV).
5. Extra para os engenheiros de dados: o expander **"Validação da ingestão"** mostra as contagens e confirma que não há voltas duplicadas.

## Mudanças em relação ao código que veio no .zip

- **Só MongoDB:** removi o fallback para a API e para dados *mock*. O escopo do documento de visão é "uso exclusivo para dados já existentes no MongoDB".
- **`session_key` como inteiro:** o código antigo convertia para `str`, e o coletor grava `int`, então nenhuma consulta encontrava dados.
- **`load_dotenv()`:** faltava, e o `.env` era ignorado.
- **Cache:** `st.cache_resource` na conexão e `st.cache_data` nas consultas.
- **Anos da sidebar:** vêm de `distinct("year")` na collection `sessions`, em vez de uma lista fixa.
