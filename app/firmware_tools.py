"""Gera o firmware a partir das configuracoes e grava no Arduino via arduino-cli."""
import io
import os
import re
import subprocess
import urllib.request
import zipfile

from . import animations as A
from . import sprites as S
from .settings import FIRMWARE_DIR, TOOLS_DIR, lang_short

CLI_URL = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
CLI_EXE = os.path.join(TOOLS_DIR, "arduino-cli", "arduino-cli.exe")
RX_BUFFER = 256  # buffer serial ampliado (necessario para streaming de audio)

STAT_LABELS = {
    "pt": ("Fome", "Alegria", "Energia", "Higiene", "dormindo", "Sem PC :("),
    "en": ("Food", "Joy", "Energy", "Clean", "sleeping", "No PC :("),
    "es": ("Hambre", "Alegria", "Energia", "Higiene", "durmiendo", "Sin PC :("),
}
MENU_LABELS = {
    "pt": ["Comer", "Brincar", "Banho", "Dormir", "Status", "Falar"],
    "en": ["Feed", "Play", "Bath", "Sleep", "Status", "Talk"],
    "es": ["Comer", "Jugar", "Bano", "Dormir", "Estado", "Hablar"],
}


def cname(name):
    return re.sub(r"[^A-Za-z0-9_]", "_", name.replace("~", "_m"))


def ascii_only(text):
    import unicodedata
    t = unicodedata.normalize("NFKD", text)
    return "".join(c for c in t if 32 <= ord(c) < 127)


# ---------------------------------------------------------------------------
# anim_data.h
# ---------------------------------------------------------------------------
def _used_sprites():
    names = ["body"]
    def add(n):
        if n not in names:
            names.append(n)
    for l, r, _, _ in A.EYE_STYLES.values():
        add(l)
        if r:
            add(r)
    for m in A.MOUTHS + A.TALK_SEQ:
        add(m)
    for comps in A.EFFECTS.values():
        for c in comps:
            add(c[0])
    for n in A.STATUS_ICONS + [m[1] for m in A.MENU_ITEMS] + ["i_pc"]:
        add(n)
    return names


def _pack(rows):
    w, h = len(rows[0]), len(rows)
    out = []
    for r in rows:
        assert len(r) == w, f"linha com largura errada: {r}"
        for bx in range(0, w, 8):
            b = 0
            for i in range(8):
                x = bx + i
                if x < w and r[x] == "#":
                    b |= 0x80 >> i
            out.append(b)
    return w, h, out


def _arr(vals, per_line=16):
    lines = []
    for i in range(0, len(vals), per_line):
        lines.append("  " + ", ".join(str(v) for v in vals[i:i + per_line]) + ",")
    return "\n".join(lines)


