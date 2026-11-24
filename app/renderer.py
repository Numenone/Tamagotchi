"""Renderizador 128x64 do pet (espelho exato do firmware render.cpp).

Desenha em um framebuffer monocromatico. O simulador do PC e a galeria
usam isto; o Arduino usa a mesma logica em C++ com os mesmos dados.
"""
from . import sprites as S
from . import animations as A

W, H = 128, 64


def cdiv(a, b):
    """Divisao inteira com truncamento para zero (igual ao C)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


_cache = {}


def fold(s):
    """Remove acentos (a fonte do display so tem ASCII), igual ao que vai para o Arduino."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if ord(c) < 128)


def sprite_pixels(name):
    px = _cache.get(name)
    if px is None:
        rows = S.get_sprite(name)
        px = [(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "#"]
        _cache[name] = (px, len(rows[0]), len(rows))
        px = _cache[name]
    return px


class Frame:
    def __init__(self):
        self.buf = bytearray(W * H)

    def clear(self):
        self.buf[:] = bytes(W * H)

    def px(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            self.buf[y * W + x] = 1

    def blit(self, name, x, y):
        pts, _, _ = sprite_pixels(name)
        for (dx, dy) in pts:
            self.px(x + dx, y + dy)

    def fill(self, x, y, w, h):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy)

    def rect(self, x, y, w, h):
        for xx in range(x, x + w):
            self.px(xx, y)
            self.px(xx, y + h - 1)
        for yy in range(y, y + h):
            self.px(x, yy)
            self.px(x + w - 1, yy)

    def text(self, x, y, s):
        s = fold(s)
        for ch in s:
            c = ord(ch)
            if c < 32 or c > 126:
                c = 63
            base = (c - 32) * 5
            for col in range(5):
                bits = S.FONT_5X7[base + col]
                for r in range(7):
                    if bits & (1 << r):
                        self.px(x + col, y + r)
            x += 6


def text_width(s):
    return len(fold(s)) * 6


def subtitle_x(text, elapsed, duration):
    """Posicao x do texto da legenda (mesma conta do firmware)."""
    text = fold(text)
    w = text_width(text)
    if w <= 124:
        return (128 - w) // 2
    travel = w - 120
    dur = duration if duration > 0 else len(text) * 80
    eff = max(dur - 800, 500)
    e = min(elapsed, eff)
    return 4 - cdiv(travel * e, eff)


def draw_scene(fb, st):
    """st = PetState (ver petsim.py). Desenha a cena completa."""
    fb.clear()
    now = st.now
    if st.stats_screen:
        _draw_stats(fb, st)
        return
    # barra superior: status ou rotulo do menu
    if st.menu_active:
        label = st.menu_label()
        fb.text((128 - text_width(label)) // 2, 0, label)
    else:
        vals = (st.hunger, st.happy, st.energy, st.clean)
        for i, v in enumerate(vals):
            x = i * 32
            fb.blit(A.STATUS_ICONS[i], x, 0)
            fb.rect(x + 9, 1, 21, 5)
            fb.fill(x + 10, 2, v * 19 // 100, 3)

    a = A.ANIMATIONS[st.anim]
    _, _, eyes, mouths, motion, effect, _, _ = a
    t = st.t
    mo = A.MOTIONS[motion]
    mdx, mdy = mo[t % len(mo)]
    ox, oy = S.PET_X + mdx, S.PET_Y + mdy
    fb.blit("body", ox, oy)

    style = eyes[t % len(eyes)]
    if len(eyes) == 1 and style in A.BLINKABLE and (now % 3200) < 140:
        style = "closed"
    l, r, edx, edy = A.EYE_STYLES[style]
    if r is None:
        fb.blit(l, ox + S.EYE_PAIR_POS[0] + edx, oy + S.EYE_PAIR_POS[1] + edy)
    else:
        fb.blit(l, ox + S.EYE_L_POS[0] + edx, oy + S.EYE_L_POS[1] + edy)
        fb.blit(r, ox + S.EYE_R_POS[0] + edx, oy + S.EYE_R_POS[1] + edy)

    if st.talking and len(mouths) == 1:
        m = A.TALK_SEQ[(now // 120) % 4]
    else:
        m = mouths[t % len(mouths)]
    fb.blit(m, ox + S.MOUTH_POS[0], oy + S.MOUTH_POS[1])

    for (icon, pat, x, y, pa, pb, pc) in A.EFFECTS[effect]:
        pos = effect_pos(pat, x, y, pa, pb, pc, t)
        if pos:
            fb.blit(icon, ox + pos[0], oy + pos[1])

    # linha de baixo: menu, legenda ou nome
    if st.menu_active:
        for i, (_, icon, _) in enumerate(A.MENU_ITEMS):
            x = 3 + i * 21
            fb.blit(icon, x, 57)
            if i == st.menu_sel:
                fb.rect(x - 2, 55, 11, 9)
    elif st.subtitle:
        x = subtitle_x(st.subtitle, now - st.subtitle_start, st.subtitle_dur)
        fb.text(x, 57, st.subtitle)
    else:
        n = st.name
        fb.text((128 - text_width(n)) // 2, 57, n)


def effect_pos(pat, x, y, a, b, c, t):
    if pat == "static":
        return (x, y)
    if pat == "blink":
        return (x, y) if (((t + a) >> 1) & 1) == 0 else None
    if pat == "rise":
        return (x, y - ((t * c + b) % a))
    if pat == "fall":
        return (x, y + ((t * c + b) % a))
    if pat == "orbit":
        k = (t + c) & 7
        return (x + cdiv(A.ORBIT_X[k] * a, 8), y + cdiv(A.ORBIT_Y[k] * b, 8))
    if pat == "sides":
        return (x + a, y + b) if (((t + c) >> 1) & 1) else (x, y)
    if pat == "bounce":
        return (x, y - cdiv(A.BOUNCE_T[(t + b) & 7] * a, 8))
    return None


STAT_LABELS = {
    "pt": ("Comida", "Alegria", "Energia", "Higiene", "dormindo"),
    "en": ("Food", "Joy", "Energy", "Clean", "sleeping"),
    "es": ("Comida", "Alegria", "Energia", "Higiene", "durmiendo"),
}


def _draw_stats(fb, st):
    fb.text(0, 0, st.name[:10])
    age = f"{st.age_min // 1440}d{(st.age_min // 60) % 24}h"
    fb.text(128 - text_width(age), 0, age)
    fb.fill(0, 9, 128, 1)
    labels = STAT_LABELS.get(st.lang, STAT_LABELS["pt"])
    vals = (st.hunger, st.happy, st.energy, st.clean)
    for i, v in enumerate(vals):
        y = 12 + i * 11
        fb.blit(A.STATUS_ICONS[i], 0, y)
        fb.text(10, y, labels[i])
        fb.rect(58, y, 46, 7)
        fb.fill(59, y + 1, v * 44 // 100, 5)
        s = str(v)
        fb.text(128 - text_width(s), y, s)
    fb.blit("i_pc", 0, 58)
    fb.text(9, 57, "ok" if st.pc_link else "--")
    if st.sleeping:
        fb.text(128 - text_width(labels[4]), 57, labels[4])
