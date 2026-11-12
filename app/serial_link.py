"""Conexão USB com o Arduino: protocolo em quadros, audio com controle de fluxo."""
import struct
import threading
import time

import serial

PROTO = 1


def make_frame(t, data=b""):
    if isinstance(t, str):
        t = ord(t)
    data = bytes(data)[:255]
    s = (t + len(data) + sum(data)) & 0xFF
    return bytes([0x7E, t, len(data)]) + data + bytes([s])


class Device:
    """Um Arduino rodando o firmware do Tamagotchi."""

    def __init__(self, port, baud, on_event=None, log=print):
        self.port = port
        self.baud = baud
        self.on_event = on_event or (lambda *a: None)
        self.log = log
        self.ser = None
        self.alive = False
        self.hello = None
        self.stats = None
        self.window = 1
        self._credits = 0
        self._cv = threading.Condition()
        self._wlock = threading.Lock()
        self._abort_audio = False
        self.playing = False
        self.mic_buf = bytearray()
        self.recording = False
        self._hello_evt = threading.Event()

    # ------------------------------------------------------------------ io
    def open(self, wait_hello=4.0):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.05, write_timeout=2)
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()
        # o Arduino reinicia quando a porta abre; esperamos o "ola" dele
        t0 = time.time()
        while time.time() - t0 < wait_hello:
            if self._hello_evt.wait(0.6):
                break
            self.send("H")
        if not self.hello:
            return False
        threading.Thread(target=self._pinger, daemon=True).start()
        return True

    def close(self):
        self.alive = False
        self._abort_audio = True
        with self._cv:
            self._cv.notify_all()
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass

    def send(self, t, data=b""):
        if not self.ser:
            return
        try:
            with self._wlock:
                self.ser.write(make_frame(t, data))
        except Exception as e:
            self.log(f"Falha ao enviar para o Arduino: {e}")
            self.alive = False
            self.on_event("disconnected", None)

    def _pinger(self):
        while self.alive:
            time.sleep(3)
            if not self.playing:
                self.send("H")

    def _reader(self):
        st, t, n, buf, s = 0, 0, 0, bytearray(), 0
        while self.alive:
            try:
                chunk = self.ser.read(256)
            except Exception:
                self.alive = False
                self.on_event("disconnected", None)
                return
            for c in chunk:
                if st == 0:
                    if c == 0x7E:
                        st = 1
                elif st == 1:
                    t, s, st = c, c, 2
                elif st == 2:
                    n, s, buf = c, (s + c) & 0xFF, bytearray()
                    st = 3 if n else 4
                elif st == 3:
                    buf.append(c)
                    s = (s + c) & 0xFF
                    if len(buf) >= n:
                        st = 4
                elif st == 4:
                    st = 0
                    if c == s:
                        self._handle(chr(t), bytes(buf))

    def _handle(self, t, d):
        if t == "k":
            with self._cv:
                self._credits += d[0] if d else 1
                self._cv.notify_all()
        elif t == "h" and len(d) >= 14:
            fw_hash = struct.unpack("<I", d[10:14])[0]
            self.hello = {"proto": d[0], "fw": d[1], "vs": d[2], "rxbuf": d[3] * 4,
                          "hunger": d[4], "happy": d[5], "energy": d[6], "clean": d[7],
                          "sleeping": d[8], "anim": d[9], "hash": fw_hash}
            self.window = max(1, (self.hello["rxbuf"] - 48) // 36)
            self.stats = dict(self.hello)
            self._hello_evt.set()
            self.on_event("hello", self.hello)
        elif t == "s" and len(d) >= 10:
            self.stats = {"hunger": d[0], "happy": d[1], "energy": d[2], "clean": d[3],
                          "sleeping": d[4], "anim": d[5], "age_min": struct.unpack("<I", d[6:10])[0]}
            self.on_event("stats", self.stats)
        elif t == "b" and d:
            self.on_event("action", d[0])
        elif t == "r":
            self.mic_buf = bytearray()
            self.recording = True
            self.on_event("rec_start", None)
        elif t == "m":
            self.mic_buf.extend(d)
        elif t == "q":
            self.recording = False
            self.on_event("rec_end", bytes(self.mic_buf))
        elif t == "x":
            self._abort_audio = True
            with self._cv:
                self._cv.notify_all()
            self.on_event("abort", None)
        elif t == "e":
            self.on_event("play_end", None)

    # ------------------------------------------------------------ comandos
    def anim(self, anim_id, seconds=5):
        self.send("A", bytes([anim_id & 0xFF, max(0, min(255, int(seconds)))]))

    def text(self, text, duration_ms=0):
        from .firmware_tools import ascii_only
        t = ascii_only(text)[:118].encode("ascii")
        ds = max(0, min(65535, int(duration_ms / 100)))
        self.send("T", struct.pack("<H", ds) + t)

    def action(self, act_id):
        self.send("X", bytes([act_id]))

    def set_volume(self, percent):
        att = max(0, min(200, int((100 - percent) * 1.6)))
        self.send("V", bytes([att]))

    def set_name(self, name):
        from .firmware_tools import ascii_only
        self.send("N", ascii_only(name)[:12].encode("ascii"))

    def record(self, on):
        self.send("R", bytes([1 if on else 0]))

    def set_stats(self, h, ha, e, c):
        self.send("S", bytes([h, ha, e, c]))

    def reset_pet(self):
        self.send("Z")

    def test_display(self):
        self.send("G")

    def play_audio(self, data):
        """Envia MP3/WAV para o alto-falante do shield (bloqueia até terminar)."""
        self._abort_audio = False
        self.playing = True
        with self._cv:
            self._credits = self.window
        self.send("P")
        try:
            for i in range(0, len(data), 32):
                with self._cv:
                    t0 = time.time()
                    while self._credits <= 0 and not self._abort_audio and self.alive:
                        self._cv.wait(0.5)
                        if time.time() - t0 > 3:
                            self.log("Arduino parou de pedir audio (timeout).")
                            self._abort_audio = True
                    if self._abort_audio or not self.alive:
                        break
                    self._credits -= 1
                self.send("D", data[i:i + 32])
        finally:
            self.send("E")
            self.playing = False
