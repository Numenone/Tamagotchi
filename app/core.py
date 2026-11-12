"""Orquestrador: pet virtual + Arduino + Claude + voz."""
import math
import os
import threading
import time

from . import animations as A
from . import firmware_tools as F
from . import voice
from .brain import Brain
from .petsim import PetState, clamp
from .serial_link import Device
from .settings import DATA_DIR, lang_short

PET_SAVE = os.path.join(DATA_DIR, "pet.json")
ACT_ID = {n: i for i, n in enumerate(A.ACTIONS + ["pet"])}


class DeviceManager:
    """Procura o Arduino, grava o firmware se precisar e mantem a conexão."""

    def __init__(self, comp):
        self.c = comp
        self.state = "waiting"  # waiting, checking, programming, done, ready, error
        self.message = ""
        self.progress = 0.0
        self.stage = ""
        self.logs = []
        self.port = None
        self.device = None
        self._bad = {}
        self._force = None
        self._run = True
        self.state_since = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def _set(self, state, msg=""):
        self.state = state
        self.message = msg
        self.state_since = time.time()

    def log(self, line):
        self.logs.append(line)
        self.logs = self.logs[-200:]
        low = line.lower()
        if "gerados" in low:
            self.progress, self.stage = max(self.progress, 0.08), "Gerando as configurações"
        elif "arduino-cli compile" in low:
            self.progress, self.stage = max(self.progress, 0.15), "Compilando o firmware"
        elif "sketch uses" in low:
            self.progress, self.stage = max(self.progress, 0.55), "Firmware compilado"
        elif "enviando para" in low:
            self.progress, self.stage = max(self.progress, 0.62), "Gravando na placa"
        elif "pronto!" in low:
            self.progress = 1.0

    def stop(self):
        self._run = False
        if self.device:
            self.device.close()

    def reprogram(self):
        self._force = "reprogram"

    def retry(self):
        self._bad.clear()
        if self.state == "error":
            self._set("waiting")

    # -------------------------------------------------------------- laco
    def _candidates(self):
        ports = F.list_ports()
        want = self.c.s.get("serial_port", "")
        now = time.time()
        names = [p for p in ports if self._bad.get(p[0], 0) < now]
        if want:
            return [p for p in names if p[0] == want]
        return [p for p in names if p[2] > 0]  # so portas USB (Arduino primeiro)

    def _loop(self):
        while self._run:
            try:
                if self.state in ("waiting", "error"):
                    if self.state == "error" and time.time() - self.state_since < 6:
                        time.sleep(0.5)
                        continue
                    cands = self._candidates()
                    if cands:
                        self._attach(cands[0][0])
                elif self.state in ("ready", "done"):
                    if self.state == "done" and time.time() - self.state_since > 4.5:
                        self._set("ready")
                    if not self.device or not self.device.alive:
                        self.c.on_disconnect()
                        self.device = None
                        self._set("waiting", "O Arduino foi desconectado.")
                    elif self._force == "reprogram":
                        self._force = None
                        self.device.close()
                        self.device = None
                        self.c.on_disconnect()
                        self._program(self.port)
            except Exception as e:  # nunca deixa o laco morrer
                self.log(f"Erro inesperado: {e}")
                self._set("error", str(e)[:200])
            time.sleep(0.8)

    def _open(self, port, wait=4.0):
        dev = Device(port, int(self.c.s.get("baud", 250000)), on_event=self.c.on_device_event, log=self.log)
        try:
            ok = dev.open(wait)
        except Exception as e:
            msg = str(e)
            if "denied" in msg.lower() or "acesso negado" in msg.lower() or "permission" in msg.lower():
                raise PermissionError(f"A porta {port} está ocupada. Feche o Arduino IDE ou o Monitor Serial.")
            raise
        return dev, ok

    def _attach(self, port):
        self.port = port
        self._set("checking", f"Encontrei algo na {port}. Verificando...")
        try:
            dev, ok = self._open(port)
        except PermissionError as e:
            self._bad[port] = time.time() + 8
            self._set("error", str(e))
            return
        except Exception as e:
            self._bad[port] = time.time() + 15
            self.log(f"Não consegui abrir {port}: {e}")
            self._set("waiting")
            return
        expected = F.expected_hash(self.c.s)
        if ok and dev.hello and dev.hello.get("hash") == expected:
            self.device = dev
            self.c.on_connect(dev)
            self._set("ready", f"Conectado na {port}")
            return
        dev.close()
        time.sleep(0.4)
        self._program(port)

    def _program(self, port):
        self.progress, self.stage, self.logs = 0.02, "Preparando", []
        self._set("programming", f"Programando o Arduino na {port}")
        done = threading.Event()

        def creep():  # a gravacao nao informa progresso: avancamos devagar
            while not done.is_set():
                if self.progress >= 0.62:
                    self.progress = min(0.97, self.progress + 0.006)
                elif self.progress >= 0.15:
                    self.progress = min(0.53, self.progress + 0.003)
                time.sleep(0.1)
        threading.Thread(target=creep, daemon=True).start()
        try:
            ok = F.upload_fw(self.c.s, port, self.log)
        finally:
            done.set()
        if not ok:
            self._bad[port] = time.time() + 20
            self._set("error", "Não consegui programar o Arduino. Veja o registro abaixo, confira o cabo e tente de novo.")
            return
        self.progress, self.stage = 1.0, "Gravado!"
        time.sleep(1.5)
        try:
            dev, ok = self._open(port, wait=6.0)
        except Exception as e:
            self._set("error", f"Gravei, mas não consegui reconectar: {e}")
            return
        if not ok:
            dev.close()
            self._bad[port] = time.time() + 20
            self._set("error", "Gravei o firmware, mas o Arduino não respondeu. Confira a velocidade (baud) e o shield.")
            return
        self.device = dev
        self.c.on_connect(dev)
        self._set("done", "Pronto!")


