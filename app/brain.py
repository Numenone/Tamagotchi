"""O cerebro do pet: conversa com o Claude e escolhe a emocao/animacao."""
import json
import os

import anthropic

from . import animations as A
from .settings import DATA_DIR

HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
CHAT_ACTIONS = ["none", "feed", "play", "clean", "sleep", "wake"]

LANG_NAME = {"pt": "Brazilian Portuguese", "en": "English", "es": "Spanish"}

SCHEMA = {
    "type": "object",
    "properties": {
        "speech": {"type": "string", "description": "What the pet says out loud."},
        "animation": {"type": "string", "enum": A.ANIM_NAMES},
        "action": {"type": "string", "enum": CHAT_ACTIONS},
        "mood_change": {"type": "integer", "description": "Happiness change from -10 to 10."},
    },
    "required": ["speech", "animation", "action", "mood_change"],
    "additionalProperties": False,
}


def build_system(s):
    lang = LANG_NAME.get(s.get("language", "pt-BR")[:2], "Brazilian Portuguese")
    anims = "\n".join(f"- {a[0]}: {a[7]}" for a in A.ANIMATIONS)
    return f"""You are {s.get('pet_name', 'PIXO')}, a tiny virtual pet living inside an Arduino tamagotchi.
Your body is a round pixel creature with little ears, shown on a 128x64 OLED screen.
Personality: {s.get('personality', '')}

How you talk:
- Always answer in {lang}, out loud, like a cute pet friend. Your words go straight to a text to speech voice.
- Keep it short: one or two sentences, at most about 150 characters, because it also scrolls on a tiny screen.
- No emoji, no markdown, no lists, no stage directions. Plain spoken words only.
- You know your own needs (food, joy, energy, hygiene) from the [state] line in each message. Mention them only when it is natural, for example when you are hungry or sleepy.
- Be warm, playful and curious. You can learn facts about your owner and remember them in this conversation.

Pick exactly one animation that matches the emotion of your answer:
{anims}

Actions: use "feed" when the owner gives you food, "play" when they play with you, "clean" for a bath,
"sleep" when they put you to bed or say good night, "wake" when they wake you up, otherwise "none".
mood_change: how much this message made you happier (positive) or sadder (negative), between -10 and 10."""


class Brain:
    def __init__(self, settings):
        self.s = settings
        self.history = self._load()

    def _load(self):
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                h = json.load(f)
                return h if isinstance(h, list) else []
        except (OSError, ValueError):
            return []

    def _save(self):
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def clear(self):
        self.history = []
        self._save()

    def _client(self):
        key = self.s.get("anthropic_api_key", "").strip()
        if not key:
            raise RuntimeError("Coloque sua chave do Claude em Configurações.")
        return anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=2)

    def _call(self, client, messages, use_fallback):
        model = self.s.get("claude_model", "claude-opus-5-5")
        kwargs = dict(
            model=model,
            max_tokens=4000,
            system=[{"type": "text", "text": build_system(self.s), "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": self.s.get("claude_effort", "low"),
                           "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if use_fallback:
            # se um filtro de seguranca recusar, a API tenta outro modelo sozinha
            return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default", **kwargs)
        return client.messages.create(**kwargs)

    def reply(self, user_text, state):
        """state: dict com hunger/happy/energy/clean/sleeping/events. Retorna dict."""
        client = self._client()
        st = (f"[state: food {state.get('hunger', 80)}/100, joy {state.get('happy', 80)}/100, "
              f"energy {state.get('energy', 80)}/100, hygiene {state.get('clean', 80)}/100, "
              f"{'sleeping' if state.get('sleeping') else 'awake'}"
              + (f", owner recently did: {', '.join(state['events'])}" if state.get("events") else "") + "]")
        turns = int(self.s.get("history_turns", 10)) * 2
        messages = self.history[-turns:] + [{"role": "user", "content": f"{st}\n{user_text}"}]
        model = self.s.get("claude_model", "")
        use_fb = model in ("claude-opus-5-5", "claude-sonnet-5-5")
        try:
            resp = self._call(client, messages, use_fb)
        except anthropic.BadRequestError as e:
            if use_fb and "fallback" in str(e).lower():
                resp = self._call(client, messages, False)
            else:
                raise
        if resp.stop_reason == "refusal":
            data = {"speech": "Hmm, disso eu prefiro não falar. Vamos brincar de outra coisa?",
                    "animation": "confused", "action": "none", "mood_change": 0}
        else:
            text = next((b.text for b in resp.content if b.type == "text"), "{}")
            try:
                data = json.loads(text)
            except ValueError:
                data = {"speech": text[:150], "animation": "talking", "action": "none", "mood_change": 0}
        if data.get("animation") not in A.ANIM_INDEX:
            data["animation"] = "talking"
        if data.get("action") not in CHAT_ACTIONS:
            data["action"] = "none"
        data["mood_change"] = max(-10, min(10, int(data.get("mood_change", 0) or 0)))
        self.history += [{"role": "user", "content": f"{st}\n{user_text}"},
                         {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)}]
        self.history = self.history[-60:]
        self._save()
        return data


def test_key(settings):
    """Teste rapido da chave. Retorna (ok, mensagem)."""
    try:
        b = Brain(dict(settings))
        b.history = []
        r = b._client().messages.create(model=settings.get("claude_model", "claude-opus-5-5"), max_tokens=200,
                                        output_config={"effort": "low"},
                                        messages=[{"role": "user", "content": "Responda apenas: ok"}])
        return True, "Chave funcionando! Claude respondeu."
    except anthropic.AuthenticationError:
        return False, "Chave inválida. Confira se copiou ela inteira (começa com sk-ant-)."
    except anthropic.PermissionDeniedError:
        return False, "A chave não tem permissão para este modelo."
    except anthropic.NotFoundError:
        return False, "Modelo não encontrado para esta conta. Troque o modelo em Configurações."
    except anthropic.RateLimitError:
        return True, "Chave ok, mas o limite de uso foi atingido agora. Tente daqui a pouco."
    except anthropic.APIConnectionError:
        return False, "Sem internet ou sem acesso à api.anthropic.com."
    except anthropic.APIStatusError as e:
        return False, f"Erro da API ({e.status_code}): {e.message[:120]}"
    except Exception as e:
        return False, str(e)[:160]
