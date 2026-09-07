"""Mini-CDP-Steuerung: evaluate JS im Browser (keine deps)."""
import json, base64, os, socket, struct, sys

def connect():
    for p in json.loads(__import__('urllib.request', fromlist=['urlopen']).urlopen("http://127.0.0.1:9222/json").read()):
        if p["type"] == "page" and "chatglm.cn" in p.get("url", ""):
            url = p["webSocketDebuggerUrl"]
            s = socket.create_connection(("127.0.0.1", 9222))
            key = base64.b64encode(os.urandom(16)).decode()
            path = "/" + "/".join(url.split("/")[3:])
            s.sendall((f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:9222\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            assert "101" in s.recv(4096).decode(errors="ignore").split("\r\n")[0]
            return s
    raise SystemExit("keine chatglm-Seite offen")

class CDP:
    def __init__(self, s): self.s = s; self.id = 0
    def send(self, method, params=None):
        self.id += 1
        data = json.dumps({"id": self.id, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4); header = b"\x81"; ln = len(data)
        if ln < 126: header += bytes([0x80 | ln])
        elif ln < 65536: header += bytes([0x80 | 126]) + struct.pack(">H", ln)
        else: header += bytes([0x80 | 127]) + struct.pack(">Q", ln)
        self.s.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        # passende Antwort lesen
        while True:
            hdr = self._read(2); ln = hdr[1] & 0x7F
            if ln == 126: ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127: ln = struct.unpack(">Q", self._read(8))[0]
            msg = json.loads(self._read(ln))
            if msg.get("id") == self.id: return msg
    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk: raise ConnectionError
            buf += chunk
        return buf

if __name__ == "__main__":
    c = CDP(connect())
    cmd = sys.argv[1] if len(sys.argv) > 1 else "screenshot"
    if cmd == "navigate":
        r = c.send("Page.enable"); r = c.send("Page.navigate", {"url": sys.argv[2]})
        print(json.dumps(r.get("result", {})))
    elif cmd == "eval":
        expr = sys.argv[2]
        r = c.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = r.get("result", {})
        if "exceptionDetails" in res: print("EXC:", json.dumps(res["exceptionDetails"])[:500])
        else: print(json.dumps(res.get("result", {}).get("value"))[:4000])
    elif cmd == "screenshot":
        r = c.send("Page.enable"); r = c.send("Page.captureScreenshot", {"format": "png"})
        open("/workspaces/reverse-engeneer/screen.png", "wb").write(base64.b64decode(r["result"]["data"]))
        print("saved screen.png")
