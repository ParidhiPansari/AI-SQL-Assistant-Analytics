# AI-Powered SQL Analytics Assistant

Natural-language analytics assistant that converts business questions into
executable SQL and runs them against a live database — with an interactive 
Streamlit dashboard for ad-hoc analytics and KPI reporting.

**Stack:** Python · SQL (SQLite) · Streamlit · OpenAI API · Pandas

## What's included

| File | Purpose |
|---|---|
| `generate_data.py` | Builds `business.db`, a synthetic e-commerce SQLite database (customers, products, orders, order_items — ~130K rows total) |
| `nl_to_sql.py` | Core engine: schema introspection, prompt construction, LLM call, SQL-safety validation, execution |
| `app.py` | Streamlit UI: NL question box, KPI dashboard, schema viewer |
| `requirements.txt` | Python dependencies |

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate the synthetic database (one-time, ~30s)
python generate_data.py

# 3. Set your OpenAI API key
export OPENAI_API_KEY="sk-..."        # Mac/Linux
setx OPENAI_API_KEY "sk-..."          # Windows (new terminal after)

# 4. Launch the app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## How it works

1. **Schema introspection** — `get_schema_description()` reads the live
   SQLite schema (tables, columns, types) plus two sample rows per table,
   so the LLM grounds its SQL in the real structure instead of guessing.
2. **Prompt → SQL** — the question and schema are sent to the OpenAI chat
   completions endpoint with a system prompt that forces SQL-only output
   and encodes business logic (e.g. how discounted revenue is computed).
3. **Safety layer** — before execution, every query is checked:
   only a single `SELECT`/`WITH` statement is allowed; `INSERT`, `UPDATE`,
   `DELETE`, `DROP`, `ALTER`, `PRAGMA`, statement-chaining, etc. are all
   blocked. A `LIMIT` is auto-injected on aggregate queries that lack one.
4. **Execution & display** — the validated SQL runs against SQLite via
   pandas; results render as a table, an auto-generated bar chart (when the
   shape fits), and a CSV download button.


## Extending this project

- **Swap SQLite for Postgres/MySQL**: change the connection logic in
  `nl_to_sql.py` (`sqlite3.connect` → `psycopg2`/`sqlalchemy` engine) and
  update `PRAGMA table_info` to an information_schema query.
- **Add query result caching** to cut API costs on repeated questions.
- **Add role-based row-level filtering** before executing generated SQL,
  for multi-tenant dashboards.
- **Swap the model** by changing `MODEL_NAME` in `nl_to_sql.py`.
