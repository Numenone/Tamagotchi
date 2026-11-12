"""Configurações do projeto (salvas em settings.json na pasta do projeto)."""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(ROOT, "settings.json")
DATA_DIR = os.path.join(ROOT, "data")
FIRMWARE_DIR = os.path.join(ROOT, "firmware", "tamagotchi")
TOOLS_DIR = os.path.join(ROOT, "tools")

DEFAULTS = {
    # Pet
    "pet_name": "PIXO",
    "language": "pt-BR",
    "personality": "Um bichinho virtual fofo, curioso e brincalhao que adora aprender coisas novas com o dono.",
    "decay_seconds": 90,
    # Claude
    "anthropic_api_key": "",
    "claude_model": "claude-opus-5-5",
    "claude_effort": "low",
    "history_turns": 10,
    # Voz
    "tts_engine": "edge",
    "tts_voice": "pt-BR-FranciscaNeural",
    "tts_rate": "+5%",
    "tts_pitch": "+25Hz",
    "stt_engine": "google",
    "whisper_model": "base",
    "device_mic": True,
    "audio_output": "arduino",
    "volume": 85,
    # Arduino / conexao
    "serial_port": "",
    "baud": 250000,
    "board_fqbn": "arduino:avr:uno",
    # Display: ST7735 (TFT colorida 0.96" 80x160), SSD1306 ou SH1106 (OLED I2C)
    "oled_driver": "ST7735",
    "tft_cs": 10,
    "tft_dc": 4,
    "tft_rst": 5,
    "tft_blk": 3,
    "tft_xofs": 1,
    "tft_yofs": 26,
    "tft_invert": True,
    "tft_bgr": True,
    "tft_color": 0,
    "oled_addr": "0x3C",
    "oled_flip": False,
    "oled_contrast": 207,
    # Botoes
    "pin_btn_a": "A0",
    "pin_btn_b": "A1",
    "pin_btn_c": "A2",
    # Shield VS1053 (padrao Geeetech)
    "vs_xcs": 6,
    "vs_xdcs": 7,
    "vs_dreq": 2,
    "vs_xreset": 8,
    "sd_cs": 9,
    "rec_gain": 0,
    "rec_maxgain": 4096,
    "rec_line_in": False,
    "vs_midi_fix": False,
}

MODELS = [
    ("claude-opus-5-5", "Claude Opus 5.5 (mais inteligente)"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (equilibrado)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (mais rápido e barato)"),
]
EFFORTS = ["low", "medium", "high"]
LANGUAGES = [("pt-BR", "Português (Brasil)"), ("en-US", "English (US)"), ("es-ES", "Español")]
VOICES = {
    "pt-BR": ["pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural", "pt-BR-AntonioNeural"],
    "en-US": ["en-US-AnaNeural", "en-US-JennyNeural", "en-US-GuyNeural", "en-US-AriaNeural"],
    "es-ES": ["es-ES-ElviraNeural", "es-MX-DaliaNeural", "es-ES-AlvaroNeural"],
}


def load():
    s = copy.deepcopy(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                s.update(json.load(f))
        except (OSError, ValueError):
            pass
    if not s.get("anthropic_api_key"):
        s["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    return s


def save(s):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def lang_short(s):
    return s.get("language", "pt-BR").split("-")[0]


os.makedirs(DATA_DIR, exist_ok=True)
