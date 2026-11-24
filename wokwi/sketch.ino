// =====================================================================
//  Tamagotchi  |  versao para o simulador Wokwi
//
//  O mesmo bichinho do Arduino Uno (50 animacoes, menu, fome, sono, banho,
//  tela de status) junto com o cerebro da ponte ESP32 (IA direto pela API),
//  tudo em um ESP32 so, porque o Wokwi simula uma placa por projeto.
//
//  Diferencas para o hardware real:
//   - a tela e uma ILI9341 colorida (a cena de 128x64 aparece ampliada 2x);
//   - o Wokwi nao tem o VS1053: no lugar do microfone voce digita no
//     Serial Monitor, e no lugar da voz o buzzer faz "piadinhos" de bichinho.
//
//  Botoes:  A (verde, tecla a) abre o menu / proximo item
//           B (azul,  tecla s) escolhe
//           C (vermelho, tecla d) volta, para a fala ou faz carinho;
//             segurar C = modo ouvindo (a frase e digitada no Serial)
//  Serial:  qualquer frase vai para o cerebro. Comandos: /comer /brincar
//           /banho /dormir /acordar /carinho /status /reset /ajuda
//  Celular: com NTFY_TOPIC em secrets.h, o PIXO ouve o topico do ntfy.sh.
//           No app ntfy, assine o topico e mande a frase (o microfone do
//           teclado faz o ditado); a resposta volta no mesmo topico.
//
//  Para conversar, coloque a chave da API em secrets.h.
// =====================================================================
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <EEPROM.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <deque>
#include <string>
#include <utility>

#include "secrets.h"
#include "anim_data.h"
#include "config.h"
#include "draw.h"
#include "prompt.h"

#ifdef API_KEY
#define HAS_KEY 1
#else
#define HAS_KEY 0
#endif

#ifdef NTFY_TOPIC
#define HAS_NTFY 1  // fala pelo celular (app ntfy)
#else
#define HAS_NTFY 0
#endif

// ------------------------------------------------------------- tipos (antes das funcoes)
struct Stats {
  uint8_t magic, hunger, happy, energy, clean, sleeping;
  uint32_t ageMin;
};
#define STATS_MAGIC 0x5B

struct Reply {
  String speech;
  uint8_t anim = ANIM_TALKING;
  String action = "none";
  int mood = 0;
};

struct Resp {
  int status = -1;
  bool chunked = false;
  long contentLength = -1;
};

struct Btn { uint8_t pin; bool down; bool held; uint32_t t0, tchg; };
struct OutMsg { String topic, body, title, tags; };  // mensagem para o ntfy

// ------------------------------------------------------------- estado do pet
static Stats st;
static uint8_t curAnim = ANIM_HELLO, autoAnim = ANIM_IDLE, overrideAnim = ANIM_HELLO;
static uint32_t overrideUntil = 2500;
static uint16_t frameT = 0;
static uint32_t lastFrame, lastDecay, lastAge, lastPick, lastSave;
static bool forcePick = true;
static bool menuActive = false, statsScreen = false, talking = false, listening = false;
static uint8_t menuSel = 0;
static uint32_t menuUntil, statsUntil, listenUntil, talkUntil;
static char subtitle[161];
static uint32_t subStart;
static uint16_t subDur;
static char petName[13] = PET_NAME;
static uint32_t frameNow;
static const char* const menuLabels[] = {MENU_LABELS};
static Btn btns[3] = {{PIN_BTN_A, 0, 0, 0, 0}, {PIN_BTN_B, 0, 0, 0, 0}, {PIN_BTN_C, 0, 0, 0, 0}};

// ------------------------------------------------------------- estado do cerebro
static volatile bool busy = false, replyReady = false, replyOk = false;
static String pendingText;
static Reply lastReply;
static uint8_t evIds[3];
static uint8_t evCount = 0;
static std::deque<std::pair<std::string, std::string>> history;
static bool wifiUp = false;
static String serialLine;

// ------------------------------------------------------------- estado do celular (ntfy)
static volatile bool ntfyUp = false;
static volatile bool stateDirty = false;  // avisar o cerebro do PC que o pet mudou
static SemaphoreHandle_t inboxLock = nullptr;
static std::deque<String> inbox;  // frases que chegaram do celular
static String ntfyLastId;

// ------------------------------------------------------------- tela
Adafruit_ILI9341 tft(TFT_PIN_CS, TFT_PIN_DC, TFT_PIN_RST);
#define SCR_W 320
#define SCR_H 240
#define SC 2                              // ampliacao da cena 128x64
#define SCENE_X ((SCR_W - 128 * SC) / 2)  // 32
#define SCENE_Y 40
static uint16_t lineBuf[128 * SC * 8 * SC];  // uma pagina ampliada (256x16)
static uint8_t prevPet[8][128], prevFx[8][128];
static uint8_t styleKey = 255, frameStyle = 0;
static bool dim = false;

static uint16_t COL_BG, COL_FRAME, COL_TEXT, COL_MUTED, colPet;

static uint16_t dimmed(uint16_t c) { return dim ? (c >> 1) & 0x7BEF : c; }

static void drawChrome() {
  tft.fillScreen(COL_BG);
  tft.drawRect(SCENE_X - 4, SCENE_Y - 4, 128 * SC + 8, 64 * SC + 8, COL_FRAME);
  tft.drawRect(SCENE_X - 3, SCENE_Y - 3, 128 * SC + 6, 64 * SC + 6, COL_FRAME);
  tft.setTextWrap(false);
  tft.setTextSize(2);
  tft.setTextColor(COL_TEXT);
  tft.setCursor((SCR_W - 10 * 12) / 2, 10);  // centralizado
  tft.print("Tamagotchi");
  tft.setTextSize(1);
  tft.setTextColor(COL_MUTED);
  tft.setCursor(SCENE_X, SCENE_Y + 64 * SC + 12);
  tft.print("A: menu/proximo   B: escolher   C: voltar");
  tft.setCursor(SCENE_X, SCENE_Y + 64 * SC + 24);
  tft.print(HAS_NTFY ? "Falar: app ntfy no celular ou Serial Monitor" : "Falar: digite no Serial Monitor e aperte Enter");
  styleKey = 255;  // redesenha a cena inteira
}

