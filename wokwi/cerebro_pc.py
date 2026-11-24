"""Cerebro do PIXO no PC, para usar com o ESP32 do Wokwi.

Abre uma pagina em http://localhost:8765 com microfone, conversa e voz.
O PC pensa (mesmo cerebro e mesma voz do Tamagotchi Studio, com a chave do
settings.json) e manda a resposta para o ESP32 do Wokwi pelo ntfy.sh:

  celular / microfone do PC / Serial do Wokwi
        -> este programa (cerebro + voz)
        -> ntfy.sh/<topico>_pc  -> ESP32 no Wokwi (animacao, legenda, acao)
        -> ntfy.sh/<topico>     -> app ntfy do celular (texto da resposta)

Rodar: CEREBRO.bat (ou .venv\\Scripts\\python.exe wokwi\\cerebro_pc.py)
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import brain as brain_mod  # noqa: E402
from app import settings as settings_mod  # noqa: E402
from app import voice  # noqa: E402

TOPIC = os.environ.get("PIXO_TOPIC", "tamagotchi_iot")  # mesmo NTFY_TOPIC do secrets.h do Wokwi
TOPIC_PC = TOPIC + "_pc"
PORT = int(os.environ.get("PIXO_PORT", "8765"))
NTFY = "https://ntfy.sh"
HERE = os.path.dirname(os.path.abspath(__file__))

S = settings_mod.load()
BRAIN = brain_mod.Brain(S)

lock = threading.Lock()  # uma conversa por vez
log_lock = threading.Lock()
LOG = []  # {"n", "t", "who", "text", "anim", "action", "audio"}
AUDIO = {}  # id -> mp3
STATE = {"hunger": 80, "happy": 80, "energy": 80, "clean": 80, "sleeping": False, "events": [], "seen": 0}
STATUS = {"ntfy": False, "thinking": False}


def add_log(who, text, **extra):
    with log_lock:
        e = {"n": len(LOG) + 1, "t": time.strftime("%H:%M:%S"), "who": who, "text": text}
        e.update(extra)
        LOG.append(e)
        del LOG[:-200]
    print(f"[{e['t']}] {who}: {text}", flush=True)
    return e


# ------------------------------------------------------------------ ntfy
def publish(topic, body, title=None, tags=None):
    req = urllib.request.Request(f"{NTFY}/{topic}", data=body.encode("utf-8"), method="POST")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    if title:
        req.add_header("Title", title)
    if tags:
        req.add_header("Tags", ",".join(tags))
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except (urllib.error.URLError, OSError) as e:
        add_log("sistema", f"nao consegui publicar no ntfy ({e})")


def send_to_pet(data):
    """Manda a resposta para o ESP32 (JSON) e o texto para o celular."""
    cmd = {"speech": data.get("speech", ""), "animation": data.get("animation", "talking"),
           "action": data.get("action", "none"), "mood": int(data.get("mood_change", 0) or 0)}
    publish(TOPIC_PC, json.dumps(cmd, ensure_ascii=False), tags=["cmd"])
    if cmd["speech"]:
        publish(TOPIC, cmd["speech"], title=S.get("pet_name", "PIXO"), tags=["pixo"])


def ntfy_listener():
    since = None
    while True:
        url = f"{NTFY}/{TOPIC},{TOPIC_PC}/json" + (f"?since={since}" if since else "")
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                STATUS["ntfy"] = True
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("event") != "message":
                        continue
                    since = ev.get("id", since)
                    handle_ntfy(ev)
        except Exception as e:  # queda de rede, timeout do keepalive etc.
            STATUS["ntfy"] = False
            if not isinstance(e, TimeoutError):
                print("ntfy:", e, flush=True)
            time.sleep(3)


def handle_ntfy(ev):
    tags = ev.get("tags") or []
    msg = (ev.get("message") or "").strip()
    if ev.get("topic") == TOPIC_PC:
        if "state" in tags:  # o ESP32 contando como o pet esta
            try:
                st = json.loads(msg)
            except ValueError:
                return
            for k in ("hunger", "happy", "energy", "clean"):
                if k in st:
                    STATE[k] = int(st[k])
            STATE["sleeping"] = bool(st.get("sleeping", False))
            if st.get("events"):
                STATE["events"] = list(st["events"])[-3:]
            STATE["seen"] = time.time()
        elif "text" in tags and msg:  # frase digitada no Serial do Wokwi
            threading.Thread(target=converse, args=(msg, "Serial do Wokwi"), daemon=True).start()
        return
    if "pixo" in tags or not msg:  # as respostas do proprio PIXO
        return
    threading.Thread(target=converse, args=(msg, "celular"), daemon=True).start()


# ------------------------------------------------------------------ cerebro
def converse(text, who):
    add_log(who, text)
    with lock:
        STATUS["thinking"] = True
        try:
            state = dict(STATE)
            data = BRAIN.reply(text, state)
            STATE["events"] = []
        except Exception as e:
            STATUS["thinking"] = False
            add_log("sistema", f"o cerebro falhou: {str(e)[:200]}")
            send_to_pet({"speech": "Nao consegui pensar agora :(", "animation": "confused"})
            return
        threading.Thread(target=send_to_pet, args=(data,), daemon=True).start()
        audio_id = None
        try:
            sp = voice.tts(data["speech"], S)
            audio_id = str(len(AUDIO) + 1)
            AUDIO[audio_id] = (sp.pc_audio, "audio/mpeg" if sp.pc_hint == "mp3" else "audio/wav")
        except Exception as e:
            print("voz falhou:", e, flush=True)
        STATUS["thinking"] = False
        add_log(S.get("pet_name", "PIXO"), data["speech"], anim=data.get("animation"),
                action=data.get("action"), audio=audio_id)


def quick_action(action):
    names = {"feed": "deu comida", "play": "brincou", "clean": "deu banho", "sleep": "colocou para dormir",
             "wake": "acordou o pet"}
    if action not in names:
        return
    add_log("voce", f"({names[action]})")
    threading.Thread(target=publish, args=(TOPIC_PC, json.dumps({"speech": "", "animation": "", "action": action,
                                                                "mood": 0}), None, ["cmd"]), daemon=True).start()


# ------------------------------------------------------------------ site
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "cerebro_pc.html"), encoding="utf-8") as f:
                page = f.read().replace("{{TOPIC}}", TOPIC).replace("{{PET}}", S.get("pet_name", "PIXO"))
            return self._send(200, page, "text/html; charset=utf-8")
        if self.path.startswith("/api/log"):
            after = 0
            if "after=" in self.path:
                try:
                    after = int(self.path.split("after=")[1].split("&")[0])
                except ValueError:
                    pass
            with log_lock:
                items = [e for e in LOG if e["n"] > after]
            st = dict(STATE)
            st["fresh"] = time.time() - st.pop("seen") < 600  # o ESP32 mandou noticia nos ultimos 10 min
            return self._send(200, json.dumps({"log": items, "state": st, "status": STATUS}, ensure_ascii=False))
        if self.path.startswith("/api/audio/"):
            a = AUDIO.get(self.path.rsplit("/", 1)[1])
            if not a:
                return self._send(404, "{}")
            return self._send(200, a[0], a[1])
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            data = {}
        if self.path == "/api/say":
            text = str(data.get("text", "")).strip()[:500]
            if text:
                threading.Thread(target=converse, args=(text, "voce"), daemon=True).start()
            return self._send(202, "{}")
        if self.path == "/api/action":
            quick_action(str(data.get("action", "")))
            return self._send(202, "{}")
        if self.path == "/api/clear":
            BRAIN.clear()
            add_log("sistema", "memoria da conversa apagada")
            return self._send(200, "{}")
        self._send(404, "{}")


def main():
    if not S.get("anthropic_api_key"):
        print("Sem chave da API no settings.json. Abra o TAMAGOTCHI.bat e coloque a chave em Configuracoes.")
        sys.exit(1)
    threading.Thread(target=ntfy_listener, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Cerebro do {S.get('pet_name', 'PIXO')} rodando em {url}  (topico ntfy: {TOPIC})")
    print("Deixe esta janela aberta. Ctrl+C para sair.", flush=True)
    add_log("sistema", f"cerebro pronto. Topico do celular: ntfy.sh/{TOPIC}")
    if not os.environ.get("PIXO_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
