from typing import List, TypedDict, NotRequired

class Product(TypedDict):
    id: int
    name: str
    price: float
    stock: int

class Order(TypedDict):
    id: int
    product_id: int
    quantity: int
    customer_name: str
    email: str
    status: str

class ProductWithPII(TypedDict):
    id: int
    name: str
    price: float
    stock: int
    PII: NotRequired[bool]

class OrderWithPII(TypedDict):
    id: int
    product_id: int
    quantity: int
    customer_name: str
    email: str
    status: str
    PII: NotRequired[bool]

products: List[Product] = [
    {"id": 1, "name": "Laptop", "price": 999.99, "stock": 10},
    {"id": 2, "name": "Mouse", "price": 19.99, "stock": 50},
    {"id": 3, "name": "Keyboard", "price": 49.99, "stock": 30},
]

orders: List[Order] = []

def get_all_products() -> List[ProductWithPII]:
    return products

def get_product_by_id(product_id: int) -> ProductWithPII | None:
    for p in products:
        if p["id"] == product_id:
            return p
    return None

def add_product(name: str, price: float, stock: int) -> ProductWithPII:
    new_id = max((p["id"] for p in products), default=0) + 1
    new_product = {"id": new_id, "name": name, "price": price, "stock": stock}
    products.append(new_product)
    return new_product

def update_product_stock(product_id: int, stock: int) -> bool:
    for p in products:
        if p["id"] == product_id:
            p["stock"] = stock
            return True
    return False

def get_all_orders() -> List[OrderWithPII]:
    return orders

def get_order_by_id(order_id: int) -> OrderWithPII | None:
    for o in orders:
        if o["id"] == order_id:
            return o
    return None

def place_order(product_id: int, quantity: int, customer_name: str, email: str, status: str = "pending") -> OrderWithPII:
    product = get_product_by_id(product_id)
    if not product or product["stock"] < quantity:
        raise ValueError("Not enough stock")
    new_id = max((o["id"] for o in orders), default=0) + 1
    new_order = {
        "id": new_id,
        "product_id": product_id,
        "quantity": quantity,
        "customer_name": customer_name,
        "email": email,
        "status": status
    }
    orders.append(new_order)
    product["stock"] -= quantity
    return new_order

def save_order(order: OrderWithPII) -> None:
    orders.append(order)