static void drawNetStatus() {
  const uint16_t ok = tft.color565(130, 255, 140), warn = tft.color565(255, 215, 90);
  tft.fillRect(0, SCR_H - 34, SCR_W, 34, COL_BG);
  tft.setTextSize(1);
  tft.setCursor(SCENE_X, SCR_H - 30);
  tft.setTextColor(wifiUp ? ok : tft.color565(255, 120, 120));
  tft.print(wifiUp ? "Wi-Fi ok" : "Wi-Fi...");
  tft.setTextColor(COL_MUTED);
  tft.print("   Cerebro: ");
  tft.setTextColor((HAS_KEY || HAS_NTFY) ? ok : warn);
  tft.print(HAS_KEY ? "no ESP32" : (HAS_NTFY ? "no PC (CEREBRO.bat)" : "sem chave (secrets.h)"));
#if HAS_NTFY
  tft.setCursor(SCENE_X, SCR_H - 16);
  tft.setTextColor(COL_MUTED);
  tft.print("Celular: ");
  tft.setTextColor(ntfyUp ? ok : warn);
  tft.print("ntfy.sh/" NTFY_TOPIC);
  tft.print(ntfyUp ? "  ok" : "  ...");
#endif
}

static void dispInit() {
  tft.begin(40000000);
  tft.setRotation(1);  // deitada: 320x240
  COL_BG = tft.color565(4, 6, 16);
  COL_FRAME = tft.color565(70, 50, 120);
  COL_TEXT = tft.color565(240, 236, 255);
  COL_MUTED = tft.color565(150, 140, 190);
  static const uint8_t PET_RGB[5][3] = {{125, 235, 255}, {130, 255, 140}, {255, 130, 200}, {255, 255, 255}, {255, 215, 90}};
  const uint8_t* c = PET_RGB[TFT_PET_COLOR % 5];
  colPet = tft.color565(c[0], c[1], c[2]);
  drawChrome();
  drawNetStatus();
}

static void dispBrightness(bool low) { dim = low; }

// cor da camada de efeitos/textos conforme a regiao da cena (igual a TFT do Uno)
static uint16_t fxColor(uint8_t x, uint8_t y) {
  static const uint8_t BAR[4][3] = {{255, 159, 67}, {255, 111, 181}, {255, 209, 102}, {103, 232, 249}};
  const uint8_t* b;
  if (statsScreen) {
    if (y >= 12 && y < 56 && x < 8) { b = BAR[(y - 12) / 11]; return tft.color565(b[0], b[1], b[2]); }
    return COL_TEXT;
  }
  if (y < 8) {
    if (menuActive) return COL_TEXT;
    b = BAR[x >> 5];
    return tft.color565(b[0], b[1], b[2]);
  }
  if (y >= 55) return tft.color565(255, 230, 150);
  return tft.color565(255, 120, 190);
}

// manda so as paginas que mudaram (deixa o simulador bem mais rapido)
static void dispSendPage(uint8_t p) {
  bool all = frameStyle != styleKey;
  if (!all && !memcmp(prevPet[p], pageBuf, 128) && !memcmp(prevFx[p], fxBuf, 128)) return;
  memcpy(prevPet[p], pageBuf, 128);
  memcpy(prevFx[p], fxBuf, 128);
  const uint16_t bg = COL_BG, pet = dimmed(colPet);
  const uint16_t W = 128 * SC;
  for (uint8_t r = 0; r < 8; r++) {
    uint8_t m = 1 << r;
    uint8_t y = p * 8 + r;
    uint16_t* row = lineBuf + (uint16_t)r * SC * W;
    for (uint8_t x = 0; x < 128; x++) {
      uint16_t c = (pageBuf[x] & m) ? pet : ((fxBuf[x] & m) ? dimmed(fxColor(x, y)) : bg);
      for (uint8_t s = 0; s < SC; s++) row[x * SC + s] = c;
    }
    for (uint8_t s = 1; s < SC; s++) memcpy(row + s * W, row, W * 2);
  }
  tft.drawRGBBitmap(SCENE_X, SCENE_Y + p * 8 * SC, lineBuf, W, 8 * SC);
}

// ------------------------------------------------------------- pet
static uint8_t clamp100(int16_t v) { return v < 0 ? 0 : (v > 100 ? 100 : v); }

static void playAnim(uint8_t a, uint32_t ms) {
  if (a >= ANIM_COUNT) return;
  overrideAnim = a;
  overrideUntil = millis() + ms;
  if (a != curAnim) { curAnim = a; frameT = 0; }
}

static void setSubtitle(const char* s, uint16_t durMs) {
  strncpy(subtitle, s, sizeof(subtitle) - 1);
  subtitle[sizeof(subtitle) - 1] = 0;
  subStart = millis();
  subDur = durMs;
}

static void saveStats() {
  EEPROM.put(0, st);
  EEPROM.commit();
  lastSave = millis();
}

static void resetStats() {
  st.magic = STATS_MAGIC; st.hunger = 80; st.happy = 80; st.energy = 80; st.clean = 80;
  st.sleeping = 0; st.ageMin = 0;
  saveStats();
}

static void printStats() {
  Serial.printf("[pet] fome %u  alegria %u  energia %u  higiene %u  %s  idade %lud%luh\n",
                st.hunger, st.happy, st.energy, st.clean, st.sleeping ? "dormindo" : "acordado",
                (unsigned long)(st.ageMin / 1440), (unsigned long)((st.ageMin / 60) % 24));
}

static void decay() {
  stateDirty = true;
  if (st.sleeping) {
    st.energy = clamp100(st.energy + 4);
    st.hunger = clamp100(st.hunger - 1);
    if (st.energy >= 100) { st.sleeping = 0; playAnim(ANIM_YAWN, 2500); dispBrightness(false); }
  } else {
    st.hunger = clamp100(st.hunger - 2);
    st.energy = clamp100(st.energy - 1);
    st.clean = clamp100(st.clean - 1);
    st.happy = clamp100(st.happy - ((st.hunger < 20 || st.clean < 20) ? 3 : 1));
  }
}

static uint8_t pickMood() {
  static const uint8_t good[] = {ANIM_IDLE, ANIM_IDLE, ANIM_HAPPY, ANIM_CURIOUS, ANIM_SINGING,
                                 ANIM_RELAXED, ANIM_WINK, ANIM_DANCING, ANIM_IDLE, ANIM_BORED};
  static const uint8_t meh[] = {ANIM_IDLE, ANIM_BORED, ANIM_IDLE, ANIM_THINKING};
  if (st.sleeping) return ANIM_SLEEPING;
  if (st.hunger < 20) return ANIM_HUNGRY;
  if (st.energy < 20) return ANIM_SLEEPY;
  if (st.clean < 20) return ANIM_DIRTY;
  if (st.happy < 20) return ANIM_SAD;
  uint8_t m = min(min(st.hunger, st.happy), min(st.energy, st.clean));
  if (m < 45) return meh[random(sizeof(meh))];
  return good[random(sizeof(good))];
}

