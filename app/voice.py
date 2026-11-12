"""Voz do pet: fala (TTS gratuito), escuta (STT gratuito) e microfone do PC."""
import asyncio
import io
import struct
import threading
import time
import wave

import numpy as np

# ------------------------------------------------------------------ u-law
def _ulaw_table():
    tab = np.zeros(256, dtype=np.int16)
    for i in range(256):
        u = ~i & 0xFF
        sign = u & 0x80
        exp = (u >> 4) & 0x07
        mant = u & 0x0F
        s = ((mant << 3) + 0x84) << exp
        s -= 0x84
        tab[i] = -s if sign else s
    return tab


ULAW = _ulaw_table()


def ulaw_to_pcm16(data):
    return ULAW[np.frombuffer(data, dtype=np.uint8)]


def resample(pcm, src, dst):
    if src == dst or len(pcm) == 0:
        return pcm.astype(np.int16)
    n = int(len(pcm) * dst / src)
    x = np.linspace(0, len(pcm) - 1, n)
    return np.interp(x, np.arange(len(pcm)), pcm.astype(np.float32)).astype(np.int16)


def wav_bytes(pcm16, rate):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16.astype(np.int16).tobytes())
    return b.getvalue()


def wav8_for_device(pcm16, rate):
    """WAV 8 kHz 8 bits (leve o bastante para a serial do Uno)."""
    p = resample(pcm16, rate, 8000)
    u8 = ((p.astype(np.int32) >> 8) + 128).clip(0, 255).astype(np.uint8)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(u8.tobytes())
    return b.getvalue()


# ------------------------------------------------------------------ TTS
class Speech:
    """Resultado de uma fala: audio pronto para PC e para o Arduino."""

    def __init__(self, pc_audio, pc_hint, device_audio, duration):
        self.pc_audio = pc_audio
        self.pc_hint = pc_hint
        self.device_audio = device_audio
        self.duration = duration


def tts(text, s):
    engine = s.get("tts_engine", "edge")
    if engine == "off" or not text.strip():
        return None
    if engine == "edge":
        try:
            return _tts_edge(text, s)
        except Exception as e:
            print("edge-tts falhou, usando voz do Windows:", e)
    return _tts_windows(text, s)


def _tts_edge(text, s):
    import edge_tts

    async def run():
        com = edge_tts.Communicate(text, s.get("tts_voice", "pt-BR-FranciscaNeural"),
                                   rate=s.get("tts_rate", "+0%"), pitch=s.get("tts_pitch", "+0Hz"))
        out = bytearray()
        async for ch in com.stream():
            if ch["type"] == "audio":
                out.extend(ch["data"])
        return bytes(out)

    mp3 = asyncio.run(run())
    if not mp3:
        raise RuntimeError("audio vazio")
    dur = len(mp3) / 6000.0  # edge-tts entrega MP3 mono 48 kbps
    return Speech(mp3, "mp3", mp3, dur)


def _tts_windows(text, s):
    import os
    import tempfile
    import pyttsx3
    eng = pyttsx3.init()
    lang = s.get("language", "pt-BR").lower()
    for v in eng.getProperty("voices"):
        meta = (v.id + " " + str(getattr(v, "languages", ""))).lower()
        if lang.replace("-", "_") in meta or lang in meta or lang[:2] in v.name.lower():
            eng.setProperty("voice", v.id)
            break
    path = os.path.join(tempfile.gettempdir(), f"pet_tts_{int(time.time()*1000)}.wav")
    eng.save_to_file(text, path)
    eng.runAndWait()
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
        sw = w.getsampwidth()
        ch = w.getnchannels()
    os.remove(path)
    pcm = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.uint8)
    if sw == 1:
        pcm = (pcm.astype(np.int16) - 128) << 8
    if ch == 2:
        pcm = pcm.reshape(-1, 2).mean(axis=1).astype(np.int16)
    return Speech(wav_bytes(pcm, rate), "wav", wav8_for_device(pcm, rate), len(pcm) / rate)


def list_edge_voices(prefix):
    import edge_tts
    voices = asyncio.run(edge_tts.list_voices())
    return sorted(v["ShortName"] for v in voices if v["ShortName"].startswith(prefix))


# ------------------------------------------------------------------ playback no PC
class PcPlayer:
    def __init__(self):
        self.ok = False
        self.busy_until = 0

    def init(self):
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000)
            self.ok = True
        except Exception as e:
            print("Sem audio no PC:", e)

    def play(self, speech):
        if not self.ok or not speech:
            return
        import pygame
        try:
            pygame.mixer.music.load(io.BytesIO(speech.pc_audio), speech.pc_hint)
            pygame.mixer.music.play()
            self.busy_until = time.time() + speech.duration
        except Exception as e:
            print("Falha ao tocar:", e)

    def stop(self):
        if self.ok:
            import pygame
            pygame.mixer.music.stop()
        self.busy_until = 0

    def busy(self):
        if not self.ok:
            return False
        import pygame
        return pygame.mixer.music.get_busy()


# ------------------------------------------------------------------ microfone do PC
class PcMic:
    RATE = 16000

    def __init__(self):
        self.frames = []
        self.stream = None
        self.level = 0.0
        self.error = ""

    def start(self):
        import sounddevice as sd
        self.frames = []
        try:
            self.stream = sd.InputStream(samplerate=self.RATE, channels=1, dtype="int16", callback=self._cb)
            self.stream.start()
            return True
        except Exception as e:
            self.error = str(e)
            self.stream = None
            return False

    def _cb(self, indata, frames, t, status):
        self.frames.append(indata.copy())
        self.level = float(np.abs(indata).mean()) / 3000.0

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.level = 0
        if not self.frames:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(self.frames).reshape(-1).astype(np.int16)


# ------------------------------------------------------------------ STT
_whisper = None
_whisper_lock = threading.Lock()


def transcribe(pcm16, rate, s):
    """Converte fala em texto. Retorna '' se nao entendeu."""
    if len(pcm16) < rate * 0.3:
        return ""
    if np.abs(pcm16).max() < 300:
        return ""
    engine = s.get("stt_engine", "google")
    lang = s.get("language", "pt-BR")
    if engine == "whisper":
        try:
            return _stt_whisper(pcm16, rate, s, lang)
        except ImportError:
            print("faster-whisper nao instalado; usando Google.")
    import speech_recognition as sr
    pcm16 = _normalize(pcm16)
    audio = sr.AudioData(pcm16.astype(np.int16).tobytes(), rate, 2)
    try:
        return sr.Recognizer().recognize_google(audio, language=lang)
    except sr.UnknownValueError:
        return ""


def _normalize(pcm):
    peak = max(1, int(np.abs(pcm).max()))
    gain = min(8.0, 20000.0 / peak)
    return (pcm.astype(np.float32) * gain).clip(-32767, 32767).astype(np.int16)


def _stt_whisper(pcm16, rate, s, lang):
    global _whisper
    from faster_whisper import WhisperModel
    with _whisper_lock:
        if _whisper is None:
            _whisper = WhisperModel(s.get("whisper_model", "base"), device="cpu", compute_type="int8")
    audio = resample(_normalize(pcm16), rate, 16000).astype(np.float32) / 32768.0
    segs, _ = _whisper.transcribe(audio, language=lang.split("-")[0])
    return " ".join(x.text.strip() for x in segs).strip()
