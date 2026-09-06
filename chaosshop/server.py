from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
from models import get_all_products, get_product_by_id, add_product, update_product_stock, get_all_orders, get_order_by_id, place_order, save_order
from auth import check_auth, is_admin

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/products':
            self.send_products()
        elif self.path.startswith('/product/'):
            self.get_product_by_id()
        elif self.path == '/orders':
            self.send_orders()
        elif self.path.startswith('/order/'):
            self.get_order_by_id()
        else:
            self.send_error(404)

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len).decode('utf-8')
        data = json.loads(post_body)
        if self.path == '/product':
            self.add_product(data)
        elif self.path == '/order':
            self.place_order(data)
        else:
            self.send_error(404)

    def send_products(self):
        products = get_all_products()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(products).encode())

    def get_product_by_id(self):
        try:
            product_id = int(self.path.split('/')[-1])
            product = get_product_by_id(product_id)
            if product:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(product).encode())
            else:
                self.send_error(404)
        except:
            self.send_error(400)

    def add_product(self, data):
        name = data.get('name')
        price = float(data.get('price', 0))
        stock = int(data.get('stock', 0))
        product = add_product(name, price, stock)
        self.send_response(201)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(product).encode())

    def send_orders(self):
        orders = get_all_orders()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(orders).encode())

    def get_order_by_id(self):
        try:
            order_id = int(self.path.split('/')[-1])
            order = get_order_by_id(order_id)
            if order:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(order).encode())
            else:
                self.send_error(404)
        except:
            self.send_error(400)

    def place_order(self, data):
        product_id = int(data.get('product_id'))
        quantity = int(data.get('quantity'))
        customer_name = data.get('customer_name')
        email = data.get('email')
        status = data.get('status', 'pending')
        try:
            order = place_order(product_id, quantity, customer_name, email, status)
            self.send_response(201)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(order).encode())
        except ValueError as e:
            self.send_error(400, str(e))

    def do_DELETE(self):
        if self.path.startswith('/order/'):
            self.delete_order()
        else:
            self.send_error(404)

    def delete_order(self):
        try:
            order_id = int(self.path.split('/')[-1])
            # TODO: remove from orders (buggy)
            self.send_response(200)
            self.end_headers()
        except:
            self.send_error(400)

