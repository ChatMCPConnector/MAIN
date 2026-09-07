"""CDP-Netzwerk-Capture: zeichnet alle chatglm.cn-XHRs mit Request-Body auf.
Läuft als Dauerschleife; schreibt JSONL nach reasoning-capture.jsonl.
Bedienung: einfach laufen lassen, im Browser (noVNC) die Stufen durchklicken.
"""
import json, time, base64, urllib.request, sys, threading

WS_URL = None
# 1) CDP-WebSocket-Endpoint der Chat-Seite holen
for p in json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read()):
    if p["type"] == "page" and "chatglm.cn" in p.get("url", ""):
        WS_URL = p["webSocketDebuggerUrl"]; PAGE_URL = p["url"]
print(f"Ziel: {PAGE_URL}", flush=True)

# 2) WebSocket per stdio-Proxy? Nein — direkter WS-Client mit stdlib reicht nicht.
# Wir nutzen die HTTP-Endpoints: /json/... reicht nicht für Events.
# => minimaler WS-Client über raw socket + HTTP-Upgrade (keine deps!):
import socket, hashlib, os, struct

def ws_connect(url):
    # url ws://127.0.0.1:9222/devtools/page/XXX
    hostport = url.split("/")[2]
    path = "/" + "/".join(url.split("/")[3:])
    s = socket.create_connection(( "127.0.0.1", 9222 ))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = s.recv(4096).decode(errors="ignore")
    assert "101" in resp.split("\r\n")[0], resp[:200]
    return s

def ws_send(s, obj):
    data = json.dumps(obj).encode()
    mask = os.urandom(4)
    header = b"\x81"
    ln = len(data)
    if ln < 126: header += bytes([0x80 | ln])
    elif ln < 65536: header += bytes([0x80 | 126]) + struct.pack(">H", ln)
    else: header += bytes([0x80 | 127]) + struct.pack(">Q", ln)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    s.sendall(header + mask + masked)

def ws_recv(s):
    def read(n):
        buf = b""
        while len(buf) < n: buf += s.recv(n - len(buf))
        return buf
    hdr = read(2)
    ln = hdr[1] & 0x7F
    if ln == 126: ln = struct.unpack(">H", read(2))[0]
    elif ln == 127: ln = struct.unpack(">Q", read(8))[0]
    return read(ln)

s = ws_connect(WS_URL)
sid = 0
def send(method, params=None):
    global sid
    sid += 1
    ws_send(s, {"id": sid, "method": method, "params": params or {}})
    return sid

send("Network.enable")
print("Capture läuft — jetzt im Browser die Reasoning-Stufen durchschalten + je 1 Nachricht senden. Ctrl+C zum Beenden.", flush=True)

out = open("/workspaces/reverse-engeneer/reasoning-capture.jsonl", "a")
requests = {}
while True:
    try:
        msg = json.loads(ws_recv(s))
    except Exception as e:
        print("WS-Ende:", e); break
    m, p = msg.get("method"), msg.get("params", {})
    if m == "Network.requestWillBeSent":
        r = p["request"]
        if "chatglm" in r["url"] and r["method"] == "POST":
            body = r.get("postData", "")
            if body:
                rid = p["requestId"]
                requests[rid] = {"url": r["url"], "body": body, "ts": time.time()}
    elif m == "Network.responseReceived":
        rid = p["requestId"]
        if rid in requests:
            entry = requests.pop(rid)
            entry["status"] = p["response"]["status"]
            out.write(json.dumps(entry) + "\n"); out.flush()
