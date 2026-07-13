"""
generate_data.py
----------------
Creates a synthetic e-commerce SQLite database (business.db) with:
  - customers   (~5,000 rows)
  - products    (~500 rows)
  - orders      (~40,000 rows)
  - order_items (~110,000+ rows)

Run once before starting the app:
    python generate_data.py
"""

import sqlite3
import random
from datetime import datetime, timedelta
from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

DB_PATH = "business.db"

N_CUSTOMERS = 5000
N_PRODUCTS = 500
N_ORDERS = 40000

CATEGORIES = {
    "Electronics": ["Phones", "Laptops", "Accessories", "Audio"],
    "Home & Kitchen": ["Cookware", "Furniture", "Decor", "Appliances"],
    "Apparel": ["Men", "Women", "Kids", "Footwear"],
    "Sports & Outdoors": ["Fitness", "Camping", "Cycling", "Team Sports"],
    "Beauty": ["Skincare", "Haircare", "Makeup", "Fragrance"],
    "Books": ["Fiction", "Non-Fiction", "Children", "Academic"],
}

SEGMENTS = ["Consumer", "Small Business", "Enterprise"]
CHANNELS = ["Web", "Mobile App", "Marketplace", "In-Store"]
STATUSES = ["Completed", "Completed", "Completed", "Completed", "Cancelled", "Refunded", "Pending"]

START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2026, 7, 1)


def random_date(start, end):
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days), seconds=random.randint(0, 86399))


def build_schema(conn):
    cur = conn.cursor()
    cur.executescript(
        """
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;

        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
            city TEXT,
            state TEXT,
            country TEXT,
            segment TEXT,
            signup_date TEXT
        );

        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT,
            category TEXT,
            subcategory TEXT,
            unit_cost REAL,
            list_price REAL
        );

        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT,
            channel TEXT,
            status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL,
            discount_pct REAL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        """
    )
    conn.commit()


def gen_customers(conn):
    rows = []
    for i in range(1, N_CUSTOMERS + 1):
        name = fake.name()
        rows.append(
            (
                i,
                name,
                f"{name.split()[0].lower()}.{i}@example.com",
                fake.city(),
                fake.state(),
                "USA",
                random.choices(SEGMENTS, weights=[70, 22, 8])[0],
                random_date(START_DATE, END_DATE).date().isoformat(),
            )
        )
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()


def gen_products(conn):
    rows = []
    pid = 1
    for category, subcats in CATEGORIES.items():
        for _ in range(N_PRODUCTS // len(CATEGORIES)):
            subcat = random.choice(subcats)
            cost = round(random.uniform(5, 400), 2)
            price = round(cost * random.uniform(1.3, 2.8), 2)
            rows.append(
                (
                    pid,
                    f"{subcat} {fake.word().capitalize()} {random.choice(['Pro','Max','Lite','Plus',''])}".strip(),
                    category,
                    subcat,
                    cost,
                    price,
                )
            )
            pid += 1
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    return pid - 1


def gen_orders_and_items(conn, n_products):
    order_rows = []
    item_rows = []
    item_id = 1

    for order_id in range(1, N_ORDERS + 1):
        customer_id = random.randint(1, N_CUSTOMERS)
        order_date = random_date(START_DATE, END_DATE)
        channel = random.choices(CHANNELS, weights=[45, 30, 20, 5])[0]
        status = random.choice(STATUSES)

        order_rows.append((order_id, customer_id, order_date.isoformat(), channel, status))

        n_items = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        for _ in range(n_items):
            product_id = random.randint(1, n_products)
            quantity = random.randint(1, 5)
            cur = conn.execute("SELECT list_price FROM products WHERE product_id=?", (product_id,))
            list_price = cur.fetchone()[0]
            discount = random.choices([0, 5, 10, 15, 20], weights=[55, 20, 15, 7, 3])[0]
            item_rows.append((item_id, order_id, product_id, quantity, list_price, discount))
            item_id += 1

        if order_id % 5000 == 0:
            print(f"  ...generated {order_id}/{N_ORDERS} orders")

    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", order_rows)
    conn.commit()
    conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", item_rows)
    conn.commit()
    print(f"  total order_items rows: {len(item_rows)}")


def main():
    conn = sqlite3.connect(DB_PATH)
    print("Building schema...")
    build_schema(conn)
    print("Generating customers...")
    gen_customers(conn)
    print("Generating products...")
    n_products = gen_products(conn)
    print("Generating orders + order_items (this takes a moment)...")
    gen_orders_and_items(conn, n_products)
    conn.close()
    print(f"\nDone. Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
