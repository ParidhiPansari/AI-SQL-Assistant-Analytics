"""
app.py
------
Streamlit front-end for the AI-Powered SQL Analytics Assistant.

Run with:
    streamlit run app.py

Requires:
    - business.db (run `python generate_data.py` first)
    - OPENAI_API_KEY environment variable set
"""

import os
import sqlite3
import pandas as pd
import streamlit as st

from nl_to_sql import answer_question, get_schema_description, DB_PATH

st.set_page_config(page_title="AI SQL Analytics Assistant", page_icon="📊", layout="wide")


@st.cache_data(show_spinner=False)
def load_table(query: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def render_kpi_dashboard():
    st.subheader("Business KPI Overview")

    kpi_query = """
    SELECT
        ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100.0)), 2) AS total_revenue,
        COUNT(DISTINCT o.order_id) AS total_orders,
        COUNT(DISTINCT o.customer_id) AS total_customers,
        ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100.0)) * 1.0
              / COUNT(DISTINCT o.order_id), 2) AS avg_order_value
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.status = 'Completed';
    """
    kpis = load_table(kpi_query).iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Revenue", f"${kpis['total_revenue']:,.0f}")
    c2.metric("Completed Orders", f"{kpis['total_orders']:,}")
    c3.metric("Unique Customers", f"{kpis['total_customers']:,}")
    c4.metric("Avg Order Value", f"${kpis['avg_order_value']:,.2f}")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Revenue by Category**")
        cat_query = """
        SELECT p.category,
               ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100.0)), 2) AS revenue
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.status = 'Completed'
        GROUP BY p.category
        ORDER BY revenue DESC;
        """
        cat_df = load_table(cat_query)
        st.bar_chart(cat_df.set_index("category"))

    with col2:
        st.markdown("**Monthly Revenue Trend**")
        trend_query = """
        SELECT strftime('%Y-%m', o.order_date) AS month,
               ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100.0)), 2) AS revenue
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
        WHERE o.status = 'Completed'
        GROUP BY month
        ORDER BY month;
        """
        trend_df = load_table(trend_query)
        st.line_chart(trend_df.set_index("month"))

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("**Orders by Channel**")
        channel_query = """
        SELECT channel, COUNT(*) AS orders
        FROM orders
        GROUP BY channel
        ORDER BY orders DESC;
        """
        st.dataframe(load_table(channel_query), use_container_width=True, hide_index=True)

    with col4:
        st.markdown("**Top 10 Products by Revenue**")
        top_products_query = """
        SELECT p.product_name,
               ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount_pct/100.0)), 2) AS revenue
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.status = 'Completed'
        GROUP BY p.product_name
        ORDER BY revenue DESC
        LIMIT 10;
        """
        st.dataframe(load_table(top_products_query), use_container_width=True, hide_index=True)


def render_nl_query_tab():
    st.subheader("Ask a question in plain English")
    st.caption(
        "Example: *\"What were the top 5 product categories by revenue last year?\"* or "
        "*\"Which customer segment has the highest average order value?\"*"
    )

    if not os.environ.get("OPENAI_API_KEY"):
        st.warning(
            "No OPENAI_API_KEY found in the environment. Set it before asking a question, e.g.\n\n"
            "`export OPENAI_API_KEY=sk-...` (Mac/Linux) or `setx OPENAI_API_KEY \"sk-...\"` (Windows)."
        )

    question = st.text_input("Your question", placeholder="e.g. What is our total revenue by month in 2025?")
    ask = st.button("Run", type="primary")

    if "history" not in st.session_state:
        st.session_state.history = []

    if ask and question.strip():
        with st.spinner("Generating SQL and querying the database..."):
            result = answer_question(question)
        st.session_state.history.insert(0, {"question": question, **result})

    for entry in st.session_state.history:
        with st.container(border=True):
            st.markdown(f"**Q: {entry['question']}**")
            st.code(entry["sql"], language="sql")
            if entry["error"]:
                st.error(entry["error"])
            else:
                df = entry["dataframe"]
                st.dataframe(df, use_container_width=True, hide_index=True)
                if df.shape[0] > 1 and df.shape[1] >= 2:
                    numeric_cols = df.select_dtypes(include="number").columns
                    if len(numeric_cols) > 0:
                        try:
                            st.bar_chart(df.set_index(df.columns[0])[numeric_cols])
                        except Exception:
                            pass
                st.download_button(
                    "Download CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name="query_result.csv",
                    mime="text/csv",
                    key=f"dl_{hash(entry['sql'])}_{len(st.session_state.history)}",
                )


def render_schema_tab():
    st.subheader("Database Schema")
    st.text(get_schema_description())


def main():
    st.title("📊 AI-Powered SQL Analytics Assistant")
    st.caption("Natural language → SQL → live analytics, backed by a 100K+ row business database.")

    tab1, tab2, tab3 = st.tabs(["💬 Ask a Question", "📈 KPI Dashboard", "🗂 Schema"])

    with tab1:
        render_nl_query_tab()
    with tab2:
        render_kpi_dashboard()
    with tab3:
        render_schema_tab()


if __name__ == "__main__":
    main()
