"""As 50 animacoes do pet.

Cada animacao combina: sequencia de olhos, sequencia de bocas, um movimento
do corpo, um efeito (particulas/icones) e a velocidade dos quadros.
A ordem da lista ANIMATIONS define o numero (id) usado no protocolo serial,
entao nao reordene sem regravar o firmware (o Studio faz isso sozinho).
"""

# ---------------------------------------------------------------------------
# Estilos de olho: nome -> (sprite_esq, sprite_dir, dx, dy)
# sprite_dir = None significa sprite unico para os dois olhos (oculos)
# ---------------------------------------------------------------------------
EYE_STYLES = {
    "open": ("eye_open", "eye_open", 0, 0),
    "closed": ("eye_closed", "eye_closed", 0, 0),
    "happy": ("eye_happy", "eye_happy", 0, 0),
    "sad": ("eye_sad", "eye_sad~", 0, 0),
    "angry": ("eye_angry", "eye_angry~", 0, 0),
    "wide": ("eye_wide", "eye_wide", 0, 0),
    "heart": ("eye_heart", "eye_heart", 0, 0),
    "star": ("eye_star", "eye_star", 0, 0),
    "spiral": ("eye_spiral", "eye_spiral~", 0, 0),
    "x": ("eye_x", "eye_x", 0, 0),
    "sleepy": ("eye_sleepy", "eye_sleepy", 0, 0),
    "half": ("eye_half", "eye_half", 0, 0),
    "cry": ("eye_cry", "eye_cry~", 0, 0),
    "shine": ("eye_shine", "eye_shine", 0, 0),
    "dot": ("eye_dot", "eye_dot", 0, 0),
    "glasses": ("eye_glasses", None, 0, 0),
    "wink": ("eye_open", "eye_happy", 0, 0),
    "look_left": ("eye_open", "eye_open", -1, 0),
    "look_right": ("eye_open", "eye_open", 1, 0),
    "look_up": ("eye_open", "eye_open", 0, -1),
    "look_down": ("eye_open", "eye_open", 0, 1),
    "confused": ("eye_wide", "eye_dot", 0, 0),
    "confused2": ("eye_dot", "eye_wide", 0, 0),
}
BLINKABLE = {"open", "look_left", "look_right", "look_up", "look_down", "wide", "shine"}

MOUTHS = [
    "m_smile", "m_bigsmile", "m_neutral", "m_frown", "m_o", "m_O", "m_yawn",
    "m_tongue", "m_grit", "m_wavy", "m_cat", "m_smirk",
]
TALK_SEQ = ["m_o", "m_O", "m_neutral", "m_O"]  # boca falando (quando ha audio)

# ---------------------------------------------------------------------------
# Movimentos: lista de deslocamentos (dx, dy) por quadro
# ---------------------------------------------------------------------------
MOTIONS = {
    "none": [(0, 0)],
    "breathe": [(0, 0), (0, 0), (0, 1), (0, 1)],
    "bounce": [(0, 0), (0, -1), (0, -2), (0, -1)],
    "hop": [(0, 0), (0, -2)],
    "jump": [(0, 0), (0, -3), (0, -6), (0, -3)],
    "shake": [(-2, 0), (2, 0)],
    "shiver": [(-1, 0), (1, 0)],
    "sway": [(0, 0), (1, 0), (2, 0), (1, 0), (0, 0), (-1, 0), (-2, 0), (-1, 0)],
    "float": [(0, 0), (0, -1), (0, -2), (0, -2), (0, -1), (0, 0), (0, 1), (0, 1)],
    "droop": [(0, 2)],
    "nod": [(0, 0), (0, 1), (0, 2), (0, 1)],
    "dance": [(-2, 0), (-2, -2), (0, 0), (2, 0), (2, -2), (0, 0)],
    "lean": [(2, 0)],
    "puff": [(0, -1)],
    "wobble": [(-1, -1), (1, -1), (1, 1), (-1, 1)],
}

# ---------------------------------------------------------------------------
# Efeitos: lista de componentes (icone, padrao, x, y, a, b, c)
# Posicoes relativas ao canto superior esquerdo do corpo.
# Padroes:
#   static (a,b,c ignorados)
#   blink  visivel quando ((t+a)>>1)&1 == 0
#   rise   sobe: y - ((t*c + b) % a)
#   fall   desce: y + ((t*c + b) % a)
#   orbit  gira: centro (x,y), raios a,b, fase c
#   sides  alterna entre (x,y) e (x+a, y+b) a cada 2 quadros, fase c
#   bounce quica: y - BOUNCE[(t+b)&7]*a/8
# ---------------------------------------------------------------------------
PATTERNS = ["static", "blink", "rise", "fall", "orbit", "sides", "bounce"]
ORBIT_X = [0, 6, 8, 6, 0, -6, -8, -6]
ORBIT_Y = [-8, -6, 0, 6, 8, 6, 0, -6]
BOUNCE_T = [0, 4, 7, 8, 8, 7, 4, 0]