static void rememberEvent(uint8_t act) {
  if (evCount < sizeof(evIds)) evIds[evCount++] = act;
  else { evIds[0] = evIds[1]; evIds[1] = evIds[2]; evIds[2] = act; }
}

static void doAction(uint8_t act) {
  switch (act) {
    case ACT_FEED:
      if (st.sleeping) playAnim(ANIM_ANNOYED, 2000);
      else if (st.hunger >= 90) { st.happy = clamp100(st.happy - 3); playAnim(ANIM_FULL, 2500); }
      else { st.hunger = clamp100(st.hunger + 30); st.happy = clamp100(st.happy + 3); playAnim(ANIM_EATING, 3000); }
      break;
    case ACT_PLAY:
      if (st.sleeping) playAnim(ANIM_ANNOYED, 2000);
      else if (st.energy < 15) playAnim(ANIM_SLEEPY, 3000);
      else {
        st.happy = clamp100(st.happy + 20); st.energy = clamp100(st.energy - 10);
        st.hunger = clamp100(st.hunger - 5); playAnim(ANIM_PLAYING, 3500);
      }
      break;
    case ACT_CLEAN:
      if (st.sleeping) playAnim(ANIM_ANNOYED, 2000);
      else { st.clean = 100; st.happy = clamp100(st.happy + 5); playAnim(ANIM_BATHING, 3500); }
      break;
    case ACT_SLEEP:
      st.sleeping = !st.sleeping;
      playAnim(ANIM_YAWN, st.sleeping ? 2000 : 2500);
      saveStats();
      break;
    case ACT_WAKE:
      if (st.sleeping) { st.sleeping = 0; playAnim(ANIM_YAWN, 2500); }
      break;
    case ACT_STATS:
      statsScreen = true; statsUntil = millis() + 5000;
      break;
    case ACT_PET:
      if (!st.sleeping) { st.happy = clamp100(st.happy + 2); playAnim(ANIM_LOVE, 2000); }
      break;
    default: return;
  }
  dispBrightness(st.sleeping);
  if (act != ACT_STATS) { rememberEvent(act); stateDirty = true; }
  Serial.printf("[pet] acao: %s\n", ACT_NAMES[act]);
  printStats();
}

// ------------------------------------------------------------- voz (buzzer)
static void stopVoice() {
  talking = false;
  noTone(PIN_BUZZER);
}

static void serviceVoice() {
  static uint32_t nextBeep = 0;
  if (!talking) return;
  uint32_t now = millis();
  if ((int32_t)(now - talkUntil) > 0) { stopVoice(); return; }
#if VOICE_BEEPS
  if ((int32_t)(now - nextBeep) >= 0) {
    // uma "silaba" por letra que esta passando na legenda
    uint32_t el = now - subStart;
    uint8_t n = textLen(subtitle);
    char ch = n ? subtitle[(el / 85) % n] : 'a';
    if (ch == ' ' || ch == ',' || ch == '.') nextBeep = now + 110;
    else {
      tone(PIN_BUZZER, 700 + (ch * 37) % 900, 55);
      nextBeep = now + 85;
    }
  }
#endif
}

// ------------------------------------------------------------- texto
// Tira acentos (a fonte da cena so tem ASCII)
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

static void say(const char* utf8, uint8_t anim) {
  String t = asciiFold(utf8, sizeof(subtitle) - 1);
  uint16_t dur = max((uint16_t)2500, (uint16_t)(t.length() * 85));
  setSubtitle(t.c_str(), dur);
  playAnim(anim, dur + 600);
  talking = true;
  talkUntil = millis() + dur;
}

static void showProblem(const char* msg) {
  playAnim(ANIM_CONFUSED, 3000);
  setSubtitle(msg, 2500);
}

