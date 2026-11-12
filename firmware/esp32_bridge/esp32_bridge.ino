// =====================================================================
//  Tamagotchi + Claude  |  Ponte sem fio no ESP32
//
//  O ESP32 fica ligado na serial do Arduino Uno (pinos 0 e 1) e faz o
//  papel que o PC fazia: ouve (Google Speech-to-Text), pensa (Claude) e
//  fala (Google Text-to-Speech). O firmware do Uno continua o mesmo.
//
//  bridge_config.h, prompt.h e secrets.h sao gerados pelo Tamagotchi
//  Studio (Configuracoes > Sem fio (ESP32) > Gravar o ESP32).
//
//  Ligacoes:  ESP32 GPIO17 (TX2) -> Uno pino 0 (RX)
//             Uno pino 1 (TX) -> divisor 1k/2k -> ESP32 GPIO16 (RX2)
//             GND com GND, e o ESP32 alimentado pelo 5V do Uno (VIN).
// =====================================================================
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <esp_heap_caps.h>
#include <atomic>
#include <deque>
#include <functional>
#include <string>
#include <utility>

#include "secrets.h"
#include "bridge_config.h"
#include "prompt.h"

#define UNO Serial2
#define UNO_RX_PIN 16
#define UNO_TX_PIN 17
#define MAX_REC_BYTES 122000UL   // 15 s de u-law 8 kHz + folga
#define MAX_MP3_BYTES 170000UL   // ~40 s de MP3 a 32 kbps
#define HEAP_RESERVE 62000UL     // o que precisa sobrar para o TLS
#define MP3_BYTES_PER_SEC 4000.0f

// ------------------------------------------------------------- estado
static SemaphoreHandle_t txLock;
static std::atomic<int> credits{0};
static std::atomic<bool> abortAudio{false}, playing{false}, busy{false};
static uint8_t window_ = 1;
static volatile uint8_t stHunger = 80, stHappy = 80, stEnergy = 80, stClean = 80, stSleeping = 0;
static uint8_t evIds[3];
static uint8_t evCount = 0;
static uint8_t* recBuf = nullptr;
static size_t recLen = 0, recCap = 0;
static bool recording = false;
static uint32_t lastPing = 0, lastUnoFrame = 0;
static bool unoSeen = false, wifiWasUp = false;
static std::deque<std::pair<std::string, std::string>> history;

// respostas HTTP e do Claude (antes das funcoes por causa dos prototipos do Arduino)
struct Resp {
  int status = -1;
  bool chunked = false;
  long contentLength = -1;
};

struct Reply {
  String speech;
  uint8_t anim = ANIM_TALKING;
  String action = "none";
  int mood = 0;
};

// entregue para a tarefa de conversa
static uint8_t* convAudio = nullptr;
static size_t convLen = 0;

// ------------------------------------------------------------- protocolo com o Uno
// quadro: 0x7E tipo tamanho dados... checksum (soma de tipo+tamanho+dados)
static void sendFrame(uint8_t type, const uint8_t* d, uint8_t n) {
  uint8_t buf[260];
  uint8_t sum = type + n;
  buf[0] = 0x7E;
  buf[1] = type;
  buf[2] = n;
  for (uint8_t i = 0; i < n; i++) {
    buf[3 + i] = d[i];
    sum += d[i];
  }
  buf[3 + n] = sum;
  xSemaphoreTake(txLock, portMAX_DELAY);
  UNO.write(buf, n + 4);
  xSemaphoreGive(txLock);
}

static void sendAnim(uint8_t id, uint8_t seconds) {
  uint8_t d[2] = {id, seconds};
  sendFrame('A', d, 2);
}

