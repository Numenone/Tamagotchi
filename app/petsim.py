"""Logica do Tamagotchi (espelho do firmware pet logic em tamagotchi.ino).

Usado pelo mascote virtual do PC. Mesmos numeros, mesmas regras.
"""
import json
import os
import random
import time

from . import animations as A

AI = A.ANIM_INDEX
IDLE_POOL_GOOD = ["idle", "idle", "happy", "curious", "singing", "relaxed", "wink", "dancing", "idle", "bored"]
IDLE_POOL_MEH = ["idle", "bored", "idle", "thinking"]
SLEEP_REST_MS = 5000  # dormindo: +1 de energia a cada 5 s (igual ao firmware)


def clamp(v):
    return max(0, min(100, int(v)))


class PetState:
    def __init__(self, name="PIXO", lang="pt", decay_seconds=90):
        self.name = name
        self.lang = lang
        self.decay_seconds = decay_seconds
        self.hunger = 80
        self.happy = 80
        self.energy = 80
        self.clean = 80
        self.sleeping = False
        self.age_min = 0
        # animacao
        self.anim = AI["hello"]
        self.t = 0
        self.now = 0
        self.talking = False
        self.override = AI["hello"]
        self.override_until = 2500
        self.auto_anim = AI["idle"]
        self.pc_link = True
        # tela
        self.menu_active = False
        self.menu_sel = 0
        self.menu_until = 0
        self.stats_screen = False
        self.stats_until = 0
        self.subtitle = ""
        self.subtitle_start = 0
        self.subtitle_dur = 0
        self.recording = False
        self._last_frame = 0
        self._last_decay = 0
        self._last_age = 0
        self._last_rest = 0
        self._last_pick = -99999
        self.events = []  # acoes executadas (para avisar o Claude)

    # ----------------------------------------------------------------- tempo
    def update(self, now_ms):
        self.now = now_ms
        speed = A.ANIMATIONS[self.anim][6]
        if now_ms - self._last_frame >= speed:
            self._last_frame = now_ms
            self.t = (self.t + 1) & 0xFFFF
        if now_ms - self._last_decay >= self.decay_seconds * 1000:
            self._last_decay = now_ms
            self.decay()
        # dormindo: recupera energia aos poucos (+1 a cada 5 s, de 0 a 100 em ~8 min)
        if self.sleeping and now_ms - self._last_rest >= SLEEP_REST_MS:
            self._last_rest = now_ms
            self.energy = clamp(self.energy + 1)
            if self.energy >= 100:
                self.sleeping = False
                self.play(AI["yawn"], 2500)
        if now_ms - self._last_age >= 60000:
            self._last_age = now_ms
            self.age_min += 1
        if self.override is not None and not self.recording and now_ms > self.override_until:
            self.override = None
            self._last_pick = -99999
        if self.override is None and now_ms - self._last_pick > 8000:
            self._last_pick = now_ms
            self.auto_anim = self.pick_mood()
        if self.menu_active and now_ms > self.menu_until:
            self.menu_active = False
        if self.stats_screen and now_ms > self.stats_until:
            self.stats_screen = False
        if self.subtitle and now_ms - self.subtitle_start > max(self.subtitle_dur, len(self.subtitle) * 80) + 1500:
            self.subtitle = ""
        new_anim = self.override if self.override is not None else self.auto_anim
        if new_anim != self.anim:
            self.anim = new_anim
            self.t = 0

    def decay(self):
        if self.sleeping:
            self.hunger = clamp(self.hunger - 1)  # a energia volta aos poucos em update()
        else:
            self.hunger = clamp(self.hunger - 2)
            self.energy = clamp(self.energy - 1)
            self.clean = clamp(self.clean - 1)
            self.happy = clamp(self.happy - (3 if (self.hunger < 20 or self.clean < 20) else 1))

    def pick_mood(self):
        if self.sleeping:
            return AI["sleeping"]
        if self.hunger < 20:
            return AI["hungry"]
        if self.energy < 20:
            return AI["sleepy"]
        if self.clean < 20:
            return AI["dirty"]
        if self.happy < 20:
            return AI["sad"]
        if min(self.hunger, self.happy, self.energy, self.clean) < 45:
            return AI[random.choice(IDLE_POOL_MEH)]
        return AI[random.choice(IDLE_POOL_GOOD)]

    # ------------------------------------------------------------- comandos
    def play(self, anim_id, ms):
        self.override = anim_id
        self.override_until = self.now + ms
        if anim_id != self.anim:
            self.anim = anim_id
            self.t = 0

    def say(self, text, duration_ms=0):
        self.subtitle = text
        self.subtitle_start = self.now
        self.subtitle_dur = duration_ms

    def action(self, name):
        """Executa uma acao do menu. Retorna True se fez algo."""
        self.events.append(name)
        if name == "feed":
            if self.sleeping:
                self.play(AI["annoyed"], 2000)
            elif self.hunger >= 90:
                self.happy = clamp(self.happy - 3)
                self.play(AI["full"], 2500)
            else:
                self.hunger = clamp(self.hunger + 30)
                self.happy = clamp(self.happy + 3)
                self.play(AI["eating"], 3000)
        elif name == "play":
            if self.sleeping:
                self.play(AI["annoyed"], 2000)
            elif self.energy < 15:
                self.play(AI["sleepy"], 3000)
            else:
                self.happy = clamp(self.happy + 20)
                self.energy = clamp(self.energy - 10)
                self.hunger = clamp(self.hunger - 5)
                self.play(AI["playing"], 3500)
        elif name == "clean":
            if self.sleeping:
                self.play(AI["annoyed"], 2000)
            else:
                self.clean = 100
                self.happy = clamp(self.happy + 5)
                self.play(AI["bathing"], 3500)
        elif name == "sleep":
            if self.sleeping:
                self.sleeping = False
                self.play(AI["yawn"], 2500)
            else:
                self.sleeping = True
                self.play(AI["yawn"], 2000)
        elif name == "wake":
            if self.sleeping:
                self.sleeping = False
                self.play(AI["yawn"], 2500)
        elif name == "stats":
            self.stats_screen = True
            self.stats_until = self.now + 5000
        elif name == "pet":
            if not self.sleeping:
                self.happy = clamp(self.happy + 2)
                self.play(AI["love"], 2000)
        return True

    # ------------------------------------------------------------- botoes
    def button_a(self):
        if not self.menu_active:
            self.menu_active = True
        else:
            self.menu_sel = (self.menu_sel + 1) % len(A.MENU_ITEMS)
        self.menu_until = self.now + 6000
        self.stats_screen = False

    def button_b(self, apply=True):
        """Retorna o nome da acao escolhida (ou None)."""
        if not self.menu_active:
            self.menu_active = True
            self.menu_until = self.now + 6000
            return None
        item = A.MENU_ITEMS[self.menu_sel][0]
        self.menu_active = False
        if item != "talk" and apply:
            self.action(item)
        return item

    def button_c(self, apply=True):
        if self.menu_active or self.stats_screen:
            self.menu_active = False
            self.stats_screen = False
            return "back"
        if apply:
            self.action("pet")
        return "pet"

    def menu_label(self):
        labels = {
            "pt": ["Comer", "Brincar", "Banho", "Dormir", "Status", "Falar"],
            "en": ["Feed", "Play", "Bath", "Sleep", "Status", "Talk"],
            "es": ["Comer", "Jugar", "Bano", "Dormir", "Estado", "Hablar"],
        }.get(self.lang, None) or [m[2] for m in A.MENU_ITEMS]
        return labels[self.menu_sel]

    # -------------------------------------------------------- persistencia
    def to_dict(self):
        return {k: getattr(self, k) for k in ("hunger", "happy", "energy", "clean", "sleeping", "age_min")}

    def save(self, path):
        try:
            d = self.to_dict()
            d["saved_at"] = time.time()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f)
        except OSError:
            pass

    def load(self, path):
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            for k in ("hunger", "happy", "energy", "clean", "age_min"):
                setattr(self, k, int(d.get(k, getattr(self, k))))
            self.sleeping = bool(d.get("sleeping", False))
            # o tempo passa enquanto o programa esta fechado (com limite)
            away = max(0, time.time() - d.get("saved_at", time.time()))
            ticks = int(min(away, 12 * 3600) // self.decay_seconds)
            for _ in range(min(ticks, 300)):
                self.decay()
            self.age_min += int(away // 60)
        except (OSError, ValueError):
            pass
