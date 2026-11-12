"""Tamagotchi Studio: programa principal (aberto pelo TAMAGOTCHI.bat)."""
import os
import sys
import time

import pygame

from . import renderer as R
from . import settings as SET
from . import ui
from .core import Companion
from .screens import (SIDEBAR_W, ChatScreen, GalleryScreen, HomeScreen, SettingsScreen, TutorialScreen,
                      WiringScreen, demo_state)
from .ui import C

NAV = [("home", "Início", "i_home"), ("chat", "Conversar", "i_chat"), ("gallery", "Animações", "i_film"),
       ("settings", "Configurações", "i_gear"), ("wiring", "Ligações", "i_bolt"), ("tutorial", "Tutorial", "i_book")]


class App:
    def __init__(self, headless=False):
        pygame.init()
        pygame.display.set_caption("Tamagotchi Studio + Claude")
        flags = 0
        self.screen = pygame.display.set_mode((ui.W, ui.H), flags)
        try:
            pygame.display.set_icon(ui.icon("i_heart", 4, C["pink"]))
        except Exception:
            pass
        self.clock = pygame.time.Clock()
        self.s = SET.load()
        self.comp = Companion(self.s)
        self.t0 = time.time()
        self.t = 0.0
        self.pending_go = None
        self.started = False
        self.screens = {
            "tutorial": TutorialScreen(self), "home": HomeScreen(self), "chat": ChatScreen(self),
            "gallery": GalleryScreen(self), "settings": SettingsScreen(self), "wiring": WiringScreen(self),
        }
        self.cur = "home" if self.s.get("tutorial_done") else "tutorial"
        if self.cur == "home" and not headless:
            self.start_companion()
        self.logo_fb = R.Frame()
        self.nav_btns = []
        for i, (key, lbl, ic) in enumerate(NAV):
            b = ui.Button((14, 130 + i * 62, SIDEBAR_W - 28, 52), lbl, (lambda k=key: self.go(k)), "ghost", ic, 17)
            self.nav_btns.append((key, b))

    def start_companion(self):
        if not self.started:
            self.started = True
            self.comp.start()

    def go(self, name):
        ui.TextInput.active = None
        prev = self.screens.get(self.cur)
        if prev is not None and prev is not self.screens[name] and hasattr(prev, "on_hide"):
            prev.on_hide()
        self.cur = name
        if name != "tutorial":
            self.start_companion()
        self.screens[name].on_show()

    def draw_sidebar(self, surf):
        pygame.draw.rect(surf, C["bg2"], (0, 0, SIDEBAR_W, ui.H))
        pygame.draw.line(surf, C["line"], (SIDEBAR_W - 1, 0), (SIDEBAR_W - 1, ui.H), 2)
        pet = self.comp.pet
        img = ui.oled_surface(ui.render_pet(pet, self.logo_fb), 1, dim=pet.sleeping, grid=False)
        surf.blit(img, (SIDEBAR_W // 2 - 64, 16))
        ui.text(surf, "Tamagotchi Studio", (SIDEBAR_W // 2, 98), 17, C["pink"], True, "center")
        for key, b in self.nav_btns:
            b.kind = "primary" if key == self.cur else "ghost"
            b.draw(surf)
        # chips de status
        mgr = self.comp.mgr
        y = ui.H - 110
        if mgr is None:
            st, col = "Arduino: aguardando", C["muted"]
        else:
            st, col = {"waiting": ("Arduino: esperando", C["yellow"]), "checking": ("Arduino: verificando", C["yellow"]),
                       "programming": ("Arduino: programando", C["cyan"]), "done": ("Arduino: pronto!", C["green"]),
                       "ready": (f"Arduino: {mgr.port}", C["green"]), "error": ("Arduino: erro", C["red"])}[mgr.state]
        pygame.draw.circle(surf, col, (28, y + 10), 7)
        ui.text(surf, st, (44, y), 15, C["text"])
        key_ok = bool(self.s.get("anthropic_api_key"))
        pygame.draw.circle(surf, C["green"] if key_ok else C["red"], (28, y + 40), 7)
        ui.text(surf, "Claude: ok" if key_ok else "Claude: sem chave", (44, y + 30), 15, C["text"])
        ui.text(surf, "TAMAGOTCHI.bat", (SIDEBAR_W // 2, ui.H - 28), 12, C["muted"], align="center")

    def frame(self, dt):
        self.t = time.time() - self.t0
        if self.pending_go:
            g, self.pending_go = self.pending_go, None
            self.go(g)
        self.comp.tick(int(self.t * 1000))
        scr = self.screens[self.cur]
        self.screen.fill(C["bg"])
        scr.draw(self.screen, dt)
        if not scr.fullscreen:
            self.draw_sidebar(self.screen)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(30) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                    continue
                scr = self.screens[self.cur]
                if not scr.fullscreen:
                    if any(b.handle(ev) for _, b in self.nav_btns):
                        continue
                scr.handle(ev)
            self.frame(dt)
            pygame.display.flip()
        self.comp.shutdown()
        pygame.quit()


def screenshot(screen_name, out, state=None, seconds=1.2):
    """Gera um PNG de uma tela (para testes): python -m app.main --shot home saída.png"""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    app = App(headless=True)
    app.cur = screen_name
    if state:
        class FakeMgr:
            pass
        m = FakeMgr()
        m.state, m.message, m.progress, m.stage, m.port = state, "Encontrei algo na COM5. Verificando...", 0.58, "Gravando na placa", "COM5"
        m.logs = ["> arduino-cli compile --fqbn arduino:avr:uno ...", "Sketch uses 16482 bytes (51%) of program storage space.",
                  "Compilado com sucesso!", "Enviando para COM5... (os LEDs RX/TX do Arduino vao piscar)"]
        app.comp.mgr = m
    if screen_name == "tutorial" and state and state.isdigit():
        app.screens["tutorial"].page = int(state)
        app.comp.mgr = None
    app.screens[screen_name].on_show()
    t_end = time.time() + seconds
    while time.time() < t_end:
        app.frame(1 / 30)
        time.sleep(1 / 30)
    pygame.image.save(app.screen, out)


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--shot":
        screenshot(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
        return
    App().run()


if __name__ == "__main__":
    main()