// ------------------------------------------------------------- HTTPS
// Conecta com HTTPS tentando ate 3 vezes: no simulador o tempo padrao (3 s)
// as vezes nao basta. Se falhar, mostra o motivo e a memoria livre.
static bool tlsConnect(WiFiClientSecure& c, const char* host, const char* tag) {
  c.setInsecure();  // sem verificar certificado (simples para prototipo)
  c.setHandshakeTimeout(60);
  for (uint8_t i = 1; i <= 3; i++) {
    if (c.connect(host, 443, 30000)) return true;
    char err[96] = "";
    c.lastError(err, sizeof(err));
    Serial.printf("[%s] falha ao conectar em %s (tentativa %u/3): %s | memoria livre %u, maior bloco %u\n", tag, host,
                  (unsigned)i, err, (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxAllocHeap());
    c.stop();
    delay(1500);
  }
  return false;
}

static int readByteT(Client& c, uint32_t idleMs) {
  uint32_t t0 = millis();
  while (!c.available()) {
    if (!c.connected()) return -1;
    if (millis() - t0 > idleMs) return -1;
    delay(2);
  }
  return c.read();
}

static bool readLine(Client& c, String& line, uint32_t idleMs) {
  line = "";
  for (;;) {
    int ch = readByteT(c, idleMs);
    if (ch < 0) return line.length() > 0;
    if (ch == '\n') return true;
    if (ch != '\r' && line.length() < 2048) line += (char)ch;
  }
}

static bool readHead(Client& c, Resp& r, uint32_t firstByteMs) {
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

static int readBlock(Client& c, uint8_t* buf, size_t want, uint32_t idleMs) {
  uint32_t t0 = millis();
  for (;;) {
    int a = c.available();
    if (a > 0) return c.read(buf, (size_t)a < want ? (size_t)a : want);
    if (!c.connected()) return -1;
    if (millis() - t0 > idleMs) return -1;
    delay(2);
  }
}

static std::string readBodyString(Client& c, const Resp& r, size_t maxLen) {
  std::string s;
  uint8_t buf[512];
  auto add = [&](const uint8_t* d, size_t n) { if (s.size() < maxLen) s.append((const char*)d, n); };
  if (!r.chunked) {
    long left = r.contentLength;
    while (left != 0) {
      size_t want = (left < 0 || left > (long)sizeof(buf)) ? sizeof(buf) : (size_t)left;
      int n = readBlock(c, buf, want, 20000);
      if (n <= 0) break;
      add(buf, n);
      if (left > 0) left -= n;
    }
    return s;
  }
  String line;
  for (;;) {
    if (!readLine(c, line, 20000)) return s;
    long size = strtol(line.c_str(), nullptr, 16);
    if (size <= 0) return s;
    while (size > 0) {
      int n = readBlock(c, buf, size > (long)sizeof(buf) ? sizeof(buf) : (size_t)size, 20000);
      if (n <= 0) return s;
      add(buf, n);
      size -= n;
    }
    readLine(c, line, 20000);  // CRLF depois de cada pedaco
  }
}

// ------------------------------------------------------------- celular e cerebro do PC (ntfy)
// Tudo pelo ntfy.sh em HTTP simples (porta 80): no gateway do Wokwi o HTTPS
// as vezes cai no meio. Dois topicos:
//   NTFY_TOPIC       conversa de gente: frases do celular e respostas do PIXO
//   NTFY_TOPIC "_pc" maquina: comandos do cerebro do PC (tag "cmd"), estado do
//                    pet (tag "state") e frases digitadas no Serial (tag "text")
#if HAS_NTFY
#define NTFY_TOPIC_PC NTFY_TOPIC "_pc"

static std::deque<OutMsg> outbox;  // publicado pela tarefa ntfyPubTask

static void queuePublish(const String& topic, const String& body, const char* title, const char* tags) {
  xSemaphoreTake(inboxLock, portMAX_DELAY);
  if (outbox.size() < 8) outbox.push_back({topic, body, String(title ? title : ""), String(tags ? tags : "")});
  xSemaphoreGive(inboxLock);
}

static bool ntfyConnect(WiFiClient& c) {
  for (uint8_t i = 1; i <= 3; i++) {
    if (c.connect("ntfy.sh", 80, 20000)) return true;
    Serial.printf("[celular] falha ao conectar no ntfy.sh (tentativa %u/3)\n", (unsigned)i);
    c.stop();
    delay(1500);
  }
  return false;
}

static bool ntfyPost(const OutMsg& m) {
  WiFiClient c;
  if (!ntfyConnect(c)) return false;
  String h = String("POST /") + m.topic + " HTTP/1.1\r\nHost: ntfy.sh\r\nUser-Agent: tamagotchi-wokwi\r\n" +
             "Content-Type: text/plain; charset=utf-8\r\n";
  if (m.title.length()) h += "Title: " + m.title + "\r\n";
  if (m.tags.length()) h += "Tags: " + m.tags + "\r\n";
  h += "Content-Length: " + String((unsigned long)m.body.length()) + "\r\nConnection: close\r\n\r\n";
  c.print(h);
  c.print(m.body);
  Resp r;
  readHead(c, r, 20000);
  c.stop();
  if (r.status != 200) Serial.printf("[celular] o ntfy recusou a mensagem (HTTP %d)\n", r.status);
  return r.status == 200;
}

static String stateJson() {
  JsonDocument d;
  d["hunger"] = st.hunger;
  d["happy"] = st.happy;
  d["energy"] = st.energy;
  d["clean"] = st.clean;
  d["sleeping"] = st.sleeping != 0;
  JsonArray ev = d["events"].to<JsonArray>();
  for (uint8_t i = 0; i < evCount; i++) ev.add(evIds[i] < ACT_COUNT ? ACT_NAMES[evIds[i]] : "?");
  String out;
  serializeJson(d, out);
  return out;
}

// publica as mensagens da fila e, no modo cerebro do PC, o estado do pet
static void ntfyPubTask(void*) {
  uint32_t lastState = 0;
  for (;;) {
    OutMsg m;
    bool have = false;
    xSemaphoreTake(inboxLock, portMAX_DELAY);
    if (!outbox.empty()) { m = outbox.front(); outbox.pop_front(); have = true; }
    xSemaphoreGive(inboxLock);
    if (have) {
      if (WiFi.status() == WL_CONNECTED) ntfyPost(m);
      continue;
    }
#if !HAS_KEY
    if (stateDirty && ntfyUp && millis() - lastState > 4000) {
      stateDirty = false;
      lastState = millis();
      OutMsg s{NTFY_TOPIC_PC, stateJson(), "", "state"};
      evCount = 0;  // o cerebro do PC ja vai saber dessas acoes
      ntfyPost(s);
      continue;
    }
#endif
    delay(300);
  }
}

// ouve os dois topicos e entrega para o loop: 'H' frase para o cerebro do ESP32,
// 'T' frase que o cerebro do PC vai responder, 'C' comando do cerebro do PC
static void ntfyTask(void*) {
  uint32_t backoff = 3000;
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) { ntfyUp = false; delay(1000); continue; }
    WiFiClient c;
    if (!ntfyConnect(c)) { ntfyUp = false; delay(backoff); continue; }
    String path = String("/") + NTFY_TOPIC + "," + NTFY_TOPIC_PC + "/json";
    if (ntfyLastId.length()) path += "?since=" + ntfyLastId;  // nao perde mensagens ao reconectar
    c.print(String("GET ") + path + " HTTP/1.1\r\nHost: ntfy.sh\r\nUser-Agent: tamagotchi-wokwi\r\n\r\n");
    Resp r;
    if (!readHead(c, r, 20000) || r.status != 200) {
      Serial.printf("[celular] ntfy respondeu %d, tentando de novo...\n", r.status);
      c.stop();
      ntfyUp = false;
      delay(backoff);
      if (backoff < 60000) backoff *= 2;
      continue;
    }
    backoff = 3000;
    if (!ntfyUp) Serial.println("[celular] conectado no ntfy.sh/" NTFY_TOPIC);
    ntfyUp = true;
    stateDirty = true;
    String line;
    while (readLine(c, line, 120000)) {
      if (!line.startsWith("{")) continue;  // tamanhos dos pedacos (chunked)
      JsonDocument f, d;
      f["id"] = true;
      f["event"] = true;
      f["topic"] = true;
      f["message"] = true;
      f["tags"] = true;
      if (deserializeJson(d, line, DeserializationOption::Filter(f))) continue;
      if (strcmp(d["event"] | "", "message") != 0) continue;  // "open" e "keepalive"
      const char* id = d["id"];
      if (id) ntfyLastId = id;
      bool tagPixo = false, tagCmd = false;
      for (JsonVariant t : d["tags"].as<JsonArray>()) {
        const char* s = t | "";
        if (!strcmp(s, "pixo")) tagPixo = true;
        if (!strcmp(s, "cmd")) tagCmd = true;
      }
      String m = d["message"] | "";
      m.trim();
      char kind;
      if (strcmp(d["topic"] | "", NTFY_TOPIC_PC) == 0) {
        if (!tagCmd) continue;  // estado e texto que o proprio ESP32 mandou
        kind = 'C';
      } else {
        if (tagPixo || !m.length()) continue;  // respostas do proprio PIXO
        kind = HAS_KEY ? 'H' : 'T';
      }
      xSemaphoreTake(inboxLock, portMAX_DELAY);
      if (inbox.size() < 6) inbox.push_back(String(kind) + m);
      xSemaphoreGive(inboxLock);
    }
    c.stop();
    ntfyUp = false;
    delay(1000);
  }
}
#endif

