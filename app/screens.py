"""Telas do Tamagotchi Studio."""
import math
import threading
import time
import webbrowser

import pygame

from . import animations as A
from . import firmware_tools as F
from . import renderer as R
from . import settings as SET
from . import ui
from .petsim import PetState
from .ui import C

AI = A.ANIM_INDEX
SIDEBAR_W = 220
CX = SIDEBAR_W + (ui.W - SIDEBAR_W) // 2


def demo_state(anim, now_ms, name="PIXO"):
    st = PetState(name)
    st.override = None
    st.anim = AI[anim] if isinstance(anim, str) else anim
    st.now = now_ms
    st.t = now_ms // A.ANIMATIONS[st.anim][6]
    return st


class Screen:
    fullscreen = False

    def __init__(self, app):
        self.app = app
        self.widgets = []

    def on_show(self):
        pass

    def handle(self, ev):
        for w in self.widgets:
            if w.handle(ev):
                return True
        return False

    def draw(self, surf, dt):
        pass


# ===================================================================== TUTORIAL
class TutorialScreen(Screen):
    fullscreen = True
    PAGES = 8

    def __init__(self, app):
        super().__init__(app)
        self.page = 0
        self.fb = R.Frame()
        self.demo = PetState(app.s.get("pet_name", "PIXO"))
        self.pressed = None
        self.egg_btns = []
        self.key_msg = ("", C["muted"])
        self.testing = False
        self.back = ui.Button((60, 640, 160, 50), "Voltar", self.prev, "secondary")
        self.next = ui.Button((ui.W - 240, 640, 180, 50), "Próximo", self.nxt, "primary")
        self.key_input = ui.TextInput((140, 420, 620, 50), app.s.get("anthropic_api_key", ""),
                                      "Cole aqui a chave (sk-ant-...)", password=True, on_enter=lambda v: self.test_key())
        self.btn_site = ui.Button((140, 490, 250, 46), "Abrir o site da chave", self.open_site, "cyan", size=16)
        self.btn_test = ui.Button((410, 490, 170, 46), "Testar chave", self.test_key, "secondary", size=16)
        self.btn_show = ui.Button((600, 490, 160, 46), "Mostrar", self.toggle_show, "ghost", size=16)

    def on_show(self):
        self.demo = PetState(self.app.s.get("pet_name", "PIXO"))

    # navegacao
    def prev(self):
        self.page = max(0, self.page - 1)

    def nxt(self):
        if self.page < self.PAGES - 1:
            self.page += 1
            if self.page == self.PAGES - 1:
                self.key_input.focus()
        else:
            self.finish()

    def open_site(self):
        webbrowser.open("https://console.anthropic.com/settings/keys")

    def toggle_show(self):
        self.key_input.reveal = not self.key_input.reveal
        self.btn_show.label = "Esconder" if self.key_input.reveal else "Mostrar"

    def test_key(self, then_finish=False):
        key = self.key_input.value.strip()
        if not key:
            self.key_msg = ("Cole a chave primeiro.", C["yellow"])
            return
        if self.testing:
            return
        self.testing = True
        self.key_msg = ("Testando com o Claude...", C["muted"])

        def run():
            from .brain import test_key
            s = dict(self.app.s)
            s["anthropic_api_key"] = key
            ok, msg = test_key(s)
            self.testing = False
            self.key_msg = (msg, C["green"] if ok else C["red"])
            if ok and then_finish:
                self._save_and_go(key)
            elif not ok and then_finish and "inválida" not in msg:
                # chave parece certa, mas algo de fora falhou (internet, modelo): segue mesmo assim
                self.key_msg = (msg + " Vou salvar mesmo assim.", C["yellow"])
                self._save_and_go(key)
        threading.Thread(target=run, daemon=True).start()

    def finish(self):
        key = self.key_input.value.strip()
        if not key.startswith("sk-ant-"):
            self.key_msg = ("Para terminar, cole sua chave do Claude (ela começa com sk-ant-).", C["yellow"])
            self.key_input.focus()
            return
        self.test_key(then_finish=True)

    def _save_and_go(self, key):
        self.app.s["anthropic_api_key"] = key
        self.app.s["tutorial_done"] = True
        SET.save(self.app.s)
        self.app.pending_go = "home"

    def handle(self, ev):
        if self.back.handle(ev) or self.next.handle(ev):
            return True
        if self.page == self.PAGES - 1:
            for w in (self.key_input, self.btn_site, self.btn_test, self.btn_show):
                if w.handle(ev):
                    return True
        if self.page in (0, 4):
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                for i, r in enumerate(self.egg_btns):
                    if r.collidepoint(ev.pos):
                        self.pressed = i
                        [self.demo.button_a, self.demo.button_b, self.demo.button_c][i]()
                        return True
            if ev.type == pygame.MOUSEBUTTONUP:
                self.pressed = None
        if ev.type == pygame.KEYDOWN and ui.TextInput.active is None:
            if ev.key in (pygame.K_RIGHT, pygame.K_RETURN):
                self.nxt()
            elif ev.key == pygame.K_LEFT:
                self.prev()
        return False

    # desenho
    def header(self, surf, title, sub=None):
        ui.text(surf, title, (ui.W // 2, 62), 38, C["text"], True, "center")
        if sub:
            ui.text(surf, sub, (ui.W // 2, 108), 19, C["muted"], align="center")

    def draw(self, surf, dt):
        t = self.app.t
        now = int(t * 1000)
        surf.fill(C["bg"])
        for i in range(30):  # estrelinhas de fundo
            x = (i * 137) % ui.W
            y = (i * 89 + int(t * 8 * (1 + i % 3))) % ui.H
            pygame.draw.circle(surf, C["bg2"], (x, y), 2 + i % 3)
        getattr(self, f"page{self.page}")(surf, t, now)
        # pontinhos de progresso
        for i in range(self.PAGES):
            col = C["pink"] if i == self.page else C["line"]
            pygame.draw.circle(surf, col, (ui.W // 2 - (self.PAGES - 1) * 14 + i * 28, 665), 7 if i == self.page else 5)
        self.back.enabled = self.page > 0
        self.next.label = "Concluir" if self.page == self.PAGES - 1 else "Próximo"
        self.next.kind = "ok" if self.page == self.PAGES - 1 else "primary"
        self.back.draw(surf)
        self.next.draw(surf)
        ui.text(surf, f"Passo {self.page + 1} de {self.PAGES}", (ui.W // 2, 695), 14, C["muted"], align="center")

    def page0(self, surf, t, now):
        self.header(surf, "Oi! Bem-vindo ao seu Tamagotchi com Claude",
                    "Um bichinho virtual de verdade: mora no Arduino, conversa com voz e tem 50 emoções.")
        self.demo.update(now)
        self.egg_btns = ui.draw_egg(surf, (380, 380), ui.render_pet(self.demo, self.fb), 2, t, pressed=self.pressed)
        x = 650
        ui.panel(surf, (x, 170, 520, 420))
        y = 195
        ui.text(surf, "O que você vai ter:", (x + 28, y), 24, C["pink"], True)
        y += 50
        items = [("i_heart", "Um pet pixelado que sente fome, sono, sujeira e alegria"),
                 ("i_chat", "Conversa por voz: o Claude é o cérebro dele"),
                 ("i_note", "Voz gratuita (Edge TTS) saindo no alto-falante do shield"),
                 ("i_film", "50 animações que seguem as emoções das respostas"),
                 ("i_pc", "Um mascote virtual aqui no PC para testar sem Arduino"),
                 ("i_bolt", "O Arduino e programado sozinho quando você ligar o USB")]
        for ic, s in items:
            surf.blit(ui.icon(ic, 3, C["cyan"]), (x + 28, y + 3))
            y = ui.text_block(surf, s, (x + 70, y), 420, 18) + 12
        ui.text(surf, "Dica: clique nos botões A, B e C do ovinho!", (380, 640 - 30), 15, C["muted"], align="center")

    def page1(self, surf, t, now):
        self.header(surf, "Como tudo se conecta", "O Arduino é o corpo, o PC é a ponte e o Claude é o cérebro.")
        boxes = [
            ((110, 200, 260, 170), "Arduino", "corpo do pet", ["Display com o pet", "Botões A B C", "Microfone e alto-falante", "Fome, sono, banho"], C["cyan"]),
            ((490, 200, 260, 170), "Este programa", "ponte no PC", ["Entende sua fala", "Cria a voz", "Programa o Arduino", "Pet virtual"], C["pink"]),
            ((870, 140, 260, 110), "Claude", "o cérebro", ["Responde e escolhe a emoção"], C["yellow"]),
            ((870, 270, 260, 110), "Voz grátis", "Edge TTS", ["Transforma texto em fala"], C["green"]),
            ((870, 400, 260, 110), "Ouvido grátis", "Google Speech", ["Transforma fala em texto"], C["orange"]),
        ]
        for (r, title, sub, lines, col) in boxes:
            rect = ui.panel(surf, r, border=col)
            ui.text(surf, title, (rect.x + 18, rect.y + 12), 22, col, True)
            ui.text(surf, sub, (rect.x + 18, rect.y + 42), 15, C["muted"])
            y = rect.y + 68
            for ln in lines:
                ui.text(surf, "* " + ln, (rect.x + 18, y), 15)
                y += 22
        # setas com bolinhas andando
        def flow(a, b, col, phase=0.0):
            pygame.draw.line(surf, C["line"], a, b, 4)
            for k in range(3):
                u = (t * 0.6 + k / 3 + phase) % 1.0
                p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
                pygame.draw.circle(surf, col, (int(p[0]), int(p[1])), 6)
        flow((370, 270), (490, 270), C["cyan"])
        flow((490, 310), (370, 310), C["pink"], 0.5)
        ui.text(surf, "USB", (430, 245), 15, C["muted"], True, "center")
        for yy, col in ((195, C["yellow"]), (325, C["green"]), (455, C["orange"])):
            flow((750, 285), (870, yy), col)
        ui.text(surf, "internet", (810, 230), 15, C["muted"], True, "center")
        ui.panel(surf, (110, 420, 640, 150))
        ui.text_block(surf, "Quando você fala, o microfone do shield grava, o som vai pelo cabo USB até o PC, "
                      "que entende as palavras e pergunta ao Claude o que responder e qual emoção mostrar. "
                      "A resposta vira voz e volta para o alto-falante do Arduino, enquanto o pet faz a animação certa.",
                      (134, 440), 600, 17)

    def page2(self, surf, t, now):
        self.header(surf, "As peças que você precisa", "Tudo barato e fácil de achar.")
        ui.draw_arduino(surf, (330, 330), 1.4, t)
        ui.text(surf, "Arduino Uno + Shield VS1053 (o vermelho)", (330, 470), 17, C["muted"], align="center")
        x, y = 640, 160
        ui.panel(surf, (x, y, 540, 440))
        parts = [
            ("1x Arduino Uno", "Com o cabo USB. Nano e Mega também funcionam com ajustes."),
            ("1x Shield VS1053 MP3 (Geeetech)", "Encaixa em cima do Uno. Tem microfone, entrada MIC, saída SPK e cartão SD."),
            ("1x Tela TFT 0.96\" 80x160 colorida (ST7735)", "A de 8 pinos: GND VCC SCL SDA RES DC CS BLK. Um OLED I2C 128x64 também serve."),
            ("3x Botões (push button)", "Os botões A, B e C do tamagotchi."),
            ("1x Fone ou caixinha de som P2", "Liga na saída SPK do shield."),
            ("Fios jumper", "Para ligar o display e os botões nos pinos que sobram."),
        ]
        yy = y + 22
        for i, (a, b) in enumerate(parts):
            pygame.draw.circle(surf, C["pink"], (x + 30, yy + 12), 13)
            ui.text(surf, str(i + 1), (x + 30, yy + 12), 15, (40, 16, 40), True, "center")
            ui.text(surf, a, (x + 56, yy), 18, C["text"], True)
            yy = ui.text_block(surf, b, (x + 56, yy + 26), 460, 15, C["muted"]) + 14

    def page3(self, surf, t, now):
        self.header(surf, "Ligações", "O shield usa os pinos 2, 6 a 13. O display e os botões vão nos pinos livres.")
        draw_wiring(surf, pygame.Rect(90, 150, 1060, 450), t, self.app.s)

    def page4(self, surf, t, now):
        self.header(surf, "Cuidando do pet", "As 4 necessidades caem com o tempo. Se ficarem baixas, ele fica triste.")
        self.demo.update(now)
        self.egg_btns = ui.draw_egg(surf, (360, 380), ui.render_pet(self.demo, self.fb), 2, t, pressed=self.pressed)
        x = 650
        ui.panel(surf, (x, 150, 520, 460))
        ui.stat_bars(surf, self.demo, (x + 28, 175), 460)
        y = 310
        ui.text(surf, "Os botões:", (x + 28, y), 22, C["pink"], True)
        y += 40
        for k, s in [("A", "Abre o menu e passa para o próximo item"),
                     ("B", "Escolhe o item: Comer, Brincar, Banho, Dormir, Status, Falar"),
                     ("C", "Volta, faz carinho, ou SEGURE para falar com ele")]:
            pygame.draw.circle(surf, C["yellow"], (x + 46, y + 12), 16)
            ui.text(surf, k, (x + 46, y + 12), 16, (90, 20, 60), True, "center")
            y = ui.text_block(surf, s, (x + 76, y), 410, 17) + 12
        ui.text(surf, "Experimente aqui: clique no A e depois no B.", (x + 28, y + 6), 16, C["cyan"])

    def page5(self, surf, t, now):
        self.header(surf, "Conversando com ele", "Segure o botão C no Arduino (ou o botão de microfone aqui no PC) e fale.")
        seq = [("listening", "1. Ele escuta enquanto você segura o botão"),
               ("thinking", "2. O Claude pensa na resposta"),
               ("happy", "3. Ele responde com voz e uma emoção"),
               ("love", "Se você elogiar, ele fica apaixonado"),
               ("laugh", "Conte uma piada e ele ri"),
               ("sad", "Se falar algo triste, ele fica triste")]
        k = int(t / 2.2) % len(seq)
        st = demo_state(seq[k][0], now, self.app.s.get("pet_name", "PIXO"))
        if seq[k][0] == "happy":
            st.talking = True
        ui.draw_oled(surf, ui.render_pet(st, self.fb), (ui.W // 2, 290), 4)
        ui.text(surf, seq[k][1], (ui.W // 2, 455), 22, C["yellow"], True, "center")
        ui.panel(surf, (200, 500, 840, 110))
        ui.text_block(surf, "Ele lembra da conversa, sabe se está com fome ou sono, e pode até comer ou dormir "
                      "se você pedir (\"toma um lanche\", \"vai dormir\"). Sem Arduino, use a tela Conversar: "
                      "o mascote do PC faz tudo igual.", (224, 518), 790, 17)

    def page6(self, surf, t, now):
        self.header(surf, "Tudo automático", "Você não precisa da Arduino IDE.")
        st = demo_state("determined", now)
        pc_port = ui.draw_pc(surf, (300, 320), 1.1, t, ui.render_pet(st, self.fb))
        usb = ui.draw_arduino(surf, (900, 320), 1.0, t, glow=(math.sin(t * 3) + 1) / 4)
        plugged = (t % 6) > 3
        pts = ui.draw_cable(surf, pc_port, usb, t, plugged)
        if plugged:
            for k in range(6):
                u = (t * 0.7 + k / 6) % 1.0
                p = pts[int(u * (len(pts) - 1))]
                ui.text(surf, "01"[k % 2], (p[0], p[1] - 18), 18, C["green"], True, "center")
        ui.panel(surf, (200, 480, 840, 130))
        ui.text_block(surf, "Quando terminar este tutorial, a tela principal fica esperando o Arduino. "
                      "É só ligar o cabo USB: eu gero as configurações, compilo e gravo a placa sozinho, com uma "
                      "animação mostrando o progresso. Se você mudar algo em Configurações, eu reprogramo de novo.",
                      (224, 498), 790, 17)

    def page7(self, surf, t, now):
        self.header(surf, "Último passo: sua chave do Claude", "É ela que dá o cérebro para o pet.")
        ui.panel(surf, (110, 150, 690, 470))
        y = 172
        for n, s in [("1", "Clique em \"Abrir o site da chave\" e entre na sua conta Anthropic (Claude Console)."),
                     ("2", "Clique em Create Key, de um nome (ex: tamagotchi) e copie a chave."),
                     ("3", "Volte aqui, clique na caixa abaixo e aperte Ctrl+V.")]:
            pygame.draw.circle(surf, C["pink"], (150, y + 13), 14)
            ui.text(surf, n, (150, y + 13), 15, (40, 16, 40), True, "center")
            y = ui.text_block(surf, s, (178, y), 600, 17) + 14
        ui.text(surf, "Chave do Claude (API key)", (140, 392), 16, C["muted"], True)
        self.key_input.draw(surf, t)
        self.btn_site.draw(surf)
        self.btn_test.draw(surf)
        self.btn_show.draw(surf)
        if self.testing:
            ui.spinner(surf, (155, 572), t, 10)
        ui.text_block(surf, self.key_msg[0], (180 if self.testing else 140, 560), 620, 16, self.key_msg[1])
        ui.panel(surf, (830, 150, 340, 470), C["bg2"])
        st = demo_state("idea", int(t * 1000))
        ui.draw_oled(surf, ui.render_pet(st, self.fb), (1000, 240), 2)
        ui.text_block(surf, "A chave fica salva só neste computador, no arquivo settings.json.\n\n"
                      "Cada conversa usa um pouquinho do crédito da sua conta Anthropic. "
                      "O modelo padrão é o Claude Opus 5.5 em modo rápido; dá para trocar depois em Configurações.",
                      (856, 330), 290, 15, C["muted"])


# ===================================================================== LIGACOES
def pin_label(v):
    v = str(v)
    if v in ("-1", ""):
        return "-"
    if v.upper().startswith("A"):
        return v.upper()
    n = int(v)
    return f"A{n - 14}" if n >= 14 else f"D{n}"


def draw_wiring(surf, area, t, s):
    """Diagrama simples: pinos do Arduino a esquerda, display e botões a direita."""
    tft = s.get("oled_driver") == "ST7735"
    gray = (150, 150, 160)
    if tft:
        pins = [("3.3V", C["red"]), ("GND", gray), ("D13 (SCK)", C["yellow"]), ("D11 (MOSI)", C["cyan"]),
                (f"{pin_label(s.get('tft_rst', 5))}  RES", (190, 140, 255)),
                (f"{pin_label(s.get('tft_dc', 4))}  DC", (120, 200, 255)),
                (f"{pin_label(s.get('tft_cs', 10))}  CS", (255, 190, 120)),
                (f"{pin_label(s.get('tft_blk', 3))}  BLK", (200, 200, 120))]
        dpins = [("GND", 1), ("VCC", 0), ("SCL", 2), ("SDA", 3), ("RES", 4), ("DC", 5), ("CS", 6), ("BLK", 7)]
    else:
        pins = [("5V", C["red"]), ("GND", gray), ("A4 / SDA", C["cyan"]), ("A5 / SCL", C["yellow"])]
        dpins = [("GND", 1), ("VCC", 0), ("SCL", 3), ("SDA", 2)]
    nb = len(pins)
    pins += [(f"{s.get('pin_btn_a', 'A0')}  botão A", C["pink"]), (f"{s.get('pin_btn_b', 'A1')}  botão B", C["green"]),
             (f"{s.get('pin_btn_c', 'A2')}  botão C", C["orange"])]
    ax = area.x + 40
    board = ui.panel(surf, (ax, area.y + 10, 250, area.h - 20), (0, 110, 160))
    ui.text(surf, "Arduino + Shield", (board.centerx, board.y + 22), 18, C["text"], True, "center")
    ui.text(surf, "(pinos livres no shield)", (board.centerx, board.y + 46), 13, (200, 230, 245), align="center")
    pin_pos = {}
    step = min(46, (board.h - 90) // len(pins))
    for i, (name, col) in enumerate(pins):
        y = board.y + 80 + i * step
        pygame.draw.rect(surf, (20, 20, 25), (board.right - 34, y - 9, 18, 18))
        pygame.draw.circle(surf, (210, 180, 80), (board.right - 25, y), 5)
        ui.text(surf, name, (board.x + 20, y), 16, C["text"], True, "midleft")
        pin_pos[i] = (board.right - 25, y)
    # display
    ox = area.x + 540
    w = 380 if tft else 300
    disp = ui.panel(surf, (ox, area.y + 10, w, 170), (20, 50, 140) if tft else (20, 40, 80))
    st = demo_state("happy", int(t * 1000))
    if tft:
        scr = pygame.Rect(disp.x + 30, disp.y + 54, w - 60, 104)
        pygame.draw.rect(surf, (4, 6, 16), scr)
        pygame.draw.rect(surf, (70, 50, 120), scr.inflate(-30, -8), 1)
        img = ui.oled_surface(ui.render_pet(st), 1, on=(125, 235, 255), off=(4, 6, 16), grid=False)
        img = pygame.transform.scale(img, (190, 95))
        surf.blit(img, img.get_rect(center=scr.center))
    else:
        scr = pygame.Rect(disp.x + 40, disp.y + 50, 220, 105)
        pygame.draw.rect(surf, (5, 10, 20), scr)
        img = ui.oled_surface(ui.render_pet(st), 1, grid=False)
        surf.blit(pygame.transform.scale(img, (200, 100)), (scr.x + 10, scr.y + 3))
    gap = (w - 60) // (len(dpins) - 1)
    for i, (nm, link) in enumerate(dpins):
        x = disp.x + 30 + i * gap
        pygame.draw.circle(surf, (210, 180, 80), (x, disp.y + 18), 6)
        ui.text(surf, nm, (x, disp.y + 36), 12, C["text"], True, "center")
        _wire(surf, pin_pos[link], (x, disp.y + 18), pins[link][1], t)
    if tft:
        ui.text(surf, "TFT colorida 0.96\" 80x160 (ST7735, SPI)", (disp.centerx, disp.bottom + 14), 15, C["muted"], align="center")
        ui.text(surf, "Resistor de 1k em série em SCL, SDA, RES, DC e CS (a tela é de 3.3 V).",
                (disp.centerx, disp.bottom + 36), 14, C["yellow"], align="center")
    else:
        ui.text(surf, "Display OLED I2C", (disp.centerx, disp.bottom + 14), 15, C["muted"], align="center")
    # botoes
    for i in range(3):
        bx = area.x + 560 + i * 140
        by = area.bottom - 110
        pygame.draw.rect(surf, (40, 40, 50), (bx - 30, by - 30, 60, 60), border_radius=8)
        pygame.draw.circle(surf, C["yellow"], (bx, by), 20)
        ui.text(surf, "ABC"[i], (bx, by), 18, (90, 20, 60), True, "center")
        leg1, leg2 = (bx - 22, by - 30), (bx + 22, by + 30)
        _wire(surf, pin_pos[nb + i], leg1, pins[nb + i][1], t)
        pygame.draw.line(surf, gray, leg2, (bx + 22, by + 48), 3)
    rail_y = area.bottom - 110 + 48
    x_a, x_c = area.x + 560 - 40, area.x + 560 + 280 + 40
    pygame.draw.line(surf, gray, (x_a, rail_y), (x_c, rail_y), 4)
    ui.text(surf, "GND", (x_c + 8, rail_y), 13, C["muted"], True, "midleft")
    gx, gy = pin_pos[1]
    pts = [(gx, gy), (gx + 70, gy), (gx + 70, rail_y), (x_a, rail_y)]
    pygame.draw.lines(surf, gray, False, pts, 3)
    ui.text(surf, "Cada botão: uma perna no pino, a outra no GND (não precisa resistor).",
            (area.x + 700, area.bottom - 22), 15, C["muted"], align="center")
    ui.text(surf, "Fone ou caixinha de som na saída SPK. O microfone já vem no shield.",
            (area.x + 700, area.bottom + 2), 15, C["muted"], align="center")


def _wire(surf, a, b, col, t, dash=False):
    pts = []
    for i in range(25):
        u = i / 24
        x = a[0] + (b[0] - a[0]) * u
        y = a[1] + (b[1] - a[1]) * (3 * u * u - 2 * u * u * u)
        pts.append((x, y))
    if dash:
        for i in range(0, len(pts) - 1, 2):
            pygame.draw.line(surf, col, pts[i], pts[i + 1], 3)
    else:
        pygame.draw.lines(surf, col, False, pts, 4)
    k = int((t * 0.5 % 1.0) * (len(pts) - 1))
    pygame.draw.circle(surf, (255, 255, 255), (int(pts[k][0]), int(pts[k][1])), 3)


class WiringScreen(Screen):
    def draw(self, surf, dt):
        ui.text(surf, "Ligações do hardware", (SIDEBAR_W + 40, 30), 32, C["text"], True)
        ui.text(surf, "Encaixe o shield VS1053 em cima do Arduino Uno e ligue o resto assim:",
                (SIDEBAR_W + 40, 76), 17, C["muted"])
        draw_wiring(surf, pygame.Rect(SIDEBAR_W + 10, 110, 1000, 420), self.app.t, self.app.s)
        ui.panel(surf, (SIDEBAR_W + 40, 548, 940, 150))
        tips = ("Problemas comuns:\n"
                "* TFT branca, cortada ou com cores trocadas: use 'Testar a tela' em Configurações e ajuste.\n"
                "* Sem som: confira o fone na saída SPK e o volume. Alguns shields precisam do 'ajuste MIDI'.\n"
                "* Microfone mudo: aumente o ganho do microfone ou desligue 'usar microfone do shield' para usar o do PC.\n"
                "* Erro ao gravar: feche a Arduino IDE ou qualquer Monitor Serial aberto na mesma porta COM.")
        ui.text_block(surf, tips, (SIDEBAR_W + 62, 562), 900, 16)


# ===================================================================== INICIO
class HomeScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.fb = R.Frame()
        self.fb2 = R.Frame()
        self.confetti = ui.Confetti((SIDEBAR_W, 0, ui.W - SIDEBAR_W, ui.H))
        self.last_state = None
        comp = app.comp
        self.btn_chat = ui.Button((CX - 150, 640, 300, 48), "Brincar com o pet no PC", lambda: app.go("chat"), "secondary", "i_chat", 16)
        self.btn_retry = ui.Button((CX - 110, 600, 220, 48), "Tentar de novo", lambda: comp.mgr.retry(), "primary")
        self.btn_reprog = ui.Button((900, 248, 280, 40), "Reprogramar o Arduino", lambda: comp.mgr.reprogram(), "secondary", size=15)
        x0 = SIDEBAR_W + 30
        self.act_btns = []
        for i, (act, ic, lbl) in enumerate(A.MENU_ITEMS[:5]):
            b = ui.Button((x0 + i * 112, 400, 104, 46), lbl, (lambda a=act: comp.do_action(a)), "secondary", ic, 14)
            self.act_btns.append(b)
        self.mic = ui.Button((x0, 470, 240, 54), "Segure para falar", self._mic, "primary", "i_mic", 16)
        self.mic.hold = True
        self.inp = ui.TextInput((x0 + 255, 470, 320, 54), "", "Ou escreva aqui e Enter", on_enter=self._send)

    def _mic(self, down):
        if down:
            self.app.comp.start_listen()
        else:
            self.app.comp.stop_listen()

    def _send(self, v):
        if self.app.comp.send_text(v):
            self.inp.value = ""

    def handle(self, ev):
        st = self.app.comp.mgr.state
        if st == "ready":
            for w in self.act_btns + [self.mic, self.inp, self.btn_reprog]:
                if w.handle(ev):
                    return True
        elif st == "error":
            if self.btn_retry.handle(ev) or self.btn_chat.handle(ev):
                return True
        elif st == "waiting":
            if self.btn_chat.handle(ev):
                return True
        return False

    def title(self, surf, s, sub=None, y=48, col=None):
        ui.text(surf, s, (CX, y), 36, col or C["text"], True, "center")
        if sub:
            ui.text(surf, sub, (CX, y + 46), 18, C["muted"], align="center")

    def draw(self, surf, dt):
        mgr = self.app.comp.mgr
        t = self.app.t
        st = mgr.state
        if st != self.last_state:
            if st == "done":
                self.confetti.burst(160)
            self.last_state = st
        getattr(self, "draw_" + st)(surf, t, mgr)
        self.confetti.update_draw(surf, dt)

    def _scene(self, surf, t, anim, plugged, glow=0.0):
        st = demo_state(anim, int(t * 1000), self.app.s.get("pet_name", "PIXO"))
        pc_port = ui.draw_pc(surf, (CX - 270, 330), 1.05, t, ui.render_pet(st, self.fb))
        usb = ui.draw_arduino(surf, (CX + 250, 330), 1.05, t, glow=glow)
        return ui.draw_cable(surf, pc_port, usb, t, plugged), usb

    def draw_waiting(self, surf, t, mgr):
        dots = "." * (1 + int(t * 2) % 3)
        self.title(surf, "Esperando o Arduino" + dots, "Ligue o cabo USB do Arduino no computador. Eu programo ele sozinho.")
        for k in range(3):  # ondas em volta do Arduino
            ph = (t * 0.8 + k / 3) % 1.0
            rad = int(60 + ph * 140)
            col = ui.lerp(C["cyan"], C["bg"], ph)
            pygame.draw.circle(surf, col, (CX + 250, 330), rad, 3)
        self._scene(surf, t, "sleepy", False)
        ui.panel(surf, (SIDEBAR_W + 60, 500, ui.W - SIDEBAR_W - 120, 120))
        steps = ["1. Encaixe o shield VS1053 no Arduino Uno", "2. Ligue o display e os botões (veja Ligações)",
                 "3. Conecte o cabo USB no PC"]
        for i, s in enumerate(steps):
            ui.text(surf, s, (SIDEBAR_W + 90, 518 + i * 30), 18)
        if mgr.message:
            ui.text(surf, mgr.message, (CX, 140), 16, C["yellow"], align="center")
        self.btn_chat.draw(surf)

    def draw_checking(self, surf, t, mgr):
        self.title(surf, "Encontrei um Arduino!", mgr.message)
        self._scene(surf, t, "curious", True, glow=0.5)
        ui.spinner(surf, (CX, 560), t, 22)
        ui.text(surf, "Vendo se ele já tem o Tamagotchi gravado...", (CX, 610), 17, C["muted"], align="center")

    def draw_programming(self, surf, t, mgr):
        self.title(surf, "Programando o Arduino", "Não desligue o cabo. Isso leva uns 30 segundos na primeira vez.")
        pts, _ = self._scene(surf, t, "determined", True, glow=(math.sin(t * 6) + 1) / 3)
        for k in range(10):  # bits voando pelo cabo
            u = (t * 0.55 + k / 10) % 1.0
            p = pts[int(u * (len(pts) - 1))]
            ui.text(surf, "10"[(k + int(t * 4)) % 2], (p[0], p[1] - 20), 20, C["green"], True, "center")
        bar = pygame.Rect(SIDEBAR_W + 110, 500, ui.W - SIDEBAR_W - 220, 34)
        pygame.draw.rect(surf, C["bg2"], bar, border_radius=17)
        fill = bar.copy()
        fill.w = max(34, int(bar.w * mgr.progress))
        pygame.draw.rect(surf, C["green"], fill, border_radius=17)
        clip = surf.get_clip()
        surf.set_clip(fill.inflate(-8, 0))
        for i in range(0, fill.w + 28, 28):  # listras andando
            x = fill.x + (i + int(t * 40)) % (fill.w + 28)
            pygame.draw.line(surf, ui.lerp(C["green"], (255, 255, 255), 0.25), (x, fill.y + 4), (x - 12, fill.bottom - 4), 6)
        surf.set_clip(clip)
        pygame.draw.rect(surf, C["line"], bar, 2, border_radius=17)
        ui.text(surf, f"{int(mgr.progress * 100)}%", bar.center, 18, (20, 30, 20), True, "center")
        ui.text(surf, mgr.stage + "...", (CX, 552), 19, C["text"], True, "center")
        self._log(surf, mgr, 584, 5)

    def _log(self, surf, mgr, y, n):
        box = pygame.Rect(SIDEBAR_W + 110, y, ui.W - SIDEBAR_W - 220, n * 20 + 16)
        pygame.draw.rect(surf, (14, 12, 26), box, border_radius=10)
        lines = [l for l in mgr.logs if l.strip()][-n:]
        for i, l in enumerate(lines):
            ui.text(surf, l[:130], (box.x + 12, box.y + 8 + i * 20), 13, C["muted"], mono=True)

    def draw_done(self, surf, t, mgr):
        self.title(surf, "Pronto! Seu Tamagotchi está vivo!", "Agora é só cuidar dele. Segure o botão C para conversar.", 60, C["green"])
        st = demo_state("celebrate", int(t * 1000), self.app.s.get("pet_name", "PIXO"))
        ui.draw_oled(surf, ui.render_pet(st, self.fb), (CX, 360), 5)

    def draw_error(self, surf, t, mgr):
        self.title(surf, "Ops, algo deu errado", None, 48, C["orange"])
        ui.text_block(surf, mgr.message, (SIDEBAR_W + 110, 100), ui.W - SIDEBAR_W - 220, 17, C["text"])
        self._scene(surf, t, "sorry", False)
        self._log(surf, mgr, 470, 5)
        self.btn_retry.rect.y = 610
        self.btn_retry.draw(surf)

    def draw_ready(self, surf, t, mgr):
        comp = self.app.comp
        x0 = SIDEBAR_W + 30
        ui.text(surf, f"{comp.pet.name} está online", (x0, 22), 30, C["text"], True)
        ui.text(surf, "Este é o espelho do display do Arduino. Tudo que acontece lá aparece aqui.", (x0, 62), 16, C["muted"])
        ui.draw_oled(surf, ui.render_pet(comp.pet, self.fb), (x0 + 290, 235), 4, dim=comp.pet.sleeping)
        for b in self.act_btns:
            b.draw(surf)
        self.mic.label = "Ouvindo..." if comp.listening else "Segure para falar"
        self.mic.draw(surf)
        self.inp.draw(surf, t)
        # status da conversa
        status = {"ouvindo": "Ouvindo você...", "entendendo": "Entendendo o que você falou...",
                  "pensando": "Claude pensando...", "preparando voz": "Preparando a voz...", "falando": "Falando..."}.get(comp.status, "")
        if status:
            ui.spinner(surf, (x0 + 14, 555), t, 9)
            ui.text(surf, status, (x0 + 34, 545), 17, C["yellow"], True)
        y = 590
        for who, msg, _ in comp.chat[-3:]:
            col = {"voce": C["cyan"], "pet": C["pink"]}.get(who, C["muted"])
            nm = {"voce": "Você", "pet": comp.pet.name}.get(who, "Info")
            y = ui.text_block(surf, f"{nm}: {msg}", (x0, y), 590, 15, col) + 2
            if y > 705:
                break
        # cartao do Arduino
        px = 880
        ui.panel(surf, (px, 100, 320, 210))
        ui.text(surf, "Arduino", (px + 20, 116), 22, C["green"], True)
        dev = comp.dev
        info = dev.hello if dev and dev.hello else {}
        rows = [("Porta", mgr.port or "-"), ("Firmware", f"v{info.get('fw', '?')} atualizado"),
                ("Chip de som", "VS1053 ok" if info.get("vs") == 4 else f"não detectado ({info.get('vs', '?')})")]
        yy = 154
        for k, v in rows:
            ui.text(surf, k, (px + 20, yy), 15, C["muted"])
            ui.text(surf, v, (px + 300, yy), 15, C["text"] if "nao" not in v else C["orange"], True, "right")
            yy += 28
        self.btn_reprog.rect.topleft = (px + 20, 248)
        self.btn_reprog.draw(surf)
        ui.panel(surf, (px, 330, 320, 160))
        ui.stat_bars(surf, comp.pet, (px + 18, 346), 284, 15)
        ui.panel(surf, (px, 510, 320, 190), C["bg2"])
        ui.text_block(surf, "No Arduino:\nA abre o menu\nB escolhe\nC volta ou faz carinho\nSegure C para falar",
                      (px + 20, 524), 280, 16, C["muted"])


# ===================================================================== CONVERSAR (mascote do PC)
class ChatScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.fb = R.Frame()
        self.pressed = None
        self.egg_btns = []
        comp = app.comp
        self.inp = ui.TextInput((760, 640, 360, 52), "", "Escreva para o pet e aperte Enter", on_enter=self._send)
        self.send_b = ui.Button((1130, 640, 90, 52), "Enviar", lambda: self._send(self.inp.value), "primary", size=16)
        self.mic = ui.Button((760, 574, 460, 54), "Segure para falar (ou segure ESPAÇO)", self._mic, "cyan", "i_mic", 16)
        self.mic.hold = True
        self.acts = []
        for i, (act, ic, lbl) in enumerate(A.MENU_ITEMS[:5]):
            self.acts.append(ui.Button((SIDEBAR_W + 20 + i * 104, 655, 98, 44), lbl, (lambda a=act: comp.do_action(a)), "secondary", ic, 14))
        self.clear_b = ui.Button((1100, 20, 120, 34), "Limpar", self._clear, "ghost", size=14)
        self.space_down = False

    def _clear(self):
        self.app.comp.chat.clear()

    def _mic(self, down):
        if down:
            self.app.comp.start_listen()
        else:
            self.app.comp.stop_listen()

    def _send(self, v):
        if self.app.comp.send_text(v):
            self.inp.value = ""

    def handle(self, ev):
        comp = self.app.comp
        for w in [self.inp, self.send_b, self.mic, self.clear_b] + self.acts:
            if w.handle(ev):
                return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            for i, r in enumerate(self.egg_btns):
                if r.collidepoint(ev.pos):
                    self.press(i)
                    return True
        if ev.type == pygame.MOUSEBUTTONUP:
            self.pressed = None
        if ui.TextInput.active is None and ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.press(ev.key - pygame.K_1)
                return True
            if ev.key == pygame.K_SPACE and not self.space_down:
                self.space_down = True
                comp.start_listen()
                return True
        if ev.type == pygame.KEYUP:
            if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.pressed = None
            if ev.key == pygame.K_SPACE and self.space_down:
                self.space_down = False
                comp.stop_listen()
        return False

    def press(self, i):
        comp = self.app.comp
        pet = comp.pet
        self.pressed = i
        if i == 0:
            pet.button_a()
        elif i == 1:
            item = pet.button_b(apply=comp.dev is None)
            if item == "talk":
                comp.start_listen() if not comp.listening else comp.stop_listen()
            elif item and comp.dev:
                comp.dev.action(A.ACTIONS.index(item))
        else:
            if comp.listening == "pc":
                comp.stop_listen()
            elif pet.button_c(apply=comp.dev is None) == "pet" and comp.dev:
                comp.dev.action(len(A.ACTIONS))  # ACT_PET

    def draw(self, surf, dt):
        comp = self.app.comp
        t = self.app.t
        ui.text(surf, "Conversar pelo PC", (SIDEBAR_W + 30, 18), 30, C["text"], True)
        sub = "Espelhando no Arduino conectado" if comp.dev else "Mascote virtual (funciona sem Arduino)"
        ui.text(surf, sub, (SIDEBAR_W + 30, 58), 15, C["green"] if comp.dev else C["muted"])
        self.egg_btns = ui.draw_egg(surf, (SIDEBAR_W + 270, 350), ui.render_pet(comp.pet, self.fb), 3, t,
                                    dim=comp.pet.sleeping, pressed=self.pressed)
        ui.text(surf, "Teclas 1, 2, 3 = botões A, B, C", (SIDEBAR_W + 270, 628), 14, C["muted"], align="center")
        for b in self.acts:
            b.draw(surf)
        # painel de conversa
        box = ui.panel(surf, (760, 70, 460, 490))
        ui.stat_bars(surf, comp.pet, (780, 86), 420, 15)
        pygame.draw.line(surf, C["line"], (780, 212), (1200, 212), 2)
        clip = surf.get_clip()
        area = pygame.Rect(770, 218, 440, 336)
        surf.set_clip(area)
        y = area.bottom - 6
        for who, msg, _ in reversed(comp.chat[-14:]):
            lines = ui.wrap(msg, 16, 330)
            hgt = len(lines) * 21 + 16
            y -= hgt + 8
            if y + hgt < area.y:
                break
            me = who == "voce"
            col = C["cyan"] if me else (C["pink"] if who == "pet" else C["panel2"])
            fg = (20, 20, 40) if who in ("voce", "pet") else C["muted"]
            w = max(ui.font(16).size(l)[0] for l in lines) + 24
            bx = area.right - w - 8 if me else area.x + 8
            pygame.draw.rect(surf, col, (bx, y, w, hgt), border_radius=12)
            for i, l in enumerate(lines):
                ui.text(surf, l, (bx + 12, y + 8 + i * 21), 16, fg)
        surf.set_clip(clip)
        if not comp.chat:
            ui.text_block(surf, f"Diga oi para o {comp.pet.name}! Segure o botão de microfone e fale, ou escreva abaixo.",
                          (790, 300), 400, 17, C["muted"])
        status = {"ouvindo": "Ouvindo...", "entendendo": "Entendendo...", "pensando": "Claude pensando...",
                  "preparando voz": "Preparando a voz...", "falando": "Falando..."}.get(comp.status, "")
        if status:
            ui.spinner(surf, (790, 40), t, 9)
            ui.text(surf, status, (808, 28), 17, C["yellow"], True)
        if comp.listening == "pc":
            lvl = min(1.0, comp.mic.level)
            pygame.draw.rect(surf, C["green"], (760, 566, int(460 * lvl), 5), border_radius=2)
        self.mic.label = "Ouvindo... solte para enviar" if comp.listening else "Segure para falar (ou segure ESPAÇO)"
        self.mic.draw(surf)
        self.inp.draw(surf, t)
        self.send_b.enabled = not comp.busy
        self.send_b.draw(surf)
        self.clear_b.draw(surf)
        if not self.app.s.get("anthropic_api_key"):
            ui.text(surf, "Sem chave do Claude: coloque em Configurações.", (990, 700), 14, C["orange"], align="center")


# ===================================================================== ANIMACOES
class GalleryScreen(Screen):
    COLS = 7

    def __init__(self, app):
        super().__init__(app)
        self.sel = 0
        self.scroll = 0
        self.fb = R.Frame()
        self.thumbs = {}
        self.rr = 0
        self.btn_dev = ui.Button((600, 210, 220, 46), "Mostrar no Arduino", self._to_dev, "primary", size=16)
        self.btn_pet = ui.Button((835, 210, 200, 46), "Tocar no pet do PC", self._to_pet, "secondary", size=16)

    def _to_dev(self):
        if self.app.comp.dev:
            self.app.comp.dev.anim(self.sel, 6)

    def _to_pet(self):
        self.app.comp.pet.play(self.sel, 6000)

    def grid_rect(self, i):
        c, r = i % self.COLS, i // self.COLS
        return pygame.Rect(SIDEBAR_W + 22 + c * 142, 300 + r * 92 - self.scroll, 134, 86)

    def handle(self, ev):
        if self.btn_pet.handle(ev) or self.btn_dev.handle(ev):
            return True
        if ev.type == pygame.MOUSEWHEEL:
            rows = (len(A.ANIMATIONS) + self.COLS - 1) // self.COLS
            self.scroll = max(0, min(rows * 92 - 410, self.scroll - ev.y * 40))
            return True
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and ev.pos[1] > 290:
            for i in range(len(A.ANIMATIONS)):
                if self.grid_rect(i).collidepoint(ev.pos):
                    self.sel = i
                    return True
        return False

    def draw(self, surf, dt):
        t = self.app.t
        now = int(t * 1000)
        a = A.ANIMATIONS[self.sel]
        ui.text(surf, "As 50 animações", (SIDEBAR_W + 30, 18), 30, C["text"], True)
        ui.text(surf, "O Claude escolhe uma destas em cada resposta. Clique para ver.", (SIDEBAR_W + 30, 58), 15, C["muted"])
        st = demo_state(self.sel, now, self.app.s.get("pet_name", "PIXO"))
        ui.draw_oled(surf, ui.render_pet(st, self.fb), (SIDEBAR_W + 175, 190), 2)
        ui.text(surf, f"#{self.sel}  {a[1]}", (600, 106), 28, C["pink"], True)
        ui.text(surf, f"nome interno: {a[0]}", (600, 144), 15, C["muted"], mono=True)
        ui.text(surf, f"quando usar: {a[7]}", (600, 168), 15, C["muted"])
        self.btn_dev.enabled = self.app.comp.dev is not None
        self.btn_dev.draw(surf)
        self.btn_pet.draw(surf)
        # miniaturas (atualiza algumas por quadro para ficar leve)
        n = len(A.ANIMATIONS)
        for _ in range(6):
            i = self.rr % n
            self.rr += 1
            self.thumbs[i] = ui.oled_surface(ui.render_pet(demo_state(i, now), R.Frame()), 1, grid=False)
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(SIDEBAR_W, 290, ui.W - SIDEBAR_W, ui.H - 290))
        for i in range(n):
            r = self.grid_rect(i)
            if r.bottom < 290 or r.y > ui.H:
                continue
            sel = i == self.sel
            pygame.draw.rect(surf, C["pink"] if sel else C["panel"], r, border_radius=8)
            img = self.thumbs.get(i)
            if img:
                surf.blit(img, (r.x + 3, r.y + 3))
            ui.text(surf, f"{i} {A.ANIMATIONS[i][1]}", (r.centerx, r.bottom - 10), 12,
                    (40, 16, 40) if sel else C["muted"], sel, "center")
        surf.set_clip(clip)
        pygame.draw.line(surf, C["line"], (SIDEBAR_W + 20, 286), (ui.W - 20, 286), 2)


# ===================================================================== CONFIGURACOES
PIN_OPTS = [(p, p) for p in ("A0", "A1", "A2", "A3", "3", "4", "5")]
TFT_PIN_OPTS = [(10, "D10"), (4, "D4"), (5, "D5"), (3, "D3"), (17, "A3"), (16, "A2")]
TFT_PIN_OPTS_NONE = TFT_PIN_OPTS + [(-1, "Nenhum")]
RESERVED = {2: "DREQ do shield", 6: "XCS do shield", 7: "XDCS do shield", 8: "XRESET do shield", 9: "SD do shield",
            11: "SPI", 12: "SPI", 13: "SPI"}


def pin_num(v):
    v = str(v).strip().upper()
    return 14 + int(v[1:]) if v.startswith("A") else int(v)


def pin_conflict(s):
    """Retorna uma mensagem se dois itens usam o mesmo pino."""
    used = {}
    items = [("botão A", s["pin_btn_a"]), ("botão B", s["pin_btn_b"]), ("botão C", s["pin_btn_c"])]
    if s.get("oled_driver") == "ST7735":
        items += [("TFT CS", s["tft_cs"]), ("TFT DC", s["tft_dc"]), ("TFT RES", s["tft_rst"]), ("TFT BLK", s["tft_blk"])]
    else:
        items += [("OLED SDA", "A4"), ("OLED SCL", "A5")]
    for name, v in items:
        n = pin_num(v)
        if n < 0:
            continue
        if n in RESERVED:
            return f"{name} está no pino {pin_label(n)}, que é usado pelo {RESERVED[n]}."
        if n in used:
            return f"{name} e {used[n]} estão no mesmo pino ({pin_label(n)})."
        used[n] = name
    return None


class SettingsScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.scroll = 0
        self.msg = ("", C["muted"])
        self.rows = []
        self.build()
        self.save_b = ui.Button((ui.W - 470, 650, 210, 50), "Salvar", self.save, "primary")
        self.save_up = ui.Button((ui.W - 250, 650, 230, 50), "Salvar e programar", lambda: self.save(True), "ok")

    def on_show(self):
        self.build()

    def build(self):
        s = self.app.s
        R_ = []

        def sec(title):
            R_.append(("sec", title))

        def row(label, help_, w, key=None, getter=None):
            R_.append(("row", label, help_, w, key, getter))

        sec("Pet")
        row("Nome do pet", "Aparece no display (até 12 letras).", ui.TextInput((0, 0, 380, 42), s["pet_name"], maxlen=12), "pet_name")
        lang = ui.Choice((0, 0, 380, 42), SET.LANGUAGES, s["language"], self._lang_changed)
        row("Idioma", "Idioma da conversa, da voz e do display.", lang, "language")
        row("Personalidade", "Como ele deve ser. Ex: preguiçoso e engraçado.", ui.TextInput((0, 0, 380, 42), s["personality"]), "personality")
        row("Velocidade das necessidades", "Quanto tempo leva para a fome, sono e sujeira subirem.",
            ui.Choice((0, 0, 380, 42), [(30, "Rápido (30 s)"), (90, "Normal (90 s)"), (180, "Lento (3 min)"), (600, "Bem lento (10 min)")],
                      int(s["decay_seconds"])), "decay_seconds")
        sec("Claude (o cérebro)")
        self.key = ui.TextInput((0, 0, 380, 42), s["anthropic_api_key"], "sk-ant-...", password=True)
        row("Chave do Claude", "Fica salva só neste PC.", self.key, "anthropic_api_key")
        row("", "", ui.Button((0, 0, 185, 40), "Testar chave", self.test_key, "secondary", size=15))
        row("Modelo", "Opus pensa melhor, Haiku responde mais rápido e gasta menos.",
            ui.Choice((0, 0, 380, 42), SET.MODELS, s["claude_model"]), "claude_model")
        row("Esforço", "Low deixa a resposta mais rápida (bom para voz).",
            ui.Choice((0, 0, 380, 42), [("low", "Rápido (low)"), ("medium", "Médio"), ("high", "Pensa mais (high)")], s["claude_effort"]), "claude_effort")
        row("Memória da conversa", "Quantas trocas ele lembra.",
            ui.Choice((0, 0, 380, 42), [(4, "Curta (4)"), (10, "Normal (10)"), (20, "Longa (20)")], int(s["history_turns"])), "history_turns")
        row("", "", ui.Button((0, 0, 230, 40), "Apagar memória", self.clear_mem, "danger", size=15))
        sec("Voz e ouvido")
        row("Voz (TTS)", "Edge TTS é grátis e soa natural. A do Windows funciona sem internet.",
            ui.Choice((0, 0, 380, 42), [("edge", "Edge TTS neural (grátis)"), ("windows", "Voz do Windows (offline)"), ("off", "Sem voz")], s["tts_engine"]), "tts_engine")
        self.voice = ui.Choice((0, 0, 380, 42), [(v, v) for v in SET.VOICES.get(s["language"], [])], s["tts_voice"])
        row("Qual voz", "Vozes neurais gratuitas.", self.voice, "tts_voice")
        pitch = int(str(s["tts_pitch"]).replace("Hz", "").replace("+", "") or 0)
        row("Tom da voz", "Mais alto deixa mais fofinho.", ui.Slider((0, 0, 320, 42), -50, 80, pitch, fmt="{:+d} Hz"), "tts_pitch",
            lambda w: f"{int(w.value):+d}Hz")
        rate = int(str(s["tts_rate"]).replace("%", "").replace("+", "") or 0)
        row("Velocidade da fala", "", ui.Slider((0, 0, 320, 42), -50, 50, rate, fmt="{:+d} %"), "tts_rate",
            lambda w: f"{int(w.value):+d}%")
        row("", "", ui.Button((0, 0, 200, 40), "Ouvir a voz", self.test_voice, "cyan", "i_note", 15))
        row("Reconhecimento de fala", "Google é grátis e não precisa instalar nada.",
            ui.Choice((0, 0, 380, 42), [("google", "Google (grátis, online)"), ("whisper", "Whisper local (offline)")], s["stt_engine"]), "stt_engine")
        row("Usar o microfone do shield", "Desligado: ao segurar C, grava pelo microfone do PC.", ui.Toggle((0, 0), s["device_mic"]), "device_mic")
        row("Saída do som", "Onde o pet fala quando o Arduino está ligado.",
            ui.Choice((0, 0, 380, 42), [("arduino", "Alto-falante do Arduino"), ("pc", "Caixas do PC"), ("both", "Os dois")], s["audio_output"]), "audio_output")
        row("Volume do Arduino", "", ui.Slider((0, 0, 320, 42), 0, 100, int(s["volume"]), fmt="{:d} %"), "volume")
        sec("Hardware (o Studio reprograma sozinho)")
        row("Placa", "", ui.Choice((0, 0, 380, 42), [("arduino:avr:uno", "Arduino Uno"), ("arduino:avr:nano", "Arduino Nano"),
                                                      ("arduino:avr:nano:cpu=atmega328old", "Nano (bootloader antigo)"),
                                                      ("arduino:avr:mega", "Arduino Mega 2560")], s["board_fqbn"]), "board_fqbn")
        ports = [("", "Automático")] + [(p[0], f"{p[0]} {p[1][:22]}") for p in F.list_ports()]
        row("Porta USB", "Automático encontra o Arduino sozinho.", ui.Choice((0, 0, 380, 42), ports, s["serial_port"]), "serial_port")
        row("Velocidade serial", "250000 é o ideal para o audio.",
            ui.Choice((0, 0, 380, 42), [(115200, "115200"), (250000, "250000 (recomendado)"), (500000, "500000")], int(s["baud"])), "baud")
        row("Modelo do display", "A TFT colorida de 8 pinos é ST7735. OLED de 4 pinos: SSD1306 ou SH1106.",
            ui.Choice((0, 0, 380, 42), [("ST7735", "TFT colorida 0.96\" 80x160"), ("SSD1306", "OLED I2C SSD1306"),
                                        ("SH1106", "OLED I2C SH1106 (1.3\")")], s["oled_driver"]), "oled_driver")
        row("TFT: pino CS", "", ui.Choice((0, 0, 380, 42), TFT_PIN_OPTS, int(s["tft_cs"])), "tft_cs")
        row("TFT: pino DC", "", ui.Choice((0, 0, 380, 42), TFT_PIN_OPTS, int(s["tft_dc"])), "tft_dc")
        row("TFT: pino RES", "Nenhum = RES ligado no pino RESET do Arduino.",
            ui.Choice((0, 0, 380, 42), TFT_PIN_OPTS_NONE, int(s["tft_rst"])), "tft_rst")
        row("TFT: pino BLK (luz)", "Nenhum = BLK ligado no 3.3V (luz sempre acesa).",
            ui.Choice((0, 0, 380, 42), TFT_PIN_OPTS_NONE, int(s["tft_blk"])), "tft_blk")
        row("TFT: ajuste horizontal", "Se a imagem estiver cortada nos lados.",
            ui.Choice((0, 0, 380, 42), [(v, str(v)) for v in (1, 0, 2, 3, 24, 26)], int(s["tft_xofs"])), "tft_xofs")
        row("TFT: ajuste vertical", "Se a imagem estiver cortada em cima ou embaixo.",
            ui.Choice((0, 0, 380, 42), [(v, str(v)) for v in (26, 24, 25, 27, 0, 1)], int(s["tft_yofs"])), "tft_yofs")
        row("TFT: inverter cores", "Se o fundo aparecer branco, mude.", ui.Toggle((0, 0), s["tft_invert"]), "tft_invert")
        row("TFT: trocar vermelho e azul", "Se o quadrado vermelho do teste sair azul, mude.", ui.Toggle((0, 0), s["tft_bgr"]), "tft_bgr")
        row("TFT: cor do pet", "", ui.Choice((0, 0, 380, 42), [(0, "Ciano"), (1, "Verde"), (2, "Rosa"), (3, "Branco"),
                                                              (4, "Amarelo")], int(s["tft_color"])), "tft_color")
        row("", "", ui.Button((0, 0, 260, 40), "Testar a tela no Arduino", self.test_display, "cyan", size=15))
        row("OLED: endereço I2C", "Se o display ficar apagado, troque.",
            ui.Choice((0, 0, 380, 42), [("0x3C", "0x3C"), ("0x3D", "0x3D")], s["oled_addr"]), "oled_addr")
        row("Girar a tela 180 graus", "", ui.Toggle((0, 0), s["oled_flip"]), "oled_flip")
        row("Brilho da tela", "", ui.Slider((0, 0, 320, 42), 1, 255, int(s["oled_contrast"])), "oled_contrast")
        row("Pino do botão A", "", ui.Choice((0, 0, 380, 42), PIN_OPTS, s["pin_btn_a"]), "pin_btn_a")
        row("Pino do botão B", "", ui.Choice((0, 0, 380, 42), PIN_OPTS, s["pin_btn_b"]), "pin_btn_b")
        row("Pino do botão C", "", ui.Choice((0, 0, 380, 42), PIN_OPTS, s["pin_btn_c"]), "pin_btn_c")
        row("Ganho do microfone", "Automático ajusta sozinho.",
            ui.Choice((0, 0, 380, 42), [(0, "Automático"), (1024, "1x"), (2048, "2x"), (4096, "4x"), (8192, "8x")], int(s["rec_gain"])), "rec_gain")
        row("Usar entrada MIC (P2) como linha", "Ligue se usar um microfone externo com fio.", ui.Toggle((0, 0), s["rec_line_in"]), "rec_line_in")
        row("Ajuste MIDI do VS1053", "Só para shields que ficam mudos (iniciam em modo MIDI).", ui.Toggle((0, 0), s["vs_midi_fix"]), "vs_midi_fix")
        sec("Outros")
        row("", "", ui.Button((0, 0, 230, 40), "Rever o tutorial", lambda: self.app.go("tutorial"), "secondary", size=15))
        row("", "", ui.Button((0, 0, 260, 40), "Novo ovo (zerar o pet)", self.reset_pet, "danger", size=15))
        self.rows = R_
        self.lang = lang

    def _lang_changed(self, v):
        vs = SET.VOICES.get(v, [])
        self.voice.set_options([(x, x) for x in vs], vs[0] if vs else None)

    def layout(self):
        y = 90 - self.scroll
        out = []
        for r in self.rows:
            if r[0] == "sec":
                out.append((r, y))
                y += 56
            else:
                out.append((r, y))
                w = r[3]
                w.rect.topleft = (SIDEBAR_W + 450, y)
                y += 64 if r[1] or r[2] else 52
        self.content_h = y + self.scroll
        return out

    def values(self):
        s = dict(self.app.s)
        for r in self.rows:
            if r[0] != "row" or not r[4]:
                continue
            w, key, getter = r[3], r[4], r[5]
            if getter:
                v = getter(w)
            elif isinstance(w, ui.TextInput):
                v = w.value.strip()
            else:
                v = w.value
            s[key] = v
        return s

    def test_display(self):
        dev = self.app.comp.dev
        if not dev:
            self.msg = ("Conecte o Arduino primeiro.", C["yellow"])
            return
        dev.test_display()
        self.msg = ("Olhe a tela: moldura branca encostando nas 4 bordas e quadrados vermelho, verde e azul, nessa ordem. "
                    "Se não, ajuste e clique em Salvar e programar.", C["cyan"])

    def save(self, program=False):
        new = self.values()
        err = pin_conflict(new)
        if err:
            self.msg = ("Não salvei: " + err, C["red"])
            return
        if not new.get("pet_name"):
            new["pet_name"] = "PIXO"
        self.app.s.clear()
        self.app.s.update(new)
        SET.save(self.app.s)
        comp = self.app.comp
        comp.apply_settings()
        dev = comp.dev
        if dev and dev.hello and (program or dev.hello.get("hash") != F.expected_hash(self.app.s)):
            comp.mgr.reprogram()
            self.msg = ("Salvo! Reprogramando o Arduino com as novas configurações...", C["green"])
            self.app.go("home")
        elif program and not dev:
            self.msg = ("Salvo! Conecte o Arduino que éu programo ele.", C["green"])
            self.app.go("home")
        else:
            self.msg = ("Configurações salvas.", C["green"])

    def test_key(self):
        self.msg = ("Testando a chave...", C["muted"])

        def run():
            from .brain import test_key
            s = self.values()
            ok, m = test_key(s)
            self.msg = (m, C["green"] if ok else C["red"])
        threading.Thread(target=run, daemon=True).start()

    def test_voice(self):
        self.msg = ("Gerando a voz...", C["muted"])

        def run():
            from . import voice
            s = self.values()
            try:
                sp = voice.tts(f"Oi! Eu sou o {s['pet_name']}. Gostou da minha voz?", s)
                if not sp:
                    self.msg = ("A voz está desligada.", C["yellow"])
                    return
                comp = self.app.comp
                if comp.dev and s.get("audio_output") in ("arduino", "both"):
                    comp.dev.play_audio(sp.device_audio)
                else:
                    comp.player.play(sp)
                self.msg = ("Tocando a voz.", C["green"])
            except Exception as e:
                self.msg = (f"Falha na voz: {str(e)[:120]}", C["red"])
        threading.Thread(target=run, daemon=True).start()

    def clear_mem(self):
        self.app.comp.brain.clear()
        self.msg = ("Memória da conversa apagada.", C["green"])

    def reset_pet(self):
        comp = self.app.comp
        p = comp.pet
        p.hunger = p.happy = p.energy = p.clean = 80
        p.sleeping = False
        p.age_min = 0
        if comp.dev:
            comp.dev.reset_pet()
        self.msg = ("Um ovo novo chocou!", C["green"])

    def handle(self, ev):
        if self.save_b.handle(ev) or self.save_up.handle(ev):
            return True
        if ev.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(self.content_h - 540, self.scroll - ev.y * 50))
            return True
        if hasattr(ev, "pos") and ev.pos[1] > 630:
            return False
        for r, _ in self.layout():
            if r[0] == "row" and r[3].handle(ev):
                return True
        return False

    def draw(self, surf, dt):
        t = self.app.t
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(SIDEBAR_W, 80, ui.W - SIDEBAR_W, 550))
        for r, y in self.layout():
            if y < 40 or y > 640:
                continue
            if r[0] == "sec":
                ui.text(surf, r[1], (SIDEBAR_W + 40, y + 12), 22, C["pink"], True)
                pygame.draw.line(surf, C["line"], (SIDEBAR_W + 40, y + 46), (ui.W - 40, y + 46), 1)
            else:
                _, label, help_, w, key, _g = r
                if label:
                    ui.text(surf, label, (SIDEBAR_W + 40, y + 2), 17, C["text"], True)
                if help_:
                    ui.text(surf, help_, (SIDEBAR_W + 40, y + 26), 13, C["muted"])
                if isinstance(w, ui.TextInput):
                    w.draw(surf, t)
                else:
                    w.draw(surf)
        surf.set_clip(clip)
        pygame.draw.rect(surf, C["bg"], (SIDEBAR_W, 0, ui.W - SIDEBAR_W, 80))
        ui.text(surf, "Configurações", (SIDEBAR_W + 30, 18), 30, C["text"], True)
        ui.text(surf, "Role com a roda do mouse. Mudanças de hardware são gravadas no Arduino automaticamente.",
                (SIDEBAR_W + 30, 56), 14, C["muted"])
        pygame.draw.rect(surf, C["bg2"], (SIDEBAR_W, 632, ui.W - SIDEBAR_W, 88))
        ui.text_block(surf, self.msg[0], (SIDEBAR_W + 30, 660), 480, 16, self.msg[1])
        self.save_b.draw(surf)
        self.save_up.draw(surf)