EFFECTS = {
    "none": [],
    "sparkles": [("i_spark", "blink", -10, 6, 0, 0, 0), ("i_spark", "blink", 38, 2, 2, 0, 0),
                 ("i_spark", "blink", 30, -10, 1, 0, 0)],
    "hearts": [("i_heart", "rise", -13, 12, 22, 0, 2), ("i_heart", "rise", 38, 8, 22, 11, 2)],
    "zzz": [("i_z", "rise", 31, 0, 12, 0, 1), ("i_zs", "rise", 37, -4, 12, 6, 1)],
    "sweat": [("i_drop", "fall", 30, 2, 8, 0, 1)],
    "notes": [("i_note", "rise", -15, 12, 18, 0, 1), ("i_note", "rise", 39, 8, 18, 9, 1)],
    "stars": [("i_spark", "orbit", 13, -6, 18, 5, 0), ("i_spark", "orbit", 13, -6, 18, 5, 3),
              ("i_spark", "orbit", 13, -6, 18, 5, 6)],
    "anger": [("i_anger", "blink", 27, 1, 0, 0, 0)],
    "fire": [("i_fire", "sides", -13, 16, 0, -1, 0), ("i_fire", "sides", 38, 16, 0, -1, 2)],
    "exclaim": [("i_excl", "sides", 36, -6, 0, -1, 0)],
    "question": [("i_quest", "sides", 35, -8, 1, -1, 0)],
    "dots": [("i_dot", "blink", 8, -9, 0, 0, 0), ("i_dot", "blink", 15, -9, 3, 0, 0),
             ("i_dot", "blink", 22, -9, 2, 0, 0)],
    "bored": [("i_dot", "blink", 34, 2, 0, 0, 0), ("i_dot", "blink", 38, 2, 3, 0, 0),
              ("i_dot", "blink", 42, 2, 2, 0, 0)],
    "lightbulb": [("i_bulb", "static", 13, -14, 0, 0, 0), ("i_spark", "blink", 4, -11, 0, 0, 0),
                  ("i_spark", "blink", 23, -11, 2, 0, 0)],
    "tears": [("i_tear", "fall", 9, 16, 12, 0, 2), ("i_tear", "fall", 21, 16, 12, 6, 2)],
    "food": [("i_apple", "bounce", 37, 18, 3, 0, 0)],
    "hungry": [("i_dot1", "static", 31, 2, 0, 0, 0), ("i_dot", "static", 34, -2, 0, 0, 0),
               ("i_apple", "blink", 37, -11, 0, 0, 0)],
    "ball": [("i_ball", "bounce", 38, 16, 20, 0, 0)],
    "bubbles": [("i_bubble", "rise", -11, 16, 22, 0, 1), ("i_bubble_s", "rise", 37, 12, 22, 8, 1),
                ("i_bubble_s", "rise", -4, 6, 22, 15, 1), ("i_bubble", "rise", 40, 18, 22, 4, 1)],
    "rain": [("i_cloud", "static", 10, -13, 0, 0, 0), ("i_rain", "fall", 12, -7, 6, 0, 1),
             ("i_rain", "fall", 16, -7, 6, 3, 1), ("i_rain", "fall", 19, -7, 6, 1, 1)],
    "sick": [("i_thermo", "sides", 35, 4, 0, -1, 0), ("i_drop", "fall", -5, 4, 8, 0, 1)],
    "snow": [("i_snow", "fall", -15, -10, 26, 0, 1), ("i_snow", "fall", 39, -10, 26, 13, 1)],
    "hot": [("i_sun", "blink", 37, -12, 0, 0, 0), ("i_drop", "fall", -5, 4, 8, 0, 1),
            ("i_drop", "fall", 31, 6, 8, 4, 1)],
    "blush": [("i_blush", "static", 3, 17, 0, 0, 0), ("i_blush", "static", 24, 17, 0, 0, 0)],
    "flowers": [("i_flower", "sides", -12, 20, 0, -1, 0), ("i_flower", "sides", 39, 20, 0, -1, 2)],
    "stink": [("i_stink", "sides", -8, 0, 1, 0, 0), ("i_stink", "sides", 37, -2, -1, 0, 2),
              ("i_dot1", "orbit", 15, -6, 16, 4, 0)],
    "confetti": [("i_dot1", "fall", -14, -12, 30, 0, 2), ("i_dot", "fall", -2, -13, 30, 10, 2),
                 ("i_dot1", "fall", 40, -12, 30, 20, 2), ("i_spark", "fall", 30, -14, 30, 5, 2),
                 ("i_dot", "fall", 45, -13, 30, 15, 2), ("i_spark", "fall", -9, -14, 30, 25, 2)],
    "wave": [("i_hand", "sides", 37, 8, 2, -2, 0)],
    "lightning": [("i_bolt", "blink", -12, 6, 0, 0, 0), ("i_bolt", "blink", 39, 6, 2, 0, 0)],
    "listen": [("i_waves", "blink", 37, 12, 0, 0, 0), ("i_waves~", "blink", -10, 12, 0, 0, 0)],
    "love_small": [("i_heart", "static", 37, 0, 0, 0, 0), ("i_spark", "blink", -9, 4, 0, 0, 0)],
}

