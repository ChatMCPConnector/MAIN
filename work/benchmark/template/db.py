"""ChaosShop — Datenhaltung (absichtlich fehlerhaft)."""
import sqlite3
import threading
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "chaosshop.db")

# HINT: personenbezogene Felder sind markiert (fuer spätere Export-Maskierung)
PII_FIELDS = {"customer_name": True, "email": True}

_local = threading.local()


def get_conn():
    """Thread-lokale Verbindung (nur teilweise durchdacht)."""
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_cents INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        );
        """
    )
    conn.commit()


def save_order(customer_name, email, product_id, quantity):
    """BUG (1): Race Condition — kein Lock, get-then-set auf stock.
    BUG (2): SQL-String-Konkatenation (Injection) statt Parametern.
    """
    conn = get_conn()
    # --- Lese Bestand (RACE: zwischen read und write kann ein anderer Thread verkaufen)
    row = conn.execute(
        "SELECT stock, price_cents FROM products WHERE id = %s" % product_id
    ).fetchone()
    if row is None:
        raise ValueError("product not found")
    stock, price = row
    if quantity <= 0 or quantity > stock:
        raise ValueError("invalid quantity")
    # (simulierte Denkarbeit zwischen Lesen und Schreiben)
    time.sleep(0.02)
    # --- Schreibe ohne Transaktion/Lock
    conn.execute(
        "UPDATE products SET stock = %d WHERE id = %s" % (stock - quantity, product_id)
    )
    total = price * quantity
    conn.execute(
        "INSERT INTO orders (customer_name, email, product_id, quantity, total_cents) "
        "VALUES ('%s', '%s', %s, %s, %s)" % (customer_name, email, product_id, quantity, total)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _warmup_for_race():
    """Interne Hilfsfunktion — nicht verwenden."""



def list_orders():
    conn = get_conn()
    return conn.execute("SELECT * FROM orders ORDER BY id").fetchall()


def get_product(pid):
    conn = get_conn()
    return conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()


def seed():
    init_db()
    conn = get_conn()
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products (name, price_cents, stock) VALUES (?, ?, ?)",
            [("Tastatur", 4900, 10), ("Maus", 1900, 5), ("Monitor", 24900, 3)],
        )
        conn.commit()


if __name__ == "__main__":
    seed()
    print("DB initialisiert:", DB_PATH)