// ------------------------------------------------------------- cerebro
static uint8_t animIndex(const char* name) {
  if (name)
    for (uint8_t i = 0; i < ANIM_COUNT; i++)
      if (strcmp(ANIM_NAMES[i], name) == 0) return i;
  return ANIM_TALKING;
}

static std::string stateLine() {
  char buf[200];
  snprintf(buf, sizeof(buf), "[state: food %u/100, joy %u/100, energy %u/100, hygiene %u/100, %s",
           st.hunger, st.happy, st.energy, st.clean, st.sleeping ? "sleeping" : "awake");
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

#if HAS_KEY
// level 0 = completo, 1 = sem effort, 2 = sem formato JSON (se o modelo recusar algum campo)
// Retorna 0 se deu certo, ou o codigo HTTP do erro (-1 = sem conexao)
static int callBrain(const std::string& userMsg, int level, std::string& textOut, bool& refused) {
  JsonDocument req;
  req["model"] = BRAIN_MODEL;
  req["max_tokens"] = 1500;
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
  m["content"] = level >= 2 ? userMsg + "\nReply ONLY with JSON: {\"speech\":\"...\",\"animation\":\"...\",\"action\":\"none\",\"mood_change\":0}" : userMsg;
  if (level == 0) req["output_config"]["effort"] = BRAIN_EFFORT;
  if (level <= 1) {
    req["output_config"]["format"]["type"] = "json_schema";
    req["output_config"]["format"]["schema"] = serialized(SCHEMA_JSON);
  }
  std::string body;
  serializeJson(req, body);
  req.clear();

  WiFiClientSecure c;
  if (!tlsConnect(c, "api.anthropic.com", "cerebro")) return -1;
  String h = String("POST /v1/messages HTTP/1.1\r\nHost: api.anthropic.com\r\nContent-Type: application/json\r\nContent-Length: ") +
             String((unsigned long)body.size()) + "\r\nConnection: close\r\nx-api-key: " + API_KEY +
             "\r\nanthropic-version: 2026-10-21\r\n\r\n";
  c.print(h);
  for (size_t i = 0; i < body.size(); i += 1024)
    c.write((const uint8_t*)body.data() + i, body.size() - i < 1024 ? body.size() - i : 1024);
  body.clear();
  body.shrink_to_fit();
  Resp r;
  if (!readHead(c, r, 90000)) {
    Serial.println("[cerebro] sem resposta");
    return -1;
  }
  std::string resp = readBodyString(c, r, 32000);
  c.stop();
  if (r.status != 200) {
    JsonDocument f, e;
    f["error"]["message"] = true;
    deserializeJson(e, resp, DeserializationOption::Filter(f));
    Serial.printf("[cerebro] HTTP %d: %.200s\n", r.status, (const char*)(e["error"]["message"] | ""));
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

static bool askBrain(const String& heard, Reply& out) {
  std::string userMsg = stateLine() + "\n" + heard.c_str();
  std::string text;
  bool refused = false;
  int rc = callBrain(userMsg, 0, text, refused);
  if (rc == 400) rc = callBrain(userMsg, 1, text, refused);
  if (rc == 400) rc = callBrain(userMsg, 2, text, refused);
  if (rc != 0) return false;
  JsonDocument d;
  if (refused) {
    out.speech = MSG_REFUSAL;
    out.anim = ANIM_CONFUSED;
  } else {
    size_t a = text.find('{'), b = text.rfind('}');
    std::string js = (a != std::string::npos && b != std::string::npos && b > a) ? text.substr(a, b - a + 1) : text;
    if (deserializeJson(d, js) == DeserializationError::Ok) {
      out.speech = d["speech"] | "";
      out.anim = animIndex(d["animation"] | "talking");
      out.action = d["action"] | "none";
      out.mood = constrain((int)(d["mood_change"] | 0), -10, 10);
    } else {
      out.speech = String(text.c_str()).substring(0, 150);
    }
  }
  out.speech.trim();
  // memoria da conversa (so na RAM: some quando reinicia)
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

// tarefa fixa no outro nucleo (criada uma vez so) para a animacao "pensando" nao travar
static TaskHandle_t brainHandle = nullptr;
static volatile bool netTestPending = false;

// /rede: testa HTTPS para alguns sites e mostra o resultado de cada um
static void netTest() {
  static const char* const hosts[] = {"ntfy.sh", "www.google.com", "www.cloudflare.com", "api.anthropic.com"};
  for (const char* h : hosts) {
    WiFiClientSecure c;
    c.setInsecure();
    c.setHandshakeTimeout(60);
    uint32_t t0 = millis();
    bool ok = c.connect(h, 443, 30000);
    char err[96] = "";
    if (!ok) c.lastError(err, sizeof(err));
    Serial.printf("[rede] %s: %s em %lu ms %s\n", h, ok ? "ok" : "FALHOU", (unsigned long)(millis() - t0), err);
    c.stop();
  }
  Serial.println("[rede] fim do teste");
}

static void brainTask(void*) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (netTestPending) { netTest(); netTestPending = false; continue; }
    Reply r;
    bool ok = askBrain(pendingText, r);
    lastReply = r;
    replyOk = ok;
    Serial.printf("[cerebro] pilha livre: %u bytes\n", (unsigned)uxTaskGetStackHighWaterMark(nullptr));
    replyReady = true;
#if HAS_NTFY
    queuePublish(NTFY_TOPIC, ok ? r.speech : String(MSG_BRAIN_ERR), petName, "pixo");  // a resposta tambem aparece no celular
#endif
  }
}
#endif

static void showThinking() {
  listening = false;
  stopVoice();
  if (st.sleeping) { st.sleeping = 0; dispBrightness(false); }
  overrideAnim = ANIM_THINKING; overrideUntil = millis() + 45000UL; curAnim = ANIM_THINKING; frameT = 0;
  subtitle[0] = 0;
}

static void startConversation(const String& text, const char* who) {
  Serial.printf("[%s] %s\n", who, text.c_str());
  listening = false;
#if !HAS_KEY
#if HAS_NTFY
  queuePublish(NTFY_TOPIC_PC, text, nullptr, "text");  // o cerebro do PC responde
  showThinking();
#else
  showProblem(MSG_NO_KEY);
  Serial.println("[pet] Coloque a chave da API em secrets.h para eu conversar.");
#endif
  return;
#else
  if (busy) { setSubtitle(MSG_BUSY, 2000); return; }
  if (!wifiUp) { showProblem(MSG_NO_WIFI); return; }
  if (st.sleeping) { st.sleeping = 0; dispBrightness(false); }
  stopVoice();
  pendingText = text;
  busy = true;
  replyReady = false;
  overrideAnim = ANIM_THINKING; overrideUntil = millis() + 120000UL; curAnim = ANIM_THINKING; frameT = 0;
  subtitle[0] = 0;
  xTaskNotifyGive(brainHandle);
#endif
}

// aplica uma resposta do cerebro (do ESP32 ou do PC)
static void applyReply(const Reply& r) {
  listening = false;
  if (r.speech.length())
    Serial.printf("[%s] %s  (%s, %s, humor %+d)\n", petName, r.speech.c_str(),
                  r.anim < ANIM_COUNT ? ANIM_NAMES[r.anim] : "-", r.action.c_str(), r.mood);
  st.happy = clamp100(st.happy + r.mood);
  static const char* const acts[] = {"feed", "play", "clean", "sleep", "wake"};
  static const uint8_t ids[] = {ACT_FEED, ACT_PLAY, ACT_CLEAN, ACT_SLEEP, ACT_WAKE};
  for (uint8_t i = 0; i < 5; i++)
    if (r.action == acts[i]) {
      if (ids[i] != ACT_SLEEP || !st.sleeping) doAction(ids[i]);
      evCount = 0;  // o cerebro ja sabe dessa acao
    }
  stateDirty = true;
  if (r.speech.length()) say(r.speech.c_str(), st.sleeping ? ANIM_SLEEPING : (r.anim < ANIM_COUNT ? r.anim : ANIM_TALKING));
  else if (overrideAnim == ANIM_THINKING) { overrideAnim = 255; forcePick = true; }
}

static void serviceBrain() {
  if (!replyReady) return;
  replyReady = false;
  busy = false;
  if (!replyOk) { showProblem(MSG_BRAIN_ERR); return; }
  applyReply(lastReply);
}

// comando do cerebro do PC: {"speech","animation","action","mood"}
static void applyCommand(const String& js) {
  JsonDocument d;
  if (deserializeJson(d, js)) return;
  Reply r;
  r.speech = d["speech"] | "";
  const char* a = d["animation"] | "";
  r.anim = *a ? animIndex(a) : 255;
  r.action = d["action"] | "none";
  r.mood = constrain((int)(d["mood"] | 0), -10, 10);
  applyReply(r);
}

// o que chegou pelo ntfy: uma coisa por vez
static void serviceInbox() {
#if HAS_NTFY
  static bool lastUp = false;
  if (ntfyUp != lastUp) { lastUp = ntfyUp; drawNetStatus(); }
  String m;
  xSemaphoreTake(inboxLock, portMAX_DELAY);
  if (!inbox.empty() && (inbox.front()[0] != 'H' || !busy)) { m = inbox.front(); inbox.pop_front(); }
  xSemaphoreGive(inboxLock);
  if (!m.length()) return;
  char kind = m[0];
  String text = m.substring(1);
  if (kind == 'H') startConversation(text, "celular");
  else if (kind == 'T') { Serial.printf("[celular] %s\n", text.c_str()); showThinking(); }
  else if (kind == 'C') applyCommand(text);
#endif
}

// ------------------------------------------------------------- fala/escuta
static void startTalk() {
  if (!HAS_KEY && !HAS_NTFY) { showProblem(MSG_NO_KEY); return; }
  if (busy) { setSubtitle(MSG_BUSY, 2000); return; }
  if (st.sleeping) { st.sleeping = 0; dispBrightness(false); }
  stopVoice();
  listening = true;
  listenUntil = millis() + 30000UL;
  overrideAnim = ANIM_LISTENING; overrideUntil = listenUntil; curAnim = ANIM_LISTENING; frameT = 0;
  setSubtitle(HAS_NTFY ? MSG_LISTEN_PHONE : MSG_LISTEN, 30000);
  Serial.println(HAS_NTFY ? "[pet] Estou ouvindo! Fale no app ntfy do celular (ou digite aqui e aperte Enter)."
                          : "[pet] Estou ouvindo! Digite aqui no Serial Monitor e aperte Enter.");
}

static void stopListening() {
  listening = false;
  subtitle[0] = 0;
  overrideAnim = 255; forcePick = true;
}

// ------------------------------------------------------------- botoes
static void onShort(uint8_t i) {
  uint32_t now = millis();
  if (i == 0) {  // A: abre menu / proximo item
    if (!menuActive) menuActive = true; else menuSel = (menuSel + 1) % MENU_COUNT;
    menuUntil = now + 6000; statsScreen = false;
  } else if (i == 1) {  // B: escolhe
    if (!menuActive) { menuActive = true; menuUntil = now + 6000; return; }
    menuActive = false;
    if (menuSel == MENU_COUNT - 1) { if (listening) stopListening(); else startTalk(); }
    else {
      static const uint8_t acts[] = {ACT_FEED, ACT_PLAY, ACT_CLEAN, ACT_SLEEP, ACT_STATS};
      doAction(acts[menuSel]);
    }
  } else {  // C: voltar / parar fala / carinho
    if (listening) { stopListening(); return; }
    if (talking) { stopVoice(); return; }
    if (menuActive || statsScreen) { menuActive = false; statsScreen = false; return; }
    doAction(ACT_PET);
  }
}

static void pollButtons() {
  uint32_t now = millis();
  for (uint8_t i = 0; i < 3; i++) {
    Btn& b = btns[i];
    bool raw = !digitalRead(b.pin);
    if (raw != b.down && now - b.tchg > 25) {
      b.down = raw; b.tchg = now;
      if (raw) { b.t0 = now; b.held = false; }
      else if (!b.held) onShort(i);
    }
    if (b.down && !b.held && now - b.t0 > 450) {
      b.held = true;
      if (i == 2) startTalk();  // segurar C = falar
    }
  }
}

// ------------------------------------------------------------- serial
static void printHelp() {
  Serial.println();
  Serial.println("=== Tamagotchi (Wokwi) ===");
  Serial.println("Botoes: A = menu/proximo, B = escolher, C = voltar/carinho.");
  Serial.println("Teclado (clique no simulador antes): a, s, d.");
  Serial.println("Digite uma frase e aperte Enter para conversar com o PIXO (o Wokwi nao tem microfone).");
  Serial.println("Comandos: /comer /brincar /banho /dormir /acordar /carinho /status /rede /reset /ajuda");
  if (!HAS_KEY) Serial.println("(Sem chave: coloque API_KEY em secrets.h para conversar.)");
#if HAS_NTFY
  Serial.println("Celular: instale o app ntfy, assine o topico \"" NTFY_TOPIC "\" e mande a frase");
  Serial.println("         (use o microfone do teclado para ditar). Ou abra https://ntfy.sh/" NTFY_TOPIC);
  if (!HAS_KEY) Serial.println("Cerebro no PC: rode wokwi\\CEREBRO.bat no computador (abre http://localhost:8765).");
#endif
  Serial.println();
}

static void handleCommand(String cmd) {
  cmd.toLowerCase();
  if (cmd == "/comer") doAction(ACT_FEED);
  else if (cmd == "/brincar") doAction(ACT_PLAY);
  else if (cmd == "/banho") doAction(ACT_CLEAN);
  else if (cmd == "/dormir") { if (!st.sleeping) doAction(ACT_SLEEP); }
  else if (cmd == "/acordar") doAction(ACT_WAKE);
  else if (cmd == "/carinho") doAction(ACT_PET);
  else if (cmd == "/status") { doAction(ACT_STATS); }
#if HAS_KEY
  else if (cmd == "/rede") {
    if (busy || netTestPending) Serial.println("[rede] espere o cerebro terminar");
    else { Serial.println("[rede] testando HTTPS (leva um tempo no simulador)..."); netTestPending = true; xTaskNotifyGive(brainHandle); }
  }
#endif
  else if (cmd == "/reset") { resetStats(); history.clear(); playAnim(ANIM_HELLO, 3000); dispBrightness(false); printStats(); }
  else printHelp();
}

static void serviceSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      String line = serialLine;
      serialLine = "";
      line.trim();
      if (!line.length()) continue;
      if (line[0] == '/') handleCommand(line);
      else startConversation(line, "voce");
    } else if (serialLine.length() < 300) {
      serialLine += c;
    }
  }
}

