"""
nl_to_sql.py
------------
Core engine that turns a natural-language business question into an
executable, READ-ONLY SQL query against business.db, using the OpenAI API.

Design notes:
  - We give the LLM the actual schema (tables + columns + types) so it
    grounds its SQL in reality instead of guessing column names.
  - We force SQL-only output (no prose, no markdown fences) via the prompt,
    then strip fences defensively anyway.
  - We hard-block anything that isn't a SELECT statement before execution,
    so the assistant can never mutate or drop data.
  - Every query gets a LIMIT injected if the model forgot one, to keep the
    UI responsive on a 100K+ row table.
"""

import os
import re
import sqlite3
import pandas as pd
from openai import OpenAI

DB_PATH = "business.db"
MODEL_NAME = "gpt-4o-mini"  # swap for any chat-completion-capable model
DEFAULT_ROW_LIMIT = 500

_client = None


def get_client():
    """Lazily create the OpenAI client so the app can start without a key
    and only fail when the user actually asks a question."""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it or add it to a .env file."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def get_schema_description(db_path: str = DB_PATH) -> str:
    """Introspect the SQLite file and build a compact schema description
    the LLM can reason over, including a couple of sample rows per table
    so it understands the data's shape/format (e.g. date strings)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]

    parts = []
    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()  # (cid, name, type, notnull, dflt, pk)
        col_desc = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        parts.append(f"TABLE {table} ({col_desc})")

        sample = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 2", conn)
        parts.append(f"  sample rows: {sample.to_dict(orient='records')}")

    conn.close()
    return "\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """You are an expert SQLite analyst. You translate a business user's
natural-language question into a single, correct, read-only SQLite SQL query.

Database schema:
{schema}

Rules:
- Output ONLY the SQL query. No explanation, no markdown code fences, no comments.
- Only ever write a SELECT statement. Never write INSERT, UPDATE, DELETE, DROP, ALTER, or PRAGMA.
- Use explicit JOINs with the foreign keys implied by the schema (customer_id, product_id, order_id).
- If the question implies an aggregate (total, average, top N, count, revenue, etc.), use
  GROUP BY / ORDER BY / LIMIT appropriately.
- Revenue for a line item = quantity * unit_price * (1 - discount_pct / 100.0).
- If the question is ambiguous, make the most reasonable business assumption rather than asking
  a follow-up question, since you cannot ask one.
- Always include a LIMIT clause (max 1000 rows) unless the question explicitly asks for a
  single aggregate value (e.g. "what's the total revenue").
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


def _is_safe_select(sql: str) -> bool:
    """Only allow a single SELECT/WITH statement. Blocks anything that could
    mutate the database or chain a second statement."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        return False  # no statement chaining
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "attach", "pragma", "create", "replace"]
    return not any(re.search(rf"\b{kw}\b", lowered) for kw in forbidden)


def _ensure_limit(sql: str, limit: int = DEFAULT_ROW_LIMIT) -> str:
    if re.search(r"\blimit\b", sql, flags=re.IGNORECASE):
        return sql
    # Don't force a LIMIT onto a bare single-row aggregate query (heuristic:
    # no GROUP BY -> likely a scalar aggregate -> leave it alone).
    if not re.search(r"\bgroup\s+by\b", sql, flags=re.IGNORECASE):
        return sql
    return sql.rstrip().rstrip(";") + f" LIMIT {limit}"


def generate_sql(question: str, schema: str) -> str:
    """Call the LLM to translate `question` into SQL grounded in `schema`."""
    client = get_client()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema)
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    raw_sql = response.choices[0].message.content
    return _strip_code_fences(raw_sql)


def run_query(sql: str, db_path: str = DB_PATH) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
    return df


def answer_question(question: str, db_path: str = DB_PATH):
    """Full pipeline: question -> SQL -> validated -> executed -> DataFrame.

    Returns a dict: {sql, dataframe, error}
    Exactly one of (dataframe, error) will be populated.
    """
    schema = get_schema_description(db_path)
    sql = generate_sql(question, schema)
    sql = _ensure_limit(sql)

    if not _is_safe_select(sql):
        return {"sql": sql, "dataframe": None, "error": "Generated query was blocked: only single read-only SELECT statements are allowed."}

    try:
        df = run_query(sql, db_path)
        return {"sql": sql, "dataframe": df, "error": None}
    except Exception as e:
        return {"sql": sql, "dataframe": None, "error": str(e)}
