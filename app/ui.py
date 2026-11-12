"""Componentes visuais do Tamagotchi Studio (pygame)."""
import math

import numpy as np
import pygame

from . import renderer as R
from . import sprites as S

W, H = 1240, 720

C = {
    "bg": (24, 20, 44),
    "bg2": (32, 27, 58),
    "panel": (41, 35, 72),
    "panel2": (52, 45, 90),
    "line": (74, 64, 122),
    "text": (243, 239, 255),
    "muted": (168, 158, 205),
    "pink": (255, 111, 181),
    "pink2": (255, 160, 205),
    "cyan": (103, 232, 249),
    "yellow": (255, 209, 102),
    "green": (126, 224, 129),
    "red": (255, 107, 107),
    "orange": (255, 159, 67),
    "oled_on": (125, 235, 255),
    "oled_off": (6, 12, 22),
    "shadow": (12, 9, 24),
}

_fonts = {}


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    f = _fonts.get(key)
    if f is None:
        if mono:
            f = pygame.font.SysFont("consolas", size)
        else:
            f = pygame.font.SysFont("segoeuisemibold" if bold else "segoeui", size)
            if bold:
                f.set_bold(False)
        _fonts[key] = f
    return f


def text(surf, s, pos, size=18, color=None, bold=False, align="left", mono=False):
    color = color or C["text"]
    img = font(size, bold, mono).render(str(s), True, color)
    r = img.get_rect()
    if align == "center":
        r.center = pos
    elif align == "right":
        r.topright = pos
    elif align == "midleft":
        r.midleft = pos
    else:
        r.topleft = pos
    surf.blit(img, r)
    return r


def wrap(s, size, width, bold=False):
    f = font(size, bold)
    out = []
    for para in str(s).split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            t = (line + " " + w).strip()
            if f.size(t)[0] <= width:
                line = t
            else:
                if line:
                    out.append(line)
                line = w
        out.append(line)
    return out


def text_block(surf, s, pos, width, size=18, color=None, bold=False, spacing=4):
    x, y = pos
    lh = font(size, bold).get_linesize() + spacing - 4
    for line in wrap(s, size, width, bold):
        text(surf, line, (x, y), size, color, bold)
        y += lh
    return y


def panel(surf, rect, color=None, radius=16, border=None, shadow=True):
    rect = pygame.Rect(rect)
    if shadow:
        pygame.draw.rect(surf, C["shadow"], rect.move(0, 4), border_radius=radius)
    pygame.draw.rect(surf, color or C["panel"], rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, 2, border_radius=radius)
    return rect


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------------------------------------------------------------- icones pixel
_icon_cache = {}


def icon(name, scale=3, color=None):
    color = color or C["text"]
    key = (name, scale, color)
    img = _icon_cache.get(key)
    if img is None:
        rows = S.get_sprite(name)
        w, h = len(rows[0]), len(rows)
        img = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch == "#":
                    img.fill(color, (x * scale, y * scale, scale, scale))
        _icon_cache[key] = img
    return img


# ---------------------------------------------------------------- tela OLED
_grid_cache = {}


def oled_surface(fb, scale, dim=False, on=None, off=None, grid=True):
    on = on or C["oled_on"]
    off = off or C["oled_off"]
    if dim:
        on = lerp(off, on, 0.45)
    arr = np.frombuffer(bytes(fb.buf), dtype=np.uint8).reshape(R.H, R.W).T
    rgb = np.empty((R.W, R.H, 3), dtype=np.uint8)
    for i in range(3):
        rgb[:, :, i] = np.where(arr, on[i], off[i])
    surf = pygame.surfarray.make_surface(rgb)
    surf = pygame.transform.scale(surf, (R.W * scale, R.H * scale))
    if grid and scale >= 3:
        g = _grid_cache.get(scale)
        if g is None:
            g = pygame.Surface((R.W * scale, R.H * scale), pygame.SRCALPHA)
            col = (0, 0, 0, 70)
            for x in range(0, R.W * scale, scale):
                pygame.draw.line(g, col, (x, 0), (x, R.H * scale))
            for y in range(0, R.H * scale, scale):
                pygame.draw.line(g, col, (0, y), (R.W * scale, y))
            _grid_cache[scale] = g
        surf.blit(g, (0, 0))
    return surf