class Companion:
    def __init__(self, settings):
        self.s = settings
        self.pet = PetState(settings.get("pet_name", "PIXO"), lang_short(settings),
                            int(settings.get("decay_seconds", 90)))
        self.pet.load(PET_SAVE)
        self.brain = Brain(settings)
        self.player = voice.PcPlayer()
        self.mic = voice.PcMic()
        self.chat = []
        self.status = ""
        self.busy = False
        self.listening = None  # "pc" ou "arduino"
        self.talk_until = 0.0
        self.dev = None
        self.mgr = None
        self._last_save = time.time()

    def start(self):
        self.player.init()
        self.mgr = DeviceManager(self)

    def shutdown(self):
        self.pet.save(PET_SAVE)
        if self.mgr:
            self.mgr.stop()

    def apply_settings(self):
        self.pet.name = self.s.get("pet_name", "PIXO")
        self.pet.lang = lang_short(self.s)
        self.pet.decay_seconds = int(self.s.get("decay_seconds", 90))
        self.brain.s = self.s
        if self.dev:
            self.dev.set_name(self.pet.name)
            self.dev.set_volume(int(self.s.get("volume", 85)))

    # ------------------------------------------------------------ tempo
    def tick(self, now_ms):
        self.pet.talking = time.time() < self.talk_until or (self.player.busy() and self.status == "falando")
        if self.status == "falando" and time.time() > self.talk_until and not self.player.busy() \
                and not (self.dev and self.dev.playing):
            self.status = ""
        self.pet.update(now_ms)
        if time.time() - self._last_save > 60:
            self._last_save = time.time()
            self.pet.save(PET_SAVE)

    def add_chat(self, who, text):
        self.chat.append((who, text, time.time()))
        self.chat = self.chat[-80:]

    # ------------------------------------------------------------ arduino
    def on_connect(self, dev):
        self.dev = dev
        dev.set_name(self.pet.name)
        dev.set_volume(int(self.s.get("volume", 85)))
        if dev.stats:
            self._sync_stats(dev.stats)
        self.add_chat("sistema", f"Arduino conectado na {dev.port}.")

    def on_disconnect(self):
        if self.dev:
            self.add_chat("sistema", "Arduino desconectado. O pet continua aqui no PC.")
        self.dev = None

    def _sync_stats(self, s):
        p = self.pet
        p.hunger, p.happy, p.energy, p.clean = s["hunger"], s["happy"], s["energy"], s["clean"]
        p.sleeping = bool(s["sleeping"])
        if "age_min" in s:
            p.age_min = s["age_min"]

    def on_device_event(self, kind, data):
        if kind == "stats" or kind == "hello":
            self._sync_stats(data)
        elif kind == "action":
            names = A.ACTIONS + ["pet"]
            name = names[data] if data < len(names) else "?"
            self.pet.events.append(name)
            if name in ("feed", "play", "clean", "sleep", "wake", "pet"):
                self.pet.action(name)
        elif kind == "rec_start":
            self.listening = "arduino"
            self.status = "ouvindo"
            self.pet.play(A.ANIM_INDEX["listening"], 16000)
            if not self.s.get("device_mic", True):
                self.mic.start()
        elif kind == "rec_end":
            self.listening = None
            if self.s.get("device_mic", True):
                pcm, rate = voice.ulaw_to_pcm16(data), 8000
            else:
                pcm, rate = self.mic.stop(), voice.PcMic.RATE
            threading.Thread(target=self._understand, args=(pcm, rate), daemon=True).start()
        elif kind == "abort":
            self.player.stop()
            self.talk_until = 0
            self.status = ""

    # ------------------------------------------------------------ acoes
    def do_action(self, name):
        if self.dev:  # o Arduino executa e devolve o evento (ai o pet do PC copia)
            self.dev.action(ACT_ID[name])
        else:
            self.pet.action(name)

    # ------------------------------------------------------------ microfone do PC
    def start_listen(self):
        if self.busy or self.listening:
            return
        if not self.mic.start():
            self.add_chat("sistema", f"Não consegui abrir o microfone do PC: {self.mic.error}")
            return
        self.listening = "pc"
        self.status = "ouvindo"
        self.pet.play(A.ANIM_INDEX["listening"], 16000)
        if self.dev:
            self.dev.anim(A.ANIM_INDEX["listening"], 16)

    def stop_listen(self):
        if self.listening != "pc":
            return
        self.listening = None
        pcm = self.mic.stop()
        threading.Thread(target=self._understand, args=(pcm, voice.PcMic.RATE), daemon=True).start()

    def _understand(self, pcm, rate):
        self.status = "entendendo"
        self._show_anim("thinking", 20)
        try:
            text = voice.transcribe(pcm, rate, self.s)
        except Exception as e:
            text = ""
            self.add_chat("sistema", f"Falha no reconhecimento de voz: {str(e)[:120]}")
        if not text:
            self.status = ""
            self._show_anim("confused", 3)
            self.add_chat("sistema", "Não entendi o que você falou. Segure o botão e fale mais perto do microfone.")
            return
        self._conversation(text)

    # ------------------------------------------------------------ conversa
    def send_text(self, text):
        text = text.strip()
        if not text or self.busy:
            return False
        threading.Thread(target=self._conversation, args=(text,), daemon=True).start()
        return True

    def _show_anim(self, name, seconds):
        i = A.ANIM_INDEX[name]
        self.pet.play(i, int(seconds * 1000))
        if self.dev:
            self.dev.anim(i, seconds)

    def _conversation(self, text):
        self.busy = True
        try:
            self.add_chat("voce", text)
            self.status = "pensando"
            self._show_anim("thinking", 30)
            p = self.pet
            state = {"hunger": p.hunger, "happy": p.happy, "energy": p.energy, "clean": p.clean,
                     "sleeping": p.sleeping, "events": p.events[-3:]}
            p.events.clear()
            try:
                data = self.brain.reply(text, state)
            except Exception as e:
                import anthropic
                self.status = ""
                self._show_anim("confused", 3)
                if isinstance(e, anthropic.AuthenticationError):
                    msg = "A chave do Claude foi recusada. Confira ou troque em Configurações."
                elif isinstance(e, anthropic.APIConnectionError):
                    msg = "Sem conexão com o Claude. Confira a internet."
                elif isinstance(e, anthropic.RateLimitError):
                    msg = "Muitas mensagens seguidas. Espere alguns segundos e tente de novo."
                else:
                    msg = f"Claude não respondeu: {str(e)[:160]}"
                self.add_chat("sistema", msg)
                return
            speech_text = data["speech"].strip()
            if data["action"] != "none":
                self.do_action(data["action"])
            if data["mood_change"]:
                p.happy = clamp(p.happy + data["mood_change"])
                if self.dev:
                    self.dev.set_stats(p.hunger, p.happy, p.energy, p.clean)
            self.status = "preparando voz"
            try:
                sp = voice.tts(speech_text, self.s)
            except Exception as e:
                sp = None
                self.add_chat("sistema", f"Sem voz agora ({str(e)[:80]}). Mostrando só o texto.")
            dur = sp.duration if sp else max(2.0, len(speech_text) / 14)
            anim_id = A.ANIM_INDEX[data["animation"]]
            hold = dur + 1.5
            p.play(anim_id, int(hold * 1000))
            p.say(speech_text, int(dur * 1000))
            self.add_chat("pet", speech_text)
            out = self.s.get("audio_output", "arduino")
            if self.dev:
                self.dev.anim(anim_id, math.ceil(hold))
                self.dev.text(speech_text, int(dur * 1000))
            self.status = "falando"
            self.talk_until = time.time() + dur
            if sp:
                to_dev = self.dev is not None and out in ("arduino", "both")
                to_pc = self.dev is None or out in ("pc", "both")
                if to_pc:
                    self.player.play(sp)
                if to_dev:
                    self.dev.play_audio(sp.device_audio)
        finally:
            self.busy = False