# ---------------------------------------------------------------------------
# As 50 animacoes: (nome, rotulo PT, olhos, bocas, movimento, efeito, ms, dica p/ Claude)
# ---------------------------------------------------------------------------
ANIMATIONS = [
    ("idle", "Parado", ["open"], ["m_smile"], "breathe", "none", 300, "neutral, calm default"),
    ("happy", "Feliz", ["happy"], ["m_bigsmile"], "bounce", "sparkles", 200, "happy, pleased"),
    ("ecstatic", "Eufórico", ["star"], ["m_bigsmile"], "jump", "sparkles", 150, "extremely happy, amazed by something great"),
    ("laugh", "Rindo", ["cry"], ["m_bigsmile", "m_O"], "shiver", "none", 120, "laughing at a joke"),
    ("love", "Apaixonado", ["heart"], ["m_smile"], "float", "hearts", 200, "love, affection, compliments"),
    ("shy", "Tímido", ["look_down"], ["m_o"], "sway", "blush", 300, "shy, flattered"),
    ("sad", "Triste", ["sad"], ["m_frown"], "droop", "rain", 400, "sad, disappointed"),
    ("crying", "Chorando", ["sad"], ["m_wavy"], "shiver", "tears", 150, "very sad, crying"),
    ("angry", "Bravo", ["angry"], ["m_grit"], "shake", "anger", 120, "angry, irritated"),
    ("furious", "Furioso", ["angry"], ["m_O"], "shake", "fire", 90, "furious, outraged"),
    ("surprised", "Surpreso", ["wide"], ["m_O"], "hop", "exclaim", 200, "surprised, wow"),
    ("scared", "Assustado", ["wide"], ["m_wavy"], "shiver", "sweat", 100, "scared, afraid"),
    ("confused", "Confuso", ["confused", "confused2"], ["m_wavy"], "sway", "question", 400, "confused, did not understand"),
    ("thinking", "Pensando", ["look_up"], ["m_neutral"], "float", "dots", 250, "thinking, pondering"),
    ("idea", "Ideia!", ["wide"], ["m_bigsmile"], "hop", "lightbulb", 200, "had an idea, eureka"),
    ("sleepy", "Com sono", ["sleepy"], ["m_o"], "nod", "none", 400, "sleepy, tired"),
    ("sleeping", "Dormindo", ["closed"], ["m_o"], "breathe", "zzz", 350, "asleep"),
    ("yawn", "Bocejando", ["closed"], ["m_yawn"], "puff", "none", 400, "yawning"),
    ("eating", "Comendo", ["happy"], ["m_O", "m_neutral", "m_o", "m_neutral"], "hop", "food", 180, "eating food"),
    ("hungry", "Com fome", ["sad"], ["m_o"], "droop", "hungry", 400, "hungry, wants food"),
    ("full", "Satisfeito", ["happy"], ["m_cat"], "sway", "none", 300, "full, satisfied after eating"),
    ("sick", "Doente", ["sleepy", "half"], ["m_wavy"], "shiver", "sick", 300, "sick, unwell"),
    ("dizzy", "Tonto", ["spiral"], ["m_wavy"], "wobble", "stars", 150, "dizzy, overwhelmed"),
    ("dancing", "Dançando", ["happy"], ["m_bigsmile"], "dance", "notes", 200, "dancing, party"),
    ("singing", "Cantando", ["closed"], ["m_O", "m_o"], "sway", "notes", 250, "singing, music"),
    ("playing", "Brincando", ["open"], ["m_bigsmile"], "jump", "ball", 150, "playing a game"),
    ("excited", "Animado", ["shine"], ["m_bigsmile"], "bounce", "sparkles", 120, "excited, can't wait"),
    ("proud", "Orgulhoso", ["closed"], ["m_smile"], "puff", "sparkles", 300, "proud of itself or the user"),
    ("cool", "Estiloso", ["glasses"], ["m_smirk"], "nod", "none", 300, "cool, confident"),
    ("wink", "Piscadinha", ["wink"], ["m_smile"], "hop", "sparkles", 300, "playful wink, joking"),
    ("bored", "Entediado", ["half"], ["m_neutral"], "sway", "bored", 500, "bored"),
    ("annoyed", "Irritado", ["half"], ["m_frown"], "none", "anger", 300, "mildly annoyed"),
    ("nervous", "Nervoso", ["look_left", "look_right"], ["m_wavy"], "shiver", "sweat", 200, "nervous, anxious"),
    ("embarrassed", "Envergonhado", ["closed"], ["m_wavy"], "shiver", "blush", 200, "embarrassed"),
    ("curious", "Curioso", ["look_right"], ["m_o"], "lean", "question", 300, "curious, asking a question"),
    ("listening", "Ouvindo", ["wide"], ["m_o"], "breathe", "listen", 250, "listening to the user"),
    ("talking", "Falando", ["open"], ["m_O", "m_neutral", "m_o", "m_smile"], "hop", "none", 140, "normal talking, explaining"),
    ("hello", "Olá", ["happy"], ["m_bigsmile"], "hop", "wave", 200, "greeting, hello"),
    ("goodbye", "Tchau", ["happy"], ["m_smile"], "sway", "wave", 250, "saying goodbye"),
    ("ko", "Nocaute", ["x"], ["m_wavy"], "droop", "stars", 500, "exhausted, knocked out"),
    ("cold", "Com frio", ["wide"], ["m_grit"], "shiver", "snow", 100, "cold, freezing"),
    ("hot", "Com calor", ["sleepy"], ["m_tongue"], "droop", "hot", 350, "hot weather, sweating"),
    ("bathing", "Tomando banho", ["closed"], ["m_smile"], "sway", "bubbles", 250, "bath, getting clean"),
    ("dirty", "Sujinho", ["sad"], ["m_frown"], "none", "stink", 300, "dirty, needs a bath"),
    ("celebrate", "Comemorando", ["star"], ["m_bigsmile"], "jump", "confetti", 150, "celebrating, congratulations"),
    ("grateful", "Agradecido", ["closed"], ["m_smile"], "nod", "love_small", 300, "thankful"),
    ("sorry", "Desculpa", ["sad"], ["m_o"], "nod", "sweat", 300, "apologizing"),
    ("mischief", "Arteiro", ["half"], ["m_smirk"], "sway", "none", 300, "mischievous, teasing, sarcastic"),
    ("determined", "Determinado", ["angry"], ["m_grit"], "bounce", "lightning", 200, "determined, motivated"),
    ("relaxed", "Relaxado", ["closed"], ["m_smile"], "float", "flowers", 400, "relaxed, peaceful, zen"),
]