// ------------------------------------------------------------- desenho da cena (igual ao Uno)
static int16_t cdiv8(int16_t v) { return v / 8; }  // trunca para zero, igual ao Python

static void drawStats() {
  char buf[16];
  drawText(0, 0, petName);
  snprintf(buf, sizeof(buf), "%lud%luh", (unsigned long)(st.ageMin / 1440), (unsigned long)((st.ageMin / 60) % 24));
  uint8_t n = textLen(buf);
  drawText(128 - n * 6, 0, buf);
  fillRect(0, 9, 128, 1);
  const char* labels[4] = {LBL_HUNGER, LBL_HAPPY, LBL_ENERGY, LBL_CLEAN};
  uint8_t vals[4] = {st.hunger, st.happy, st.energy, st.clean};
  for (uint8_t i = 0; i < 4; i++) {
    int16_t y = 12 + i * 11;
    blit(pgm_read_byte(&STATUS_ICONS[i]), 0, y);
    drawText(10, y, labels[i]);
    frameRect(58, y, 46, 7);
    fillRect(59, y + 1, vals[i] * 44 / 100, 5);
    snprintf(buf, sizeof(buf), "%u", vals[i]);
    drawText(128 - textLen(buf) * 6, y, buf);
  }
  blit(SPR_i_pc, 0, 58);
  drawText(9, 57, (wifiUp && HAS_KEY) ? "ok" : "--");
  if (st.sleeping) drawText(128 - textLen(LBL_SLEEPING) * 6, 57, LBL_SLEEPING);
}

