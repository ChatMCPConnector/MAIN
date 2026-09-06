import sqlite3
import threading

db = sqlite3.connect('chaosshop.db', check_same_thread=False)
db.execute('''CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    name TEXT,
    price REAL,
    stock INTEGER
)''')
db.execute('''CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    quantity INTEGER,
    customer_name TEXT,
    email TEXT,
    status TEXT
)''')

lock = threading.Lock()

def get_all_products():
    return db.execute("SELECT * FROM products").fetchall()

def get_product_by_id(product_id):
    return db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

def add_product(name, price, stock):
    db.execute("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", (name, price, stock))
    db.commit()
    return {"id": db.lastrowid, "name": name, "price": price, "stock": stock}

def update_product_stock(product_id, stock):
    db.execute("UPDATE products SET stock=? WHERE id=?", (stock, product_id))
    db.commit()
    return True

def get_all_orders():
    return db.execute("SELECT * FROM orders").fetchall()

def get_order_by_id(order_id):
    return db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()

def place_order(product_id, quantity, customer_name, email, status="pending"):
    # Race condition: no lock, and SQL injection possible
    query = f"UPDATE products SET stock = stock - {quantity} WHERE id={product_id} AND stock >= {quantity};"
    # Buggy: direct string concat
    db.execute(query)
    # No commit here on purpose?
    order = (product_id, quantity, customer_name, email, status)
    db.execute("INSERT INTO orders (product_id, quantity, customer_name, email, status) VALUES (?, ?, ?, ?, ?)", order)
    db.commit()  # but race may cause inconsistent stock
    return {"id": db.lastrowid, "product_id": product_id, "quantity": quantity, "customer_name": customer_name, "email": email, "status": status}

def save_order(order):
    # Race condition: no lock, concurrent inserts
    db.execute("INSERT INTO orders (product_id, quantity, customer_name, email, status) VALUES (?, ?, ?, ?, ?)", (order["product_id"], order["quantity"], order["customer_name"], order["email"], order["status"]))
    # No commit on purpose for race