ANIM_NAMES = [a[0] for a in ANIMATIONS]
ANIM_INDEX = {n: i for i, n in enumerate(ANIM_NAMES)}
assert len(ANIMATIONS) == 50, len(ANIMATIONS)

# Acoes do pet (menu do aparelho / comandos do Claude)
ACTIONS = ["none", "feed", "play", "clean", "sleep", "wake", "stats", "talk"]
MENU_ITEMS = [("feed", "i_apple", "Comer"), ("play", "i_ball", "Brincar"), ("clean", "i_soap", "Banho"),
              ("sleep", "i_moon", "Dormir"), ("stats", "i_stats", "Status"), ("talk", "i_mic", "Falar")]
STATUS_ICONS = ["i_apple", "i_heart", "i_bolt", "i_drop"]


def anim(name_or_id):
    if isinstance(name_or_id, int):
        return ANIMATIONS[name_or_id]
    return ANIMATIONS[ANIM_INDEX[name_or_id]]


def _validate():
    from . import sprites
    names = set(sprites.all_sprites())
    def chk(n):
        base = n[:-1] if n.endswith("~") else n
        assert base in names, f"sprite inexistente: {n}"
    for l, r, _, _ in EYE_STYLES.values():
        chk(l)
        if r:
            chk(r)
    for m in MOUTHS + TALK_SEQ:
        chk(m)
    for comps in EFFECTS.values():
        for c in comps:
            chk(c[0])
            assert c[1] in PATTERNS
    for a in ANIMATIONS:
        for e in a[2]:
            assert e in EYE_STYLES, e
        for m in a[3]:
            assert m in MOUTHS, m
        assert a[4] in MOTIONS, a[4]
        assert a[5] in EFFECTS, a[5]


_validate()