static void effectComp(uint8_t ci, int16_t ox, int16_t oy) {
  const int8_t* c = COMP_DATA + ci * 7;
  uint8_t icon = (uint8_t)pgm_read_byte(c);
  uint8_t pat = pgm_read_byte(c + 1);
  int16_t x = (int8_t)pgm_read_byte(c + 2), y = (int8_t)pgm_read_byte(c + 3);
  int16_t a = (int8_t)pgm_read_byte(c + 4), b = (int8_t)pgm_read_byte(c + 5), cc = (int8_t)pgm_read_byte(c + 6);
  uint16_t t = frameT;
  switch (pat) {
    case PAT_STATIC: break;
    case PAT_BLINK: if (((t + a) >> 1) & 1) return; break;
    case PAT_RISE: y -= (int16_t)(((uint32_t)t * cc + b) % a); break;
    case PAT_FALL: y += (int16_t)(((uint32_t)t * cc + b) % a); break;
    case PAT_ORBIT: {
      uint8_t k = (t + cc) & 7;
      x += cdiv8((int8_t)pgm_read_byte(&ORBIT_X[k]) * a);
      y += cdiv8((int8_t)pgm_read_byte(&ORBIT_Y[k]) * b);
    } break;
    case PAT_SIDES: if (((t + cc) >> 1) & 1) { x += a; y += b; } break;
    case PAT_BOUNCE: y -= cdiv8((int8_t)pgm_read_byte(&BOUNCE_T[(t + b) & 7]) * a); break;
  }
  blit(icon, ox + x, oy + y);
}