def gen_anim_data():
    spr_names = _used_sprites()
    spr_id = {n: i for i, n in enumerate(spr_names)}
    bits, info = [], []
    for n in spr_names:
        w, h, data = _pack(S.get_sprite(n))
        info.append((w, h, len(bits)))
        bits.extend(data)

    eye_names = list(A.EYE_STYLES)
    eye_id = {n: i for i, n in enumerate(eye_names)}
    eyes = []
    for n in eye_names:
        l, r, dx, dy = A.EYE_STYLES[n]
        eyes.append((spr_id[l], spr_id[r] if r else 255, dx, dy, 1 if n in A.BLINKABLE else 0))

    mot_names = list(A.MOTIONS)
    mot_data, mot_tab = [], []
    for n in mot_names:
        seq = A.MOTIONS[n]
        mot_tab.append((len(mot_data) // 2, len(seq)))
        for dx, dy in seq:
            mot_data += [dx, dy]

    eff_names = list(A.EFFECTS)
    comp_data, eff_tab = [], []
    for n in eff_names:
        comps = A.EFFECTS[n]
        eff_tab.append((len(comp_data) // 7, len(comps)))
        for icon, pat, x, y, a, b, c in comps:
            comp_data += [spr_id[icon], A.PATTERNS.index(pat), x, y, a, b, c]

    seq_data, anims = [], []
    for (name, _lbl, e, m, mo, ef, ms, _hint) in A.ANIMATIONS:
        eo = len(seq_data)
        seq_data += [eye_id[x] for x in e]
        mo_ = len(seq_data)
        seq_data += [spr_id[x] for x in m]
        anims.append((eo, len(e), mo_, len(m), mot_names.index(mo), eff_names.index(ef), max(1, min(255, ms // 10))))
    assert len(seq_data) < 256

    o = []
    o.append("// GERADO AUTOMATICAMENTE pelo Tamagotchi Studio. Nao edite a mao.")
    o.append("#pragma once\n#include <avr/pgmspace.h>\n")
    o.append(f"#define BODY_X {S.PET_X}\n#define BODY_Y {S.PET_Y}")
    o.append(f"#define EYE_LX {S.EYE_L_POS[0]}\n#define EYE_LY {S.EYE_L_POS[1]}")
    o.append(f"#define EYE_RX {S.EYE_R_POS[0]}\n#define EYE_RY {S.EYE_R_POS[1]}")
    o.append(f"#define EYE_PX {S.EYE_PAIR_POS[0]}\n#define EYE_PY {S.EYE_PAIR_POS[1]}")
    o.append(f"#define MOUTH_X {S.MOUTH_POS[0]}\n#define MOUTH_Y {S.MOUTH_POS[1]}\n")
    o.append("struct SprInfo { uint8_t w, h; uint16_t ofs; };")
    o.append("struct EyeStyle { uint8_t l, r; int8_t dx, dy; uint8_t blink; };")
    o.append("struct Seq16 { uint16_t ofs; uint8_t len; };")
    o.append("struct Anim { uint8_t eyeOfs, eyeLen, mouthOfs, mouthLen, motion, effect, speed10; };\n")
    for n, i in spr_id.items():
        o.append(f"#define SPR_{cname(n)} {i}")
    o.append(f"\nconst uint8_t SPR_BITS[] PROGMEM = {{\n{_arr(bits)}\n}};")
    o.append("const SprInfo SPR_INFO[] PROGMEM = {\n" + "\n".join(f"  {{{w}, {h}, {ofs}}}," for w, h, ofs in info) + "\n};\n")
    o.append(f"const uint8_t FONT5X7[] PROGMEM = {{\n{_arr(S.FONT_5X7)}\n}};\n")
    o.append(f"#define EYE_CLOSED {eye_id['closed']}")
    o.append("const EyeStyle EYES[] PROGMEM = {\n" + "\n".join(f"  {{{l}, {r}, {dx}, {dy}, {bl}}}," for l, r, dx, dy, bl in eyes) + "\n};\n")
    o.append("const uint8_t TALK_SEQ[4] PROGMEM = {" + ", ".join(str(spr_id[m]) for m in A.TALK_SEQ) + "};")
    o.append("const int8_t MOTION_DATA[] PROGMEM = {\n" + _arr(mot_data) + "\n};")
    o.append("const Seq16 MOTIONS[] PROGMEM = {\n" + "\n".join(f"  {{{a}, {b}}}," for a, b in mot_tab) + "\n};\n")
    for i, p in enumerate(A.PATTERNS):
        o.append(f"#define PAT_{p.upper()} {i}")
    o.append("const int8_t COMP_DATA[] PROGMEM = {\n" + _arr(comp_data, 14) + "\n};")
    o.append("const Seq16 EFFECTS[] PROGMEM = {\n" + "\n".join(f"  {{{a}, {b}}}," for a, b in eff_tab) + "\n};\n")
    o.append("const int8_t ORBIT_X[8] PROGMEM = {" + ", ".join(map(str, A.ORBIT_X)) + "};")
    o.append("const int8_t ORBIT_Y[8] PROGMEM = {" + ", ".join(map(str, A.ORBIT_Y)) + "};")
    o.append("const int8_t BOUNCE_T[8] PROGMEM = {" + ", ".join(map(str, A.BOUNCE_T)) + "};\n")
    o.append("const uint8_t SEQ_DATA[] PROGMEM = {\n" + _arr(seq_data) + "\n};")
    o.append(f"#define ANIM_COUNT {len(anims)}")
    o.append("const Anim ANIMS[] PROGMEM = {\n" + "\n".join(
        "  {" + ", ".join(map(str, a)) + f"}},  // {i} {A.ANIMATIONS[i][0]}" for i, a in enumerate(anims)) + "\n};")
    for i, a in enumerate(A.ANIMATIONS):
        o.append(f"#define ANIM_{a[0].upper()} {i}")
    o.append("\nconst uint8_t STATUS_ICONS[4] PROGMEM = {" + ", ".join(str(spr_id[n]) for n in A.STATUS_ICONS) + "};")
    o.append(f"#define MENU_COUNT {len(A.MENU_ITEMS)}")
    o.append("const uint8_t MENU_ICONS[MENU_COUNT] PROGMEM = {" + ", ".join(str(spr_id[m[1]]) for m in A.MENU_ITEMS) + "};")
    for i, act in enumerate(A.ACTIONS + ["pet"]):
        o.append(f"#define ACT_{act.upper()} {i}")
    return "\n".join(o) + "\n"


# ---------------------------------------------------------------------------
# config.h
# ---------------------------------------------------------------------------
def _pin(v):
    v = str(v).strip().upper()
    return v if v.startswith("A") else str(int(v))


def gen_config(s):
    lang = lang_short(s)
    lbl = STAT_LABELS.get(lang, STAT_LABELS["pt"])
    menu = MENU_LABELS.get(lang, MENU_LABELS["pt"])
    name = ascii_only(s.get("pet_name", "PIXO"))[:12] or "PIXO"
    vol = int(s.get("volume", 85))
    att = max(0, min(200, int((100 - vol) * 1.6)))
    rows = [
        "// GERADO AUTOMATICAMENTE pelo Tamagotchi Studio (TAMAGOTCHI.bat).",
        "// Para mudar, use a aba Configuracoes do Studio e clique em Enviar.",
        "#pragma once",
        f'#define PET_NAME "{name}"',
        f"#define SERIAL_BAUD {int(s.get('baud', 250000))}",
        f"#define DISPLAY_TFT {1 if s.get('oled_driver') == 'ST7735' else 0}",
        f"#define OLED_SH1106 {1 if s.get('oled_driver') == 'SH1106' else 0}",
        f"#define TFT_PIN_CS {int(s.get('tft_cs', 10))}",
        f"#define TFT_PIN_DC {int(s.get('tft_dc', 4))}",
        f"#define TFT_PIN_RST {int(s.get('tft_rst', 5))}",
        f"#define TFT_PIN_BLK {int(s.get('tft_blk', 3))}",
        f"#define TFT_XOFS {int(s.get('tft_xofs', 1))}",
        f"#define TFT_YOFS {int(s.get('tft_yofs', 26))}",
        f"#define TFT_INVERT {1 if s.get('tft_invert', True) else 0}",
        f"#define TFT_BGR {1 if s.get('tft_bgr', True) else 0}",
        f"#define TFT_FLIP {1 if s.get('oled_flip') else 0}",
        f"#define TFT_PET_COLOR {int(s.get('tft_color', 0))}",
        f"#define OLED_I2C_ADDR {s.get('oled_addr', '0x3C')}",
        f"#define OLED_FLIP {1 if s.get('oled_flip') else 0}",
        f"#define OLED_CONTRAST {int(s.get('oled_contrast', 207))}",
        f"#define PIN_BTN_A {_pin(s.get('pin_btn_a', 'A0'))}",
        f"#define PIN_BTN_B {_pin(s.get('pin_btn_b', 'A1'))}",
        f"#define PIN_BTN_C {_pin(s.get('pin_btn_c', 'A2'))}",
        f"#define VS_PIN_XCS {int(s.get('vs_xcs', 6))}",
        f"#define VS_PIN_XDCS {int(s.get('vs_xdcs', 7))}",
        f"#define VS_PIN_DREQ {int(s.get('vs_dreq', 2))}",
        f"#define VS_PIN_XRESET {int(s.get('vs_xreset', 8))}",
        f"#define SD_PIN_CS {int(s.get('sd_cs', 9))}",
        f"#define VS_VOLUME {att}",
        f"#define VS_REC_GAIN {int(s.get('rec_gain', 0))}",
        f"#define VS_REC_MAXGAIN {int(s.get('rec_maxgain', 4096))}",
        f"#define VS_REC_LINE_IN {1 if s.get('rec_line_in') else 0}",
        f"#define VS_MIDI_FIX {1 if s.get('vs_midi_fix') else 0}",
        f"#define DECAY_SECONDS {int(s.get('decay_seconds', 90))}",
        f'#define LBL_HUNGER "{lbl[0]}"',
        f'#define LBL_HAPPY "{lbl[1]}"',
        f'#define LBL_ENERGY "{lbl[2]}"',
        f'#define LBL_CLEAN "{lbl[3]}"',
        f'#define LBL_SLEEPING "{lbl[4]}"',
        f'#define LBL_NOPC "{lbl[5]}"',
        "#define MENU_LABELS " + ", ".join(f'"{m}"' for m in menu),
    ]
    return "\n".join(rows) + "\n"


def expected_hash(s):
    """Impressao digital do firmware: muda se config, animacoes ou codigo mudarem."""
    import zlib
    h = zlib.crc32(gen_anim_data().encode())
    h = zlib.crc32(gen_config(s).encode(), h)
    for fn in ("tamagotchi.ino", "oled.h", "tft.h", "vs1053.h"):
        p = os.path.join(FIRMWARE_DIR, fn)
        if os.path.exists(p):
            with open(p, "rb") as f:
                h = zlib.crc32(f.read().replace(b"\r\n", b"\n"), h)
    return h & 0xFFFFFFFF or 1


def write_firmware_files(s, log=print):
    os.makedirs(FIRMWARE_DIR, exist_ok=True)
    with open(os.path.join(FIRMWARE_DIR, "anim_data.h"), "w", encoding="ascii", newline="\n") as f:
        f.write(gen_anim_data())
    h = expected_hash(s)
    with open(os.path.join(FIRMWARE_DIR, "config.h"), "w", encoding="ascii", newline="\n") as f:
        f.write(gen_config(s) + f"#define FW_HASH 0x{h:08X}UL\n")
    log("config.h e anim_data.h gerados a partir das configuracoes.")
    return h


# ---------------------------------------------------------------------------
# arduino-cli
# ---------------------------------------------------------------------------
def _run(args, log, timeout=900):
    log("> arduino-cli " + " ".join(args))
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        p = subprocess.Popen([CLI_EXE] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", creationflags=flags)
    except OSError as e:
        log(f"ERRO ao executar arduino-cli: {e}")
        return 1, ""
    out = []
    for line in p.stdout:
        line = line.rstrip()
        out.append(line)
        if line:
            log(line)
    p.wait(timeout=timeout)
    return p.returncode, "\n".join(out)


def ensure_cli(log=print):
    if not os.path.exists(CLI_EXE):
        log("Baixando arduino-cli (so na primeira vez)...")
        os.makedirs(os.path.dirname(CLI_EXE), exist_ok=True)
        with urllib.request.urlopen(CLI_URL, timeout=120) as r:
            data = r.read()
        zipfile.ZipFile(io.BytesIO(data)).extractall(os.path.dirname(CLI_EXE))
        log("arduino-cli instalado.")
    rc, out = _run(["core", "list"], log)
    if "arduino:avr" not in out:
        log("Instalando o suporte a placas AVR (Uno/Nano/Mega)...")
        _run(["core", "update-index"], log)
        rc, _ = _run(["core", "install", "arduino:avr"], log)
        if rc != 0:
            return False
    return True


def list_ports():
    try:
        from serial.tools import list_ports as lp
        # VIDs USB de Arduino e dos chips USB-serial usados nos clones
        known = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4, 0x067B, 0x239A}
        ports = []
        for p in lp.comports():
            desc = p.description or ""
            score = 0
            if p.vid is not None:  # so portas USB (ignora COM1, Bluetooth etc.)
                score = 2 if p.vid in known or "arduino" in desc.lower() else 1
            ports.append((p.device, desc, score))
        ports.sort(key=lambda x: -x[2])
        return ports
    except Exception:
        return []


def compile_fw(s, log=print):
    write_firmware_files(s, log)
    if not ensure_cli(log):
        return False
    fqbn = s.get("board_fqbn", "arduino:avr:uno")
    rc, out = _run(["compile", "--fqbn", fqbn, "--build-property",
                    f"build.extra_flags=-DSERIAL_RX_BUFFER_SIZE={RX_BUFFER}", FIRMWARE_DIR], log)
    if rc == 0:
        log("Compilado com sucesso!")
    else:
        log("ERRO na compilacao (veja acima).")
    return rc == 0


# ---------------------------------------------------------------------------
# ESP32: ponte sem fio (o ESP32 faz o papel do PC, ligado na serial do Uno)
# ---------------------------------------------------------------------------
ESP32_DIR = os.path.join(os.path.dirname(FIRMWARE_DIR), "esp32_bridge")
ESP32_URL = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
ESP32_FQBN = "esp32:esp32:esp32:PartitionScheme=huge_app"

ESP32_MSGS = {
    "pt": ("Nao entendi :(", "Sem Wi-Fi", "Wi-Fi ok!", "Erro no Claude",
           "Hmm, disso eu prefiro não falar. Vamos brincar de outra coisa?"),
    "en": ("Didn't get that :(", "No Wi-Fi", "Wi-Fi ok!", "Claude error",
           "Hmm, I'd rather not talk about that. Let's play something else?"),
    "es": ("No entendi :(", "Sin Wi-Fi", "Wi-Fi ok!", "Error de Claude",
           "Mmm, de eso prefiero no hablar. ¿Jugamos a otra cosa?"),
}


def c_string(text):
    """Literal de C seguro para qualquer texto (aspas, barras e acentos)."""
    out = []
    for b in str(text).encode("utf-8"):
        if b in (0x22, 0x5C):
            out.append("\\" + chr(b))
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\{b:03o}")
    return '"' + "".join(out) + '"'


def esp32_missing(s):
    falta = []
    if not s.get("wifi_ssid", "").strip():
        falta.append("o nome do Wi-Fi")
    if not s.get("anthropic_api_key", "").strip():
        falta.append("a chave do Claude")
    if not s.get("google_api_key", "").strip():
        falta.append("a chave do Google Cloud")
    return falta


def gen_esp32_config(s):
    lang = lang_short(s)
    msgs = ESP32_MSGS.get(lang, ESP32_MSGS["pt"])
    name = ascii_only(s.get("pet_name", "PIXO"))[:12] or "PIXO"
    vol = int(s.get("volume", 85))
    att = max(0, min(200, int((100 - vol) * 1.6)))
    rate = int(str(s.get("tts_rate", "+5%")).replace("%", "").replace("+", "") or 0)
    model = s.get("claude_model", "claude-opus-5-5")
    acts = A.ACTIONS + ["pet"]
    rows = [
        "// GERADO AUTOMATICAMENTE pelo Tamagotchi Studio. Nao edite a mao.",
        "#pragma once",
        f"#define PET_NAME {c_string(name)}",
        f"#define LANG_CODE {c_string(s.get('language', 'pt-BR'))}",
        f"#define UNO_BAUD {int(s.get('baud', 250000))}",
        f"#define UNO_VOLUME_ATT {att}",
        f"#define CLAUDE_MODEL {c_string(model)}",
        f"#define CLAUDE_EFFORT {c_string(s.get('claude_effort', 'low'))}",
        f"#define CLAUDE_FALLBACK {1 if model in ('claude-opus-5-5', 'claude-sonnet-5-5') else 0}",
        f"#define HISTORY_TURNS {int(s.get('history_turns', 10))}",
        f"#define GTTS_VOICE {c_string(s.get('gtts_voice', ''))}",
        f"#define GTTS_GENDER {c_string(s.get('gtts_gender', 'FEMALE'))}",
        f"#define GTTS_PITCH {float(s.get('gtts_pitch', 4.0)):.1f}",
        f"#define GTTS_RATE {max(0.5, min(2.0, 1 + rate / 100)):.2f}",
        f"#define ANIM_COUNT {len(A.ANIMATIONS)}",
        "static const char* const ANIM_NAMES[ANIM_COUNT] = {"
        + ", ".join(c_string(a[0]) for a in A.ANIMATIONS) + "};",
        f"#define ACT_COUNT {len(acts)}",
        "static const char* const ACT_NAMES[ACT_COUNT] = {" + ", ".join(c_string(a) for a in acts) + "};",
    ]
    for anim in ("thinking", "confused", "happy", "talking", "listening"):
        rows.append(f"#define ANIM_{anim.upper()} {A.ANIM_INDEX[anim]}")
    for key, val in zip(("NOT_UNDERSTOOD", "NO_WIFI", "WIFI_OK", "CLAUDE_ERR", "REFUSAL"), msgs):
        rows.append(f"#define MSG_{key} {c_string(val)}")
    return "\n".join(rows) + "\n"


def gen_esp32_prompt(s):
    import json
    from .brain import SCHEMA, build_system
    system = build_system(s)
    assert ")TAMA" not in system
    return ("// GERADO AUTOMATICAMENTE pelo Tamagotchi Studio (mesmo prompt do cerebro do PC).\n"
            "#pragma once\n"
            f'static const char SYSTEM_PROMPT[] = R"TAMA({system})TAMA";\n'
            f"static const char SCHEMA_JSON[] = {c_string(json.dumps(SCHEMA, separators=(',', ':')))};\n")


def gen_esp32_secrets(s):
    return ("// GERADO pelo Tamagotchi Studio. Contem as suas chaves: NAO compartilhe nem suba no GitHub.\n"
            "#pragma once\n"
            f"#define WIFI_SSID {c_string(s.get('wifi_ssid', '').strip())}\n"
            f"#define WIFI_PASS {c_string(s.get('wifi_password', ''))}\n"
            f"#define ANTHROPIC_API_KEY {c_string(s.get('anthropic_api_key', '').strip())}\n"
            f"#define GOOGLE_API_KEY {c_string(s.get('google_api_key', '').strip())}\n")


def write_esp32_files(s, log=print, with_secrets=True):
    os.makedirs(ESP32_DIR, exist_ok=True)
    files = {"bridge_config.h": gen_esp32_config(s), "prompt.h": gen_esp32_prompt(s)}
    if with_secrets:
        files["secrets.h"] = gen_esp32_secrets(s)
    for fn, body in files.items():
        with open(os.path.join(ESP32_DIR, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    log("Arquivos do ESP32 gerados a partir das configuracoes.")


def ensure_esp32_core(log=print):
    if not ensure_cli(log):
        return False
    rc, out = _run(["core", "list"], log)
    if "esp32:esp32" not in out:
        log("Instalando o suporte ao ESP32 (so na primeira vez, e grande: pode levar uns 10 minutos)...")
        _run(["core", "update-index", "--additional-urls", ESP32_URL], log)
        rc, _ = _run(["core", "install", "esp32:esp32", "--additional-urls", ESP32_URL], log, timeout=3600)
        if rc != 0:
            return False
    rc, out = _run(["lib", "list", "ArduinoJson"], log)
    if "ArduinoJson" not in out:
        log("Instalando a biblioteca ArduinoJson...")
        rc, _ = _run(["lib", "install", "ArduinoJson"], log)
        if rc != 0:
            return False
    return True


def compile_esp32(s, log=print, with_secrets=True):
    write_esp32_files(s, log, with_secrets)
    if not ensure_esp32_core(log):
        log("ERRO ao instalar o suporte ao ESP32 (confira a internet).")
        return False
    rc, _ = _run(["compile", "--fqbn", ESP32_FQBN, ESP32_DIR], log, timeout=1800)
    log("Compilado com sucesso!" if rc == 0 else "ERRO na compilacao do ESP32 (veja acima).")
    return rc == 0


def upload_esp32(s, port, log=print):
    falta = esp32_missing(s)
    if falta:
        log("Falta preencher: " + ", ".join(falta) + ".")
        return False
    if not port:
        log("Escolha a porta USB do ESP32.")
        return False
    if not compile_esp32(s, log):
        return False
    log(f"Enviando para o ESP32 na {port}... (se travar em 'Connecting', segure o botao BOOT da placa)")
    rc, _ = _run(["upload", "-p", port, "--fqbn", ESP32_FQBN, ESP32_DIR], log)
    if rc == 0:
        log("Pronto! ESP32 gravado. Ligue ele no Uno e o pet conversa sem o PC.")
    else:
        log("ERRO no envio. Confira a porta, feche o Monitor Serial e tente segurando o botao BOOT.")
    return rc == 0


def upload_fw(s, port, log=print):
    if not compile_fw(s, log):
        return False
    if not port:
        log("Nenhuma porta COM escolhida. Conecte o Arduino no USB e clique em Atualizar portas.")
        return False
    fqbn = s.get("board_fqbn", "arduino:avr:uno")
    log(f"Enviando para {port}... (os LEDs RX/TX do Arduino vao piscar)")
    rc, _ = _run(["upload", "-p", port, "--fqbn", fqbn, FIRMWARE_DIR], log)
    if rc == 0:
        log("Pronto! Firmware gravado. O pet deve aparecer no display em 2 segundos.")
    else:
        log("ERRO no envio. Feche o Monitor Serial/Arduino IDE e confira a porta COM.")
    return rc == 0
