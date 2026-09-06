"""ChaosShop — HTTP-Server (Standardbibliothek, absichtlich fehlerhaft)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import db
import auth

PORT = 8700


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._json(200, {"status": "ok"})
        if u.path == "/orders":
            orders = db.list_orders()
            return self._json(200, [
                {"id": o[0], "customer_name": o[1], "email": o[2],
                 "product_id": o[3], "quantity": o[4], "total_cents": o[5], "status": o[6]}
                for o in orders
            ])
        if u.path == "/products":
            conn = db.get_conn()
            rows = conn.execute("SELECT * FROM products").fetchall()
            return self._json(200, [dict(zip(("id", "name", "price_cents", "stock"), r)) for r in rows])
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/orders":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid json"})
        try:
            oid = db.save_order(
                data.get("customer_name", ""),
                data.get("email", ""),
                data.get("product_id"),
                data.get("quantity"),
            )
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        return self._json(201, {"order_id": oid})


def run():
    db.seed()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"ChaosShop listening on {PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