static void drawScene() {
  drawBuf = fxBuf;  // textos, barra de status e efeitos
  if (statsScreen) { drawStats(); return; }
  if (menuActive) {
    const char* l = menuLabels[menuSel];
    drawText((128 - textLen(l) * 6) / 2, 0, l);
  } else {
    uint8_t vals[4] = {st.hunger, st.happy, st.energy, st.clean};
    for (uint8_t i = 0; i < 4; i++) {
      int16_t x = i * 32;
      blit(pgm_read_byte(&STATUS_ICONS[i]), x, 0);
      frameRect(x + 9, 1, 21, 5);
      fillRect(x + 10, 2, vals[i] * 19 / 100, 3);
    }
  }
  Anim an;
  memcpy_P(&an, &ANIMS[curAnim], sizeof(an));
  uint16_t t = frameT;
  uint16_t mofs = pgm_read_word(&MOTIONS[an.motion].ofs);
  uint8_t mlen = pgm_read_byte(&MOTIONS[an.motion].len);
  uint8_t mi = t % mlen;
  int16_t ox = BODY_X + (int8_t)pgm_read_byte(&MOTION_DATA[(mofs + mi) * 2]);
  int16_t oy = BODY_Y + (int8_t)pgm_read_byte(&MOTION_DATA[(mofs + mi) * 2 + 1]);
  drawBuf = pageBuf;  // o pet em si
  blit(SPR_body, ox, oy);

  uint8_t es = pgm_read_byte(&SEQ_DATA[an.eyeOfs + t % an.eyeLen]);
  EyeStyle e;
  memcpy_P(&e, &EYES[es], sizeof(e));
  if (an.eyeLen == 1 && e.blink && (frameNow % 3200) < 140) memcpy_P(&e, &EYES[EYE_CLOSED], sizeof(e));
  if (e.r == 255) blit(e.l, ox + EYE_PX + e.dx, oy + EYE_PY + e.dy);
  else {
    blit(e.l, ox + EYE_LX + e.dx, oy + EYE_LY + e.dy);
    blit(e.r, ox + EYE_RX + e.dx, oy + EYE_RY + e.dy);
  }
  uint8_t ms;
  if (talking && an.mouthLen == 1) ms = pgm_read_byte(&TALK_SEQ[(frameNow / 120) % 4]);
  else ms = pgm_read_byte(&SEQ_DATA[an.mouthOfs + t % an.mouthLen]);
  blit(ms, ox + MOUTH_X, oy + MOUTH_Y);

  drawBuf = fxBuf;
  uint16_t eofs = pgm_read_word(&EFFECTS[an.effect].ofs);
  uint8_t elen = pgm_read_byte(&EFFECTS[an.effect].len);
  for (uint8_t i = 0; i < elen; i++) effectComp(eofs + i, ox, oy);

  if (menuActive) {
    for (uint8_t i = 0; i < MENU_COUNT; i++) {
      int16_t x = 3 + i * 21;
      blit(pgm_read_byte(&MENU_ICONS[i]), x, 57);
      if (i == menuSel) frameRect(x - 2, 55, 11, 9);
    }
  } else if (subtitle[0]) {
    int16_t w = textLen(subtitle) * 6, x;
    if (w <= 124) x = (128 - w) / 2;
    else {
      int32_t travel = w - 120;
      int32_t dur = subDur ? subDur : (int32_t)textLen(subtitle) * 80;
      int32_t eff = dur - 800; if (eff < 500) eff = 500;
      int32_t el = frameNow - subStart; if (el > eff) el = eff;
      x = 4 - (int16_t)(travel * el / eff);
    }
    drawText(x, 57, subtitle);
  } else {
    drawText((128 - textLen(petName) * 6) / 2, 57, petName);
  }
}

static void serviceDisplay() {
  static uint32_t lastFrameStart = 0;
  if (millis() - lastFrameStart < 45) return;
  lastFrameStart = millis();
  frameNow = lastFrameStart;
  frameStyle = (statsScreen ? 1 : 0) | (menuActive ? 2 : 0) | (dim ? 4 : 0);
  for (uint8_t p = 0; p < 8; p++) {
    curPage = p;
    memset(pageBuf, 0, sizeof(pageBuf));
    memset(fxBuf, 0, sizeof(fxBuf));
    drawScene();
    dispSendPage(p);
  }
  styleKey = frameStyle;
}

// ------------------------------------------------------------- logica por tempo
static void petTick() {
  uint32_t now = millis();
  Anim an;
  memcpy_P(&an, &ANIMS[curAnim], sizeof(an));
  if (now - lastFrame >= (uint32_t)an.speed10 * 10) { lastFrame = now; frameT++; }
  if (now - lastDecay >= (uint32_t)DECAY_SECONDS * 1000UL) { lastDecay = now; decay(); }
  if (now - lastAge >= 60000UL) { lastAge = now; st.ageMin++; }
  if (now - lastSave >= 300000UL) saveStats();
  if (overrideAnim != 255 && (int32_t)(now - overrideUntil) > 0) {
    overrideAnim = 255; forcePick = true;
  }
  if (overrideAnim == 255 && (forcePick || now - lastPick > 8000UL)) {
    lastPick = now; forcePick = false; autoAnim = pickMood();
  }
  if (menuActive && (int32_t)(now - menuUntil) > 0) menuActive = false;
  if (statsScreen && (int32_t)(now - statsUntil) > 0) statsScreen = false;
  if (listening && (int32_t)(now - listenUntil) > 0) stopListening();
  if (subtitle[0] && !listening) {
    uint32_t dur = subDur ? subDur : (uint32_t)textLen(subtitle) * 80;
    if (now - subStart > dur + 1500) subtitle[0] = 0;
  }
  uint8_t want = overrideAnim != 255 ? overrideAnim : autoAnim;
  if (want != curAnim) { curAnim = want; frameT = 0; }
}

static void serviceWifi() {
  bool up = WiFi.status() == WL_CONNECTED;
  if (up == wifiUp) return;
  wifiUp = up;
  drawNetStatus();
  if (up) {
    Serial.printf("[wifi] conectado, IP %s\n", WiFi.localIP().toString().c_str());
    if (!busy && !talking && !listening) setSubtitle(MSG_WIFI_OK, 2000);
  } else {
    Serial.println("[wifi] desconectado, tentando de novo...");
  }
}

// ------------------------------------------------------------- setup/loop
void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < 3; i++) pinMode(btns[i].pin, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  randomSeed(esp_random());
  EEPROM.begin(64);
  EEPROM.get(0, st);
  if (st.magic != STATS_MAGIC) resetStats();
  dispInit();
  dispBrightness(st.sleeping);
  printHelp();
  printStats();
  // As tarefas de rede ficam no nucleo 0 com prioridade minima (0): o HTTPS no
  // simulador gasta varios segundos de CPU e, com prioridade maior, a tarefa
  // ociosa nao rodava, o watchdog achava que travou e reiniciava o ESP32.
#if HAS_KEY
  xTaskCreatePinnedToCore(brainTask, "brain", 32768, nullptr, tskIDLE_PRIORITY, &brainHandle, 0);
#endif
#if HAS_NTFY
  inboxLock = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(ntfyTask, "ntfy", 12288, nullptr, tskIDLE_PRIORITY, nullptr, 0);
  xTaskCreatePinnedToCore(ntfyPubTask, "ntfypub", 10240, nullptr, tskIDLE_PRIORITY, nullptr, 0);
#endif
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);  // canal 6 conecta mais rapido no Wokwi
}

void loop() {
  serviceSerial();
  serviceWifi();
  serviceBrain();
  serviceInbox();
  pollButtons();
  petTick();
  serviceVoice();
  serviceDisplay();
  delay(1);
}