// Tira acentos (a tela do Uno so tem ASCII)
static String asciiFold(const char* s, size_t maxLen) {
  static const char LATIN[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYTsaaaaaaaceeeeiiiidnooooo/ouuuuyty";
  String out;
  const uint8_t* p = (const uint8_t*)s;
  while (*p && out.length() < maxLen) {
    uint32_t cp;
    if (*p < 0x80) { cp = *p++; }
    else if ((*p & 0xE0) == 0xC0 && p[1]) { cp = ((p[0] & 0x1F) << 6) | (p[1] & 0x3F); p += 2; }
    else if ((*p & 0xF0) == 0xE0 && p[1] && p[2]) { cp = ((p[0] & 0x0F) << 12) | ((p[1] & 0x3F) << 6) | (p[2] & 0x3F); p += 3; }
    else if ((*p & 0xF8) == 0xF0 && p[1] && p[2] && p[3]) { cp = 0xFFFF; p += 4; }
    else { p++; continue; }
    if (cp >= 32 && cp < 127) out += (char)cp;
    else if (cp >= 0xC0 && cp <= 0xFF) out += LATIN[cp - 0xC0];
    else if (cp == 0x2018 || cp == 0x2019) out += '\'';
    else if (cp == 0x201C || cp == 0x201D) out += '"';
    else if (cp == 0x2013 || cp == 0x2014) out += '-';
    else if (cp == 0x2026) out += "...";
  }
  return out;
}

static void sendText(const char* utf8, uint32_t durationMs) {
  String t = asciiFold(utf8, 118);
  uint8_t d[121];
  uint16_t ds = durationMs / 100 > 65535 ? 65535 : durationMs / 100;
  d[0] = ds & 0xFF;
  d[1] = ds >> 8;
  memcpy(d + 2, t.c_str(), t.length());
  sendFrame('T', d, 2 + t.length());
}

static void showProblem(const char* msg) {
  sendAnim(ANIM_CONFUSED, 3);
  sendText(msg, 2500);
}

// ------------------------------------------------------------- memoria
static uint8_t* bigAlloc(size_t want, size_t* got) {
  if (psramFound()) {
    uint8_t* p = (uint8_t*)ps_malloc(want);
    if (p) { *got = want; return p; }
  }
  size_t largest = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  size_t freeH = heap_caps_get_free_size(MALLOC_CAP_8BIT);
  if (largest < 9000) return nullptr;
  size_t cap = want;
  if (cap > largest - 1024) cap = largest - 1024;
  if (freeH < HEAP_RESERVE + 8000) return nullptr;
  if (cap > freeH - HEAP_RESERVE) cap = freeH - HEAP_RESERVE;
  if (cap < 8000) return nullptr;
  uint8_t* p = (uint8_t*)malloc(cap);
  *got = p ? cap : 0;
  return p;
}

// ------------------------------------------------------------- HTTPS
static bool postStart(WiFiClientSecure& c, const char* host, const char* path, size_t len, const String& extraHeaders) {
  c.setInsecure();  // sem verificar certificado (simples para prototipo)
  if (!c.connect(host, 443)) {
    Serial.printf("[http] falha ao conectar em %s\n", host);
    return false;
  }
  String h = String("POST ") + path + " HTTP/1.1\r\nHost: " + host +
             "\r\nContent-Type: application/json\r\nContent-Length: " + String((unsigned long)len) +
             "\r\nConnection: close\r\n" + extraHeaders + "\r\n";
  c.print(h);
  return true;
}

static int readByteT(WiFiClientSecure& c, uint32_t idleMs) {
  uint32_t t0 = millis();
  while (!c.available()) {
    if (!c.connected()) return -1;
    if (millis() - t0 > idleMs) return -1;
    delay(2);
  }
  return c.read();
}

static bool readLine(WiFiClientSecure& c, String& line, uint32_t idleMs) {
  line = "";
  for (;;) {
    int ch = readByteT(c, idleMs);
    if (ch < 0) return line.length() > 0;
    if (ch == '\n') return true;
    if (ch != '\r' && line.length() < 1024) line += (char)ch;
  }
}

static bool readHead(WiFiClientSecure& c, Resp& r, uint32_t firstByteMs) {
  String line;
  if (!readLine(c, line, firstByteMs)) return false;
  int sp = line.indexOf(' ');
  if (sp < 0) return false;
  r.status = line.substring(sp + 1).toInt();
  while (readLine(c, line, 15000)) {
    if (line.length() == 0) return true;
    String low = line;
    low.toLowerCase();
    if (low.startsWith("transfer-encoding:") && low.indexOf("chunked") > 0) r.chunked = true;
    if (low.startsWith("content-length:")) r.contentLength = low.substring(15).toInt();
  }
  return false;
}

static int readBlock(WiFiClientSecure& c, uint8_t* buf, size_t want, uint32_t idleMs) {
  uint32_t t0 = millis();
  for (;;) {
    int a = c.available();
    if (a > 0) return c.read(buf, (size_t)a < want ? (size_t)a : want);
    if (!c.connected()) return -1;
    if (millis() - t0 > idleMs) return -1;
    delay(2);
  }
}

// Le o corpo (com ou sem "chunked") e entrega os bytes para cb.
static void readBody(WiFiClientSecure& c, const Resp& r, const std::function<void(const uint8_t*, size_t)>& cb) {
  uint8_t buf[512];
  if (!r.chunked) {
    long left = r.contentLength;
    while (left != 0) {
      size_t want = (left < 0 || left > (long)sizeof(buf)) ? sizeof(buf) : (size_t)left;
      int n = readBlock(c, buf, want, 20000);
      if (n <= 0) break;
      cb(buf, n);
      if (left > 0) left -= n;
    }
    return;
  }
  String line;
  for (;;) {
    if (!readLine(c, line, 20000)) return;
    long size = strtol(line.c_str(), nullptr, 16);
    if (size <= 0) return;
    while (size > 0) {
      int n = readBlock(c, buf, size > (long)sizeof(buf) ? sizeof(buf) : (size_t)size, 20000);
      if (n <= 0) return;
      cb(buf, n);
      size -= n;
    }
    readLine(c, line, 20000);  // CRLF depois de cada pedaco
  }
}

static std::string readBodyString(WiFiClientSecure& c, const Resp& r, size_t maxLen) {
  std::string s;
  readBody(c, r, [&](const uint8_t* d, size_t n) {
    if (s.size() < maxLen) s.append((const char*)d, n);
  });
  return s;
}

// ------------------------------------------------------------- base64
static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static void writeBase64(WiFiClientSecure& c, const uint8_t* data, size_t len) {
  char out[1024];
  size_t o = 0;
  for (size_t i = 0; i < len; i += 3) {
    uint32_t v = (uint32_t)data[i] << 16;
    if (i + 1 < len) v |= (uint32_t)data[i + 1] << 8;
    if (i + 2 < len) v |= data[i + 2];
    out[o++] = B64[(v >> 18) & 63];
    out[o++] = B64[(v >> 12) & 63];
    out[o++] = i + 1 < len ? B64[(v >> 6) & 63] : '=';
    out[o++] = i + 2 < len ? B64[v & 63] : '=';
    if (o >= sizeof(out) - 4) {
      c.write((const uint8_t*)out, o);
      o = 0;
    }
  }
  if (o) c.write((const uint8_t*)out, o);
}

// Acha "audioContent" na resposta do Google e decodifica o base64 em out.
struct AudioSink {
  uint8_t* out;
  size_t cap, len = 0;
  uint8_t state = 0, match = 0;
  uint32_t acc = 0;
  uint8_t nbits = 0;
  bool overflow = false;
  int8_t dec[256];
  AudioSink(uint8_t* o, size_t c) : out(o), cap(c) {
    memset(dec, -1, sizeof(dec));
    for (int i = 0; i < 64; i++) dec[(uint8_t)B64[i]] = i;
  }
  void feed(const uint8_t* d, size_t n) {
    static const char KEY[] = "\"audioContent\"";
    for (size_t i = 0; i < n; i++) {
      char ch = d[i];
      if (state == 0) {
        match = (ch == KEY[match]) ? match + 1 : (ch == KEY[0] ? 1 : 0);
        if (KEY[match] == 0) state = 1;
      } else if (state == 1) {
        if (ch == '"') state = 2;
      } else if (state == 2) {
        if (ch == '"') { state = 3; continue; }
        int8_t v = dec[(uint8_t)ch];
        if (v < 0) continue;  // '=', '\\', espacos
        acc = (acc << 6) | v;
        nbits += 6;
        if (nbits >= 8) {
          nbits -= 8;
          if (len < cap) out[len++] = (acc >> nbits) & 0xFF;
          else overflow = true;
        }
      }
    }
  }
};

// ------------------------------------------------------------- ouvido (Google Speech-to-Text)
static String transcribe(const uint8_t* data, size_t len) {
  WiFiClientSecure c;
  String pre = String("{\"config\":{\"encoding\":\"MULAW\",\"sampleRateHertz\":8000,\"languageCode\":\"") + LANG_CODE +
               "\",\"enableAutomaticPunctuation\":true},\"audio\":{\"content\":\"";
  const char* post = "\"}}";
  size_t total = pre.length() + 4 * ((len + 2) / 3) + strlen(post);
  if (!postStart(c, "speech.googleapis.com", "/v1/speech:recognize", total,
                 String("X-goog-api-key: ") + GOOGLE_API_KEY + "\r\n"))
    return "";
  c.print(pre);
  writeBase64(c, data, len);
  c.print(post);
  Resp r;
  if (!readHead(c, r, 30000)) {
    Serial.println("[stt] sem resposta");
    return "";
  }
  std::string body = readBodyString(c, r, 16000);
  c.stop();
  if (r.status != 200) {
    Serial.printf("[stt] HTTP %d: %.200s\n", r.status, body.c_str());
    return "";
  }
  JsonDocument filter;
  filter["results"][0]["alternatives"][0]["transcript"] = true;
  JsonDocument doc;
  if (deserializeJson(doc, body, DeserializationOption::Filter(filter))) return "";
  String out;
  for (JsonVariant res : doc["results"].as<JsonArray>()) {
    const char* t = res["alternatives"][0]["transcript"];
    if (t && *t) {
      if (out.length()) out += " ";
      out += t;
    }
  }
  out.trim();
  return out;
}

// ------------------------------------------------------------- cerebro (Claude)
static uint8_t animIndex(const char* name) {
  if (name)
    for (uint8_t i = 0; i < ANIM_COUNT; i++)
      if (strcmp(ANIM_NAMES[i], name) == 0) return i;
  return ANIM_TALKING;
}

static int actIndex(const char* name) {
  for (int i = 0; i < ACT_COUNT; i++)
    if (strcmp(ACT_NAMES[i], name) == 0) return i;
  return -1;
}

static std::string stateLine() {
  char buf[200];
  snprintf(buf, sizeof(buf), "[state: food %u/100, joy %u/100, energy %u/100, hygiene %u/100, %s",
           stHunger, stHappy, stEnergy, stClean, stSleeping ? "sleeping" : "awake");
  std::string s = buf;
  if (evCount) {
    s += ", owner recently did: ";
    for (uint8_t i = 0; i < evCount; i++) {
      if (i) s += ", ";
      s += evIds[i] < ACT_COUNT ? ACT_NAMES[evIds[i]] : "?";
    }
    evCount = 0;
  }
  s += "]";
  return s;
}

// Retorna 0 se deu certo, ou o codigo HTTP do erro (-1 = sem conexao)
static int callClaude(const std::string& userMsg, bool useFallback, std::string& textOut, bool& refused) {
  JsonDocument req;
  req["model"] = CLAUDE_MODEL;
  req["max_tokens"] = 4000;
  JsonObject sys = req["system"].add<JsonObject>();
  sys["type"] = "text";
  sys["text"] = SYSTEM_PROMPT;
  sys["cache_control"]["type"] = "ephemeral";
  JsonArray msgs = req["messages"].to<JsonArray>();
  for (auto& turn : history) {
    JsonObject u = msgs.add<JsonObject>();
    u["role"] = "user";
    u["content"] = turn.first;
    JsonObject a = msgs.add<JsonObject>();
    a["role"] = "assistant";
    a["content"] = turn.second;
  }
  JsonObject m = msgs.add<JsonObject>();
  m["role"] = "user";
  m["content"] = userMsg;
  req["output_config"]["effort"] = CLAUDE_EFFORT;
  req["output_config"]["format"]["type"] = "json_schema";
  req["output_config"]["format"]["schema"] = serialized(SCHEMA_JSON);
  if (useFallback) req["fallbacks"] = "default";  // se um filtro recusar, a API tenta outro modelo
  std::string body;
  serializeJson(req, body);
  req.clear();

  String headers = String("x-api-key: ") + ANTHROPIC_API_KEY + "\r\nanthropic-version: 2026-10-21\r\n";
  if (useFallback) headers += "anthropic-beta: server-side-fallback-2026-07-01\r\n";
  WiFiClientSecure c;
  if (!postStart(c, "api.anthropic.com", "/v1/messages", body.size(), headers)) return -1;
  for (size_t i = 0; i < body.size(); i += 1024)
    c.write((const uint8_t*)body.data() + i, body.size() - i < 1024 ? body.size() - i : 1024);
  body.clear();
  body.shrink_to_fit();
  Resp r;
  if (!readHead(c, r, 120000)) {
    Serial.println("[claude] sem resposta");
    return -1;
  }
  std::string resp = readBodyString(c, r, 96000);
  c.stop();
  if (r.status != 200) {
    JsonDocument f, e;
    f["error"]["message"] = true;
    deserializeJson(e, resp, DeserializationOption::Filter(f));
    const char* msg = e["error"]["message"] | "";
    Serial.printf("[claude] HTTP %d: %.200s\n", r.status, msg);
    if (r.status == 400 && useFallback && strstr(msg, "allback")) return 4001;  // tenta sem fallback
    return r.status;
  }
  JsonDocument f, doc;
  f["stop_reason"] = true;
  f["content"][0]["type"] = true;
  f["content"][0]["text"] = true;
  if (deserializeJson(doc, resp, DeserializationOption::Filter(f))) return 2;
  refused = doc["stop_reason"] == "refusal";
  textOut.clear();
  for (JsonVariant b : doc["content"].as<JsonArray>()) {
    const char* tx = b["text"];
    if (b["type"] == "text" && tx) textOut = tx;
  }
  return 0;
}

static bool askClaude(const String& heard, Reply& out) {
  std::string userMsg = stateLine() + "\n" + heard.c_str();
  std::string text;
  bool refused = false;
  bool fb = CLAUDE_FALLBACK;
  int rc = callClaude(userMsg, fb, text, refused);
  if (rc == 4001) rc = callClaude(userMsg, false, text, refused);
  if (rc != 0) return false;
  JsonDocument d;
  if (refused) {
    out.speech = MSG_REFUSAL;
    out.anim = ANIM_CONFUSED;
  } else if (deserializeJson(d, text) == DeserializationError::Ok) {
    out.speech = d["speech"] | "";
    out.anim = animIndex(d["animation"] | "talking");
    out.action = d["action"] | "none";
    out.mood = constrain((int)(d["mood_change"] | 0), -10, 10);
  } else {
    out.speech = String(text.c_str()).substring(0, 150);
  }
  out.speech.trim();
  // memoria da conversa (so na RAM: some quando desliga)
  JsonDocument h;
  h["speech"] = out.speech;
  h["animation"] = ANIM_NAMES[out.anim];
  h["action"] = out.action;
  h["mood_change"] = out.mood;
  std::string saved;
  serializeJson(h, saved);
  history.emplace_back(userMsg, saved);
  while (history.size() > HISTORY_TURNS) history.pop_front();
  return out.speech.length() > 0;
}

// ------------------------------------------------------------- voz (Google Text-to-Speech)
static int ttsRequest(const String& text, bool withTone, uint8_t* mp3, size_t cap, size_t& len) {
  JsonDocument d;
  d["input"]["text"] = text;
  d["voice"]["languageCode"] = LANG_CODE;
  if (strlen(GTTS_VOICE)) d["voice"]["name"] = GTTS_VOICE;
  else d["voice"]["ssmlGender"] = GTTS_GENDER;
  d["audioConfig"]["audioEncoding"] = "MP3";
  if (withTone) {
    d["audioConfig"]["pitch"] = GTTS_PITCH;
    d["audioConfig"]["speakingRate"] = GTTS_RATE;
  }
  std::string body;
  serializeJson(d, body);
  WiFiClientSecure c;
  if (!postStart(c, "texttospeech.googleapis.com", "/v1/text:synthesize", body.size(),
                 String("X-goog-api-key: ") + GOOGLE_API_KEY + "\r\n"))
    return -1;
  c.write((const uint8_t*)body.data(), body.size());
  Resp r;
  if (!readHead(c, r, 30000)) return -1;
  if (r.status != 200) {
    std::string err = readBodyString(c, r, 1500);
    Serial.printf("[tts] HTTP %d: %.200s\n", r.status, err.c_str());
    return r.status;
  }
  AudioSink sink(mp3, cap);
  readBody(c, r, [&](const uint8_t* b, size_t n) { sink.feed(b, n); });
  c.stop();
  len = sink.len;
  if (sink.overflow) Serial.println("[tts] audio cortado (sem memoria)");
  return 0;
}

static void playMp3(const uint8_t* data, size_t len) {
  abortAudio = false;
  playing = true;
  credits = window_;
  sendFrame('P', nullptr, 0);
  for (size_t i = 0; i < len; i += 32) {
    uint32_t t0 = millis();
    while (credits <= 0 && !abortAudio) {
      if (millis() - t0 > 3000) {
        Serial.println("[audio] o Uno parou de pedir audio");
        abortAudio = true;
      }
      vTaskDelay(1);
    }
    if (abortAudio) break;
    credits--;
    sendFrame('D', data + i, len - i < 32 ? len - i : 32);
  }
  sendFrame('E', nullptr, 0);
  playing = false;
}

static void speak(const Reply& rep) {
  // humor primeiro, depois a acao (o Uno aplica a acao em cima)
  if (rep.mood) {
    stHappy = constrain((int)stHappy + rep.mood, 0, 100);
    uint8_t s[4] = {stHunger, stHappy, stEnergy, stClean};
    sendFrame('S', s, 4);
  }
  int act = actIndex(rep.action.c_str());
  if (act > 0) {
    uint8_t a = act;
    sendFrame('X', &a, 1);
  }
  size_t cap = 0, len = 0;
  uint8_t* mp3 = bigAlloc(MAX_MP3_BYTES, &cap);
  int rc = -1;
  if (mp3) {
    rc = ttsRequest(rep.speech, true, mp3, cap, len);
    if (rc == 400) rc = ttsRequest(rep.speech, false, mp3, cap, len);  // voz sem ajuste de tom
  } else {
    Serial.println("[tts] sem memoria para o audio");
  }
  float dur = (rc == 0 && len) ? len / MP3_BYTES_PER_SEC : max(2.0f, rep.speech.length() / 14.0f);
  sendAnim(rep.anim, (uint8_t)min(255.0f, ceilf(dur + 1.5f)));
  sendText(rep.speech.c_str(), (uint32_t)(dur * 1000));
  if (rc == 0 && len) playMp3(mp3, len);
  else if (rc != 0) Serial.println("[tts] sem voz, mostrando so o texto");
  if (mp3) free(mp3);
}

// ------------------------------------------------------------- conversa (tarefa separada)
static void convTask(void*) {
  uint8_t* audio = convAudio;
  size_t len = convLen;
  convAudio = nullptr;
  sendAnim(ANIM_THINKING, 30);
  Serial.printf("[conv] %u bytes de audio, heap livre %u\n", (unsigned)len, (unsigned)ESP.getFreeHeap());
  String heard = transcribe(audio, len);
  free(audio);
  if (heard.length() == 0) {
    showProblem(MSG_NOT_UNDERSTOOD);
  } else {
    Serial.printf("[conv] voce: %s\n", heard.c_str());
    Reply rep;
    if (askClaude(heard, rep)) {
      Serial.printf("[conv] pet: %s\n", rep.speech.c_str());
      speak(rep);
    } else {
      showProblem(MSG_CLAUDE_ERR);
    }
  }
  busy = false;
  vTaskDelete(nullptr);
}

// ------------------------------------------------------------- quadros que chegam do Uno
static void handleUno(uint8_t t, const uint8_t* d, uint8_t n) {
  uint32_t now = millis();
  bool wasQuiet = !unoSeen || now - lastUnoFrame > 12000;
  lastUnoFrame = now;
  unoSeen = true;
  switch (t) {
    case 'k':
      credits += n ? d[0] : 1;
      break;
    case 'h':
      if (n >= 14) {
        int rx = d[3] * 4;
        window_ = rx > 84 ? (rx - 48) / 36 : 1;
        stHunger = d[4]; stHappy = d[5]; stEnergy = d[6]; stClean = d[7]; stSleeping = d[8];
        if (wasQuiet) {  // Uno acabou de ligar: manda nome e volume
          sendFrame('N', (const uint8_t*)PET_NAME, strlen(PET_NAME));
          uint8_t v = UNO_VOLUME_ATT;
          sendFrame('V', &v, 1);
          Serial.printf("[uno] conectado (janela de audio %u)\n", window_);
          if (WiFi.status() != WL_CONNECTED) showProblem(MSG_NO_WIFI);
        }
      }
      break;
    case 's':
      if (n >= 5) { stHunger = d[0]; stHappy = d[1]; stEnergy = d[2]; stClean = d[3]; stSleeping = d[4]; }
      break;
    case 'b':
      if (n) {
        if (evCount == 3) { evIds[0] = evIds[1]; evIds[1] = evIds[2]; evCount = 2; }
        evIds[evCount++] = d[0];
      }
      break;
    case 'r':
      if (busy) break;  // ainda respondendo a fala anterior
      if (!recBuf) recBuf = bigAlloc(MAX_REC_BYTES, &recCap);
      recLen = 0;
      recording = recBuf != nullptr;
      if (!recording) Serial.println("[uno] sem memoria para gravar");
      break;
    case 'm':
      if (recording && recLen + n <= recCap) {
        memcpy(recBuf + recLen, d, n);
        recLen += n;
      }
      break;
    case 'q':
      if (!recording) break;
      recording = false;
      if (WiFi.status() != WL_CONNECTED) { showProblem(MSG_NO_WIFI); break; }
      if (recLen < 2400) { showProblem(MSG_NOT_UNDERSTOOD); break; }  // menos de 0,3 s
      busy = true;
      convAudio = recBuf;
      convLen = recLen;
      recBuf = nullptr;  // a tarefa libera
      if (xTaskCreate(convTask, "conversa", 20480, nullptr, 1, nullptr) != pdPASS) {
        free(convAudio);
        convAudio = nullptr;
        busy = false;
        showProblem(MSG_CLAUDE_ERR);
      }
      break;
    case 'x':
      abortAudio = true;
      break;
  }
}

static void serviceUno() {
  static uint8_t st = 0, type, len, pos, sum;
  static uint8_t buf[256];
  while (UNO.available()) {
    uint8_t c = UNO.read();
    switch (st) {
      case 0: if (c == 0x7E) st = 1; break;
      case 1: type = c; sum = c; st = 2; break;
      case 2: len = c; sum += c; pos = 0; st = len ? 3 : 4; break;
      case 3: buf[pos++] = c; sum += c; if (pos >= len) st = 4; break;
      case 4: st = 0; if (c == sum) handleUno(type, buf, len); break;
    }
  }
}

// ------------------------------------------------------------- setup/loop
void setup() {
  Serial.begin(115200);
  UNO.setRxBufferSize(8192);
  UNO.begin(UNO_BAUD, SERIAL_8N1, UNO_RX_PIN, UNO_TX_PIN);
  txLock = xSemaphoreCreateMutex();
  Serial.printf("\nTamagotchi + Claude: ponte ESP32 (%s)\n", PET_NAME);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  if (strlen(WIFI_PASS)) WiFi.begin(WIFI_SSID, WIFI_PASS);
  else WiFi.begin(WIFI_SSID);
  sendFrame('H', nullptr, 0);
}

void loop() {
  serviceUno();
  uint32_t now = millis();
  bool up = WiFi.status() == WL_CONNECTED;
  if (up != wifiWasUp) {
    wifiWasUp = up;
    if (up) {
      Serial.printf("[wifi] conectado, IP %s\n", WiFi.localIP().toString().c_str());
      if (unoSeen) {
        sendAnim(ANIM_HAPPY, 2);
        sendText(MSG_WIFI_OK, 2000);
      }
    } else {
      Serial.println("[wifi] desconectado");
    }
  }
  // O Uno so deixa falar se recebeu algo nos ultimos 10 s. Sem Wi-Fi nao
  // mandamos nada, e ele mostra que esta sem conexao quando tentam falar.
  if (up && !playing && now - lastPing > 3000) {
    lastPing = now;
    sendFrame('H', nullptr, 0);
  }
  vTaskDelay(1);
}