def draw_oled(surf, fb, center, scale, dim=False, bezel=True):
    img = oled_surface(fb, scale, dim)
    r = img.get_rect(center=center)
    if bezel:
        b = r.inflate(28, 28)
        pygame.draw.rect(surf, (14, 14, 22), b, border_radius=14)
        pygame.draw.rect(surf, (60, 60, 80), b, 2, border_radius=14)
    surf.blit(img, r)
    return r


def render_pet(state, fb=None):
    fb = fb or R.Frame()
    R.draw_scene(fb, state)
    return fb


# ---------------------------------------------------------------- ovo do tamagotchi
def draw_egg(surf, center, fb, scale=3, t=0.0, dim=False, pressed=None):
    """Desenha a carcaca de tamagotchi. Retorna os retangulos dos botões A, B, C."""
    cx, cy = center
    sw, sh = R.W * scale, R.H * scale
    ew, eh = sw + 150, sh + 260
    egg = pygame.Rect(0, 0, ew, eh)
    egg.center = (cx, cy)
    # sombra e corpo
    pygame.draw.ellipse(surf, C["shadow"], egg.move(0, 10))
    pygame.draw.ellipse(surf, (230, 90, 160), egg)
    inner = egg.inflate(-18, -18)
    pygame.draw.ellipse(surf, C["pink"], inner)
    hl = pygame.Rect(inner.x + 40, inner.y + 30, inner.w // 3, inner.h // 5)
    pygame.draw.ellipse(surf, C["pink2"], hl)
    # bolinhas decorativas
    for i in range(7):
        a = i / 7 * math.tau + t * 0.2
        px = cx + math.cos(a) * (ew * 0.42)
        py = cy + math.sin(a) * (eh * 0.43)
        pygame.draw.circle(surf, (255, 190, 222), (int(px), int(py)), 5)
    scr_center = (cx, cy - 40)
    draw_oled(surf, fb, scr_center, scale, dim)
    # botoes
    rects = []
    by = cy + sh // 2 + 40
    for i, lbl in enumerate("ABC"):
        bx = cx + (i - 1) * 70
        down = pressed == i
        r = pygame.Rect(0, 0, 46, 46)
        r.center = (bx, by + (8 if i == 1 else 0) + (3 if down else 0))
        if not down:
            pygame.draw.ellipse(surf, (150, 40, 100), r.move(0, 5))
        pygame.draw.ellipse(surf, C["yellow"] if not down else (230, 180, 70), r)
        pygame.draw.ellipse(surf, (255, 235, 170), r.inflate(-26, -26).move(-6, -6))
        text(surf, lbl, (r.centerx, r.bottom + 14), 16, (90, 20, 60), True, "center")
        rects.append(r)
    return rects


# ---------------------------------------------------------------- widgets
class Button:
    def __init__(self, rect, label, cb=None, kind="primary", icon_name=None, size=18, enabled=True):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.cb = cb
        self.kind = kind
        self.icon_name = icon_name
        self.size = size
        self.enabled = enabled
        self.down = False
        self.hold = False  # True = dispara cb(True) ao apertar e cb(False) ao soltar

    def colors(self, hover):
        base = {"primary": C["pink"], "secondary": C["panel2"], "ok": C["green"], "cyan": C["cyan"],
                "danger": C["red"], "ghost": C["bg2"], "yellow": C["yellow"]}[self.kind]
        if not self.enabled:
            return lerp(base, C["bg"], 0.6), C["muted"]
        if self.down:
            base = lerp(base, (0, 0, 0), 0.2)
        elif hover:
            base = lerp(base, (255, 255, 255), 0.15)
        fg = (40, 16, 40) if self.kind in ("primary", "ok", "cyan", "yellow") else C["text"]
        return base, fg

    def handle(self, ev):
        if not self.enabled:
            return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.down = True
            if self.hold and self.cb:
                self.cb(True)
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.down:
            self.down = False
            if self.hold:
                if self.cb:
                    self.cb(False)
            elif self.rect.collidepoint(ev.pos) and self.cb:
                self.cb()
            return True
        return False

    def draw(self, surf):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        bg, fg = self.colors(hover)
        r = self.rect.move(0, 2 if self.down else 0)
        if not self.down:
            pygame.draw.rect(surf, lerp(bg, (0, 0, 0), 0.35), self.rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surf, bg, r, border_radius=12)
        x = r.centerx
        if self.icon_name:
            ic = icon(self.icon_name, 3, fg)
            tw = font(self.size, True).size(self.label)[0]
            total = ic.get_width() + (10 + tw if self.label else 0)
            ix = r.centerx - total // 2
            surf.blit(ic, (ix, r.centery - ic.get_height() // 2))
            if self.label:
                text(surf, self.label, (ix + ic.get_width() + 10, r.centery), self.size, fg, True, "midleft")
        else:
            text(surf, self.label, (x, r.centery), self.size, fg, True, "center")


def clipboard_text():
    try:
        t = pygame.scrap.get_text()
        if t:
            return t
    except Exception:
        pass
    try:
        import tkinter
        tk = tkinter.Tk()
        tk.withdraw()
        t = tk.clipboard_get()
        tk.destroy()
        return t
    except Exception:
        return ""


class TextInput:
    active = None

    def __init__(self, rect, value="", placeholder="", password=False, on_enter=None, size=18, maxlen=400):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.placeholder = placeholder
        self.password = password
        self.on_enter = on_enter
        self.size = size
        self.maxlen = maxlen
        self.reveal = False

    @property
    def focused(self):
        return TextInput.active is self

    def focus(self):
        TextInput.active = self
        pygame.key.start_text_input()

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                self.focus()
                return True
            if self.focused:
                TextInput.active = None
        if not self.focused:
            return False
        if ev.type == pygame.TEXTINPUT:
            self.value = (self.value + ev.text)[: self.maxlen]
            return True
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_BACKSPACE:
                if ev.mod & pygame.KMOD_CTRL:
                    self.value = self.value.rstrip().rsplit(" ", 1)[0] if " " in self.value.strip() else ""
                else:
                    self.value = self.value[:-1]
                return True
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.on_enter:
                    self.on_enter(self.value)
                return True
            if ev.key == pygame.K_v and ev.mod & pygame.KMOD_CTRL:
                self.value = (self.value + clipboard_text().strip().replace("\r", "").replace("\n", " "))[: self.maxlen]
                return True
            if ev.key == pygame.K_ESCAPE:
                TextInput.active = None
                return True
            return True
        return False

    def draw(self, surf, t=0.0):
        focus = self.focused
        pygame.draw.rect(surf, C["bg"], self.rect, border_radius=10)
        pygame.draw.rect(surf, C["pink"] if focus else C["line"], self.rect, 2, border_radius=10)
        shown = self.value
        if self.password and not self.reveal and shown:
            shown = shown[:7] + "*" * max(0, min(30, len(shown) - 11)) + shown[-4:] if len(shown) > 12 else "*" * len(shown)
        f = font(self.size)
        avail = self.rect.w - 24
        while shown and f.size(shown)[0] > avail:
            shown = shown[1:]
        clip = surf.get_clip()
        surf.set_clip(self.rect.inflate(-6, -4))
        if shown:
            r = text(surf, shown, (self.rect.x + 12, self.rect.centery), self.size, C["text"], align="midleft")
            cx = r.right + 2
        else:
            text(surf, self.placeholder, (self.rect.x + 12, self.rect.centery), self.size, C["muted"], align="midleft")
            cx = self.rect.x + 12
        if focus and int(t * 2) % 2 == 0:
            pygame.draw.line(surf, C["pink"], (cx, self.rect.centery - 11), (cx, self.rect.centery + 11), 2)
        surf.set_clip(clip)


class Choice:
    """Seletor < opcao > (clique na esquerda/direita)."""

    def __init__(self, rect, options, value, on_change=None, size=17):
        self.rect = pygame.Rect(rect)
        self.options = options  # lista de (valor, rotulo)
        self.size = size
        self.on_change = on_change
        vals = [o[0] for o in options]
        self.i = vals.index(value) if value in vals else 0

    @property
    def value(self):
        return self.options[self.i][0] if self.options else None

    def set_options(self, options, value=None):
        self.options = options
        vals = [o[0] for o in options]
        self.i = vals.index(value) if value in vals else 0

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos) and self.options:
            step = -1 if ev.pos[0] < self.rect.centerx else 1
            self.i = (self.i + step) % len(self.options)
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def draw(self, surf):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surf, C["panel2"] if hover else C["bg"], self.rect, border_radius=10)
        pygame.draw.rect(surf, C["line"], self.rect, 2, border_radius=10)
        text(surf, "<", (self.rect.x + 16, self.rect.centery), 20, C["pink"], True, "center")
        text(surf, ">", (self.rect.right - 16, self.rect.centery), 20, C["pink"], True, "center")
        lbl = self.options[self.i][1] if self.options else "-"
        clip = surf.get_clip()
        surf.set_clip(self.rect.inflate(-60, 0))
        text(surf, lbl, self.rect.center, self.size, C["text"], align="center")
        surf.set_clip(clip)


class Toggle:
    def __init__(self, pos, value, on_change=None):
        self.rect = pygame.Rect(pos[0], pos[1], 56, 30)
        self.value = bool(value)
        self.on_change = on_change

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.value = not self.value
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def draw(self, surf):
        col = C["green"] if self.value else C["line"]
        pygame.draw.rect(surf, col, self.rect, border_radius=15)
        kx = self.rect.right - 15 if self.value else self.rect.x + 15
        pygame.draw.circle(surf, C["text"], (kx, self.rect.centery), 11)


class Slider:
    def __init__(self, rect, lo, hi, value, on_change=None, fmt="{:.0f}"):
        self.rect = pygame.Rect(rect)
        self.lo, self.hi = lo, hi
        self.value = value
        self.on_change = on_change
        self.drag = False
        self.fmt = fmt

    def _set(self, x):
        t = max(0.0, min(1.0, (x - self.rect.x) / self.rect.w))
        self.value = round(self.lo + t * (self.hi - self.lo))
        if self.on_change:
            self.on_change(self.value)

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.inflate(0, 20).collidepoint(ev.pos):
            self.drag = True
            self._set(ev.pos[0])
            return True
        if ev.type == pygame.MOUSEMOTION and self.drag:
            self._set(ev.pos[0])
            return True
        if ev.type == pygame.MOUSEBUTTONUP and self.drag:
            self.drag = False
            return True
        return False

    def draw(self, surf):
        r = self.rect
        pygame.draw.rect(surf, C["bg"], (r.x, r.centery - 4, r.w, 8), border_radius=4)
        t = (self.value - self.lo) / max(1, (self.hi - self.lo))
        pygame.draw.rect(surf, C["pink"], (r.x, r.centery - 4, int(r.w * t), 8), border_radius=4)
        pygame.draw.circle(surf, C["text"], (r.x + int(r.w * t), r.centery), 10)
        text(surf, self.fmt.format(self.value), (r.right + 14, r.centery), 16, C["muted"], align="midleft")


def stat_bars(surf, pet, pos, width=300, size=16):
    x, y = pos
    items = [("i_apple", "Fome", pet.hunger, C["orange"]), ("i_heart", "Alegria", pet.happy, C["pink"]),
             ("i_bolt", "Energia", pet.energy, C["yellow"]), ("i_drop", "Higiene", pet.clean, C["cyan"])]
    for ic, lbl, v, col in items:
        surf.blit(icon(ic, 3, col), (x, y + 2))
        text(surf, lbl, (x + 34, y), size, C["text"])
        bx = x + 120
        bw = width - 170
        pygame.draw.rect(surf, C["bg"], (bx, y + 4, bw, 14), border_radius=7)
        pygame.draw.rect(surf, col, (bx, y + 4, max(14, int(bw * v / 100)), 14), border_radius=7)
        text(surf, f"{v}%", (x + width, y), size, C["muted"], align="right")
        y += 30
    return y


def spinner(surf, center, t, r=18, color=None):
    color = color or C["pink"]
    for i in range(10):
        a = t * 6 + i * math.tau / 10
        alpha = (i + 1) / 10
        col = lerp(C["bg"], color, alpha)
        pygame.draw.circle(surf, col, (int(center[0] + math.cos(a) * r), int(center[1] + math.sin(a) * r)), 4)


# ---------------------------------------------------------------- ilustracoes
def draw_arduino(surf, center, scale=1.0, t=0.0, glow=0.0, shield=True):
    """Arduino Uno azul com o shield VS1053 vermelho por cima. Retorna a posicao da porta USB."""
    cx, cy = center
    s = scale
    w, h = int(230 * s), int(160 * s)
    board = pygame.Rect(0, 0, w, h)
    board.center = (cx, cy)
    if glow > 0:
        for i in range(4):
            rr = board.inflate(int((20 + i * 14) * glow), int((20 + i * 14) * glow))
            g = pygame.Surface(rr.size, pygame.SRCALPHA)
            pygame.draw.rect(g, (*C["green"], int(40 * glow)), g.get_rect(), border_radius=24)
            surf.blit(g, rr)
    pygame.draw.rect(surf, C["shadow"], board.move(0, 6), border_radius=10)
    pygame.draw.rect(surf, (0, 110, 160), board, border_radius=10)
    # porta USB e conector de forca
    usb = pygame.Rect(board.x - int(16 * s), board.y + int(22 * s), int(40 * s), int(36 * s))
    pygame.draw.rect(surf, (190, 195, 205), usb, border_radius=3)
    pygame.draw.rect(surf, (20, 20, 20), (board.x - int(14 * s), board.y + int(110 * s), int(34 * s), int(30 * s)), border_radius=3)
    if shield:
        sh = board.inflate(-int(20 * s), -int(14 * s)).move(int(8 * s), 0)
        pygame.draw.rect(surf, (210, 30, 40), sh, border_radius=8)
        # chip VS1053
        chip = pygame.Rect(0, 0, int(46 * s), int(46 * s))
        chip.center = (sh.centerx, sh.centery - int(4 * s))
        pygame.draw.rect(surf, (25, 25, 30), chip, border_radius=4)
        text(surf, "VS1053", (chip.centerx, chip.centery), max(9, int(11 * s)), (200, 200, 210), True, "center")
        # conectores MIC e SPK
        for i, lbl in enumerate(("MIC", "SPK")):
            jx = sh.x + int((120 + i * 50) * s)
            jack = pygame.Rect(jx, sh.y + int(4 * s), int(34 * s), int(30 * s))
            pygame.draw.rect(surf, (20, 20, 20), jack, border_radius=4)
            pygame.draw.circle(surf, (90, 90, 90), jack.center, int(7 * s))
            text(surf, lbl, (jack.centerx, jack.bottom + int(8 * s)), max(9, int(11 * s)), C["text"], True, "center")
        # microfone redondo
        pygame.draw.circle(surf, (50, 50, 55), (sh.x + int(40 * s), sh.y + int(22 * s)), int(14 * s))
        pygame.draw.circle(surf, (140, 140, 145), (sh.x + int(40 * s), sh.y + int(22 * s)), int(10 * s))
        # slot SD
        pygame.draw.rect(surf, (170, 170, 180), (sh.x + int(14 * s), sh.bottom - int(42 * s), int(44 * s), int(36 * s)), border_radius=3)
    # barras de pinos
    for i in range(14):
        x = board.x + int((60 + i * 11) * s)
        pygame.draw.rect(surf, (30, 30, 35), (x, board.y + int(3 * s), int(8 * s), int(8 * s)))
        pygame.draw.rect(surf, (30, 30, 35), (x, board.bottom - int(11 * s), int(8 * s), int(8 * s)))
    # LED piscando
    on = int(t * 3) % 2 == 0
    pygame.draw.circle(surf, C["green"] if on else (40, 80, 40), (board.right - int(18 * s), board.y + int(20 * s)), max(3, int(4 * s)))
    return (usb.x, usb.centery)


def draw_pc(surf, center, scale=1.0, t=0.0, fb=None):
    cx, cy = center
    s = scale
    mon = pygame.Rect(0, 0, int(200 * s), int(130 * s))
    mon.center = (cx, cy - int(20 * s))
    pygame.draw.rect(surf, C["shadow"], mon.move(0, 6), border_radius=10)
    pygame.draw.rect(surf, (60, 58, 90), mon, border_radius=10)
    scr = mon.inflate(-int(18 * s), -int(18 * s))
    pygame.draw.rect(surf, (14, 12, 28), scr, border_radius=6)
    if fb is not None:
        img = oled_surface(fb, 1, grid=False)
        img = pygame.transform.scale(img, (scr.w - 10, int((scr.w - 10) / 2)))
        surf.blit(img, img.get_rect(center=scr.center))
    pygame.draw.rect(surf, (60, 58, 90), (cx - int(14 * s), mon.bottom, int(28 * s), int(26 * s)))
    pygame.draw.rect(surf, (60, 58, 90), (cx - int(55 * s), mon.bottom + int(24 * s), int(110 * s), int(10 * s)), border_radius=5)
    return (mon.right, mon.bottom - int(30 * s))


def draw_cable(surf, a, b, t, plugged, color=(40, 40, 50)):
    """Cabo USB entre a (PC) e b (porta do Arduino). Se não plugado, o plugue fica indo e vindo."""
    ax, ay = a
    bx, by = b
    if plugged:
        end = (bx + 6, by)
    else:
        k = (math.sin(t * 2.4) + 1) / 2
        end = (int(bx - 90 + 60 * k), int(by))
    pts = []
    for i in range(31):
        u = i / 30
        x = ax + (end[0] - ax) * u
        y = ay + (end[1] - ay) * u + math.sin(u * math.pi) * 60
        pts.append((x, y))
    pygame.draw.lines(surf, color, False, pts, 9)
    pygame.draw.lines(surf, (90, 90, 110), False, pts, 3)
    plug = pygame.Rect(0, 0, 36, 24)
    plug.midright = end
    pygame.draw.rect(surf, (200, 200, 210), plug, border_radius=4)
    pygame.draw.rect(surf, (150, 150, 160), (plug.right - 10, plug.y + 6, 14, 12))
    return pts


class Confetti:
    def __init__(self, area):
        import random
        self.r = random
        self.area = pygame.Rect(area)
        self.parts = []

    def burst(self, n=120):
        cols = [C["pink"], C["cyan"], C["yellow"], C["green"], C["orange"]]
        for _ in range(n):
            self.parts.append([self.area.centerx + self.r.uniform(-60, 60), self.area.y + self.r.uniform(40, 140),
                               self.r.uniform(-6, 6), self.r.uniform(-9, -2), self.r.choice(cols),
                               self.r.uniform(0, 6.28), self.r.randint(4, 9)])

    def update_draw(self, surf, dt):
        alive = []
        for p in self.parts:
            p[0] += p[2] * dt * 60
            p[1] += p[3] * dt * 60
            p[3] += 0.25 * dt * 60
            p[5] += 0.2
            if p[1] < self.area.bottom + 20:
                alive.append(p)
                w = abs(math.cos(p[5])) * p[6] + 2
                pygame.draw.rect(surf, p[4], (p[0], p[1], w, p[6]))
        self.parts = alive
