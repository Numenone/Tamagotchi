// =====================================================================
//  Tamagotchi + Claude  |  Arduino Uno + Shield VS1053 (Geeetech) + OLED ou TFT
//  Este arquivo e gravado automaticamente pelo TAMAGOTCHI.bat.
//  config.h e anim_data.h sao gerados pelo Studio a partir das configs.
// =====================================================================
#include <Arduino.h>
#include <EEPROM.h>
#include "config.h"
#include "anim_data.h"
#include "oled.h"
#include "tft.h"
#include "vs1053.h"

#define PROTO_VERSION 1
#define FW_VERSION 1
#ifndef FW_HASH
#define FW_HASH 0UL
#endif
#ifndef SERIAL_RX_BUFFER_SIZE
#define SERIAL_RX_BUFFER_SIZE 64
#endif

// ------------------------------------------------------------- estado
struct Stats {
  uint8_t magic, hunger, happy, energy, clean, sleeping;
  uint32_t ageMin;
};
static Stats st;
#define STATS_MAGIC 0x5B

static uint8_t curAnim = ANIM_HELLO, autoAnim = ANIM_IDLE, overrideAnim = ANIM_HELLO;
static uint32_t overrideUntil = 2500;
static uint16_t frameT = 0;
static uint32_t lastFrame, lastDecay, lastAge, lastPick, lastSave, lastStatsTx, lastPc;
static bool forcePick = true;
static bool menuActive = false, statsScreen = false, talking = false, recording = false, pcLink = false;
static uint8_t menuSel = 0;
static uint32_t menuUntil, statsUntil, recStart;
static char subtitle[121];
static uint32_t subStart;
static uint16_t subDur;
static char petName[13] = PET_NAME;
static uint32_t frameNow;
static const char* const menuLabels[] = {MENU_LABELS};
static uint32_t testUntil = 0;
bool statsScreenActive() { return statsScreen; }
bool menuIsActive() { return menuActive; }

// ------------------------------------------------------------- protocolo
// quadro: 0x7E tipo tamanho dados... checksum(soma de tipo+tamanho+dados)
static void sendFrame(uint8_t type, const uint8_t* d, uint8_t n) {
  uint8_t sum = type + n;
  Serial.write((uint8_t)0x7E);
  Serial.write(type);
  Serial.write(n);
  for (uint8_t i = 0; i < n; i++) { Serial.write(d[i]); sum += d[i]; }
  Serial.write(sum);
}

static void sendHello() {
  uint32_t h = FW_HASH;
  uint8_t d[14] = {PROTO_VERSION, FW_VERSION, vsVersion, (uint8_t)(SERIAL_RX_BUFFER_SIZE / 4),
                   st.hunger, st.happy, st.energy, st.clean, st.sleeping, curAnim,
                   (uint8_t)h, (uint8_t)(h >> 8), (uint8_t)(h >> 16), (uint8_t)(h >> 24)};
  sendFrame('h', d, sizeof(d));
}

static void sendStats() {
  uint32_t a = st.ageMin;
  uint8_t d[10] = {st.hunger, st.happy, st.energy, st.clean, st.sleeping, curAnim,
                   (uint8_t)a, (uint8_t)(a >> 8), (uint8_t)(a >> 16), (uint8_t)(a >> 24)};
  sendFrame('s', d, sizeof(d));
  lastStatsTx = millis();
}

static void sendEvent(uint8_t act) { sendFrame('b', &act, 1); sendStats(); }

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

static void saveStats() { EEPROM.put(0, st); lastSave = millis(); }

static void resetStats() {
  st.magic = STATS_MAGIC; st.hunger = 80; st.happy = 80; st.energy = 80; st.clean = 80;
  st.sleeping = 0; st.ageMin = 0;
  saveStats();
}

static void decay() {
  if (st.sleeping) {
    st.energy = clamp100(st.energy + 4);
    st.hunger = clamp100(st.hunger - 1);
    if (st.energy >= 100) { st.sleeping = 0; playAnim(ANIM_YAWN, 2500); }
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
  dispBrightness(st.sleeping ? 8 : OLED_CONTRAST);
  sendEvent(act);
}

// ------------------------------------------------------------- fala/escuta
static void startTalk() {
  if (recording) return;
  if (!pcLink) { playAnim(ANIM_CONFUSED, 2500); setSubtitle(LBL_NOPC, 0); return; }
  if (st.sleeping) { st.sleeping = 0; dispBrightness(OLED_CONTRAST); }
  if (talking) { vsAbort(); talking = false; sendFrame('x', 0, 0); }
  vsStartRecord();
  recording = true;
  recStart = millis();
  sendFrame('r', 0, 0);
  overrideAnim = ANIM_LISTENING; overrideUntil = 0xFFFFFFFF; curAnim = ANIM_LISTENING; frameT = 0;
}

static void stopTalk() {
  if (!recording) return;
  vsStopRecord();
  recording = false;
  sendFrame('q', 0, 0);
  playAnim(ANIM_THINKING, 20000);
}

// ------------------------------------------------------------- botoes
struct Btn { uint8_t pin; bool down; bool held; uint32_t t0, tchg; };
static Btn btns[3] = {{PIN_BTN_A, 0, 0, 0, 0}, {PIN_BTN_B, 0, 0, 0, 0}, {PIN_BTN_C, 0, 0, 0, 0}};

static void onShort(uint8_t i) {
  uint32_t now = millis();
  if (i == 0) {  // A: abre menu / proximo item
    if (!menuActive) menuActive = true; else menuSel = (menuSel + 1) % MENU_COUNT;
    menuUntil = now + 6000; statsScreen = false;
  } else if (i == 1) {  // B: escolhe
    if (!menuActive) { menuActive = true; menuUntil = now + 6000; return; }
    menuActive = false;
    if (menuSel == MENU_COUNT - 1) { if (recording) stopTalk(); else startTalk(); }
    else {
      static const uint8_t acts[] = {ACT_FEED, ACT_PLAY, ACT_CLEAN, ACT_SLEEP, ACT_STATS};
      doAction(acts[menuSel]);
    }
  } else {  // C: voltar / parar fala / carinho
    if (recording) { stopTalk(); return; }
    if (talking) { vsAbort(); talking = false; sendFrame('x', 0, 0); return; }
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
      else if (i == 2) stopTalk();  // soltou o C segurado
    }
    if (b.down && !b.held && now - b.t0 > 450) {
      b.held = true;
      if (i == 2) startTalk();  // segurar C = falar
    }
  }
}

// ------------------------------------------------------------- serial
static uint8_t renderPage = 255;
static uint32_t lastFrameStart = 0;
static uint8_t rxState = 0, rxType, rxLen, rxPos, rxSum;
static uint8_t rxBuf[124];
static bool pendingAudio = false;

static void handleFrame() {
  lastPc = millis();
  if (!pcLink) { pcLink = true; }
  switch (rxType) {
    case 'H': sendHello(); break;
    case 'A':
      if (rxLen >= 1) {
        uint8_t sec = rxLen >= 2 ? rxBuf[1] : 5;
        if (!recording) playAnim(rxBuf[0], sec == 255 ? 600000UL : (uint32_t)sec * 1000UL);
      }
      break;
    case 'T':
      if (rxLen >= 2) {
        uint16_t ds = rxBuf[0] | ((uint16_t)rxBuf[1] << 8);
        rxBuf[rxLen < sizeof(rxBuf) ? rxLen : sizeof(rxBuf) - 1] = 0;
        setSubtitle((const char*)rxBuf + 2, ds * 100);
      }
      break;
    case 'P':
      if (recording) { vsStopRecord(); recording = false; }
      vsStartPlay(); talking = true;
      break;
    case 'D':
      if (vsState == VS_PLAY) {
        if (vsReady()) vsData(rxBuf, rxLen); else { pendingAudio = true; return; }
      }
      { uint8_t one = 1; sendFrame('k', &one, 1); }
      break;
    case 'E': vsEndPlay(); break;
    case 'V': if (rxLen) vsSetVolume(rxBuf[0]); break;
    case 'N':
      if (rxLen) {
        uint8_t n = rxLen > 12 ? 12 : rxLen;
        memcpy(petName, rxBuf, n); petName[n] = 0;
      }
      break;
    case 'X': if (rxLen) doAction(rxBuf[0]); break;
    case 'R': if (rxLen) { if (rxBuf[0]) startTalk(); else stopTalk(); } break;
    case 'S':
      if (rxLen >= 4) {
        st.hunger = clamp100(rxBuf[0]); st.happy = clamp100(rxBuf[1]);
        st.energy = clamp100(rxBuf[2]); st.clean = clamp100(rxBuf[3]);
        saveStats(); sendStats();
      }
      break;
    case 'Z': resetStats(); playAnim(ANIM_HELLO, 3000); sendStats(); break;
    case 'G': renderPage = 255; dispTestPattern(); testUntil = millis() + 6000; break;
  }
}

static void serviceSerial() {
  if (pendingAudio) {
    if (!vsReady()) return;
    vsData(rxBuf, rxLen);
    pendingAudio = false;
    uint8_t one = 1;
    sendFrame('k', &one, 1);
  }
  uint8_t budget = 80;
  while (Serial.available() && budget--) {
    uint8_t c = Serial.read();
    switch (rxState) {
      case 0: if (c == 0x7E) rxState = 1; break;
      case 1: rxType = c; rxSum = c; rxState = 2; break;
      case 2:
        rxLen = c; rxSum += c; rxPos = 0;
        if (rxLen >= sizeof(rxBuf)) rxState = 0; else rxState = rxLen ? 3 : 4;
        break;
      case 3: rxBuf[rxPos++] = c; rxSum += c; if (rxPos >= rxLen) rxState = 4; break;
      case 4:
        rxState = 0;
        if (c == rxSum) { handleFrame(); if (pendingAudio) return; }
        break;
    }
  }
}

// ------------------------------------------------------------- desenho
static int16_t cdiv8(int16_t v) { return v / 8; }  // trunca para zero, igual ao Python

static void utoa2(uint32_t v, char* out) { ultoa(v, out, 10); }

static void drawStats() {
  char buf[12];
  drawText(0, 0, petName);
  utoa2(st.ageMin / 1440, buf);
  uint8_t n = textLen(buf);
  buf[n++] = 'd';
  utoa2((st.ageMin / 60) % 24, buf + n);
  n = textLen(buf);
  buf[n++] = 'h'; buf[n] = 0;
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
    utoa2(vals[i], buf);
    drawText(128 - textLen(buf) * 6, y, buf);
  }
  blit(SPR_i_pc, 0, 58);
  drawText(9, 57, pcLink ? "ok" : "--");
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
  if (testUntil) {
    if ((int32_t)(millis() - testUntil) < 0) return;
    testUntil = 0;
#if DISPLAY_TFT
    tftFrame();
#endif
  }
  if (renderPage == 255) {
    if (millis() - lastFrameStart < 45) return;
    lastFrameStart = millis();
    frameNow = lastFrameStart;
    renderPage = 0;
  }
  curPage = renderPage;
  memset(pageBuf, 0, sizeof(pageBuf));
  memset(fxBuf, 0, sizeof(fxBuf));
  drawScene();
  dispSendPage(renderPage);
  if (++renderPage >= 8) renderPage = 255;
}

// ------------------------------------------------------------- logica por tempo
static void petTick() {
  uint32_t now = millis();
  Anim an;
  memcpy_P(&an, &ANIMS[curAnim], sizeof(an));
  if (now - lastFrame >= (uint32_t)an.speed10 * 10) { lastFrame = now; frameT++; }
  if (now - lastDecay >= (uint32_t)DECAY_SECONDS * 1000UL) { lastDecay = now; decay(); sendStats(); }
  if (now - lastAge >= 60000UL) { lastAge = now; st.ageMin++; }
  if (now - lastSave >= 300000UL) saveStats();
  if (overrideAnim != 255 && !recording && (int32_t)(now - overrideUntil) > 0) {
    overrideAnim = 255; forcePick = true;
  }
  if (overrideAnim == 255 && (forcePick || now - lastPick > 8000UL)) {
    lastPick = now; forcePick = false; autoAnim = pickMood();
  }
  if (menuActive && (int32_t)(now - menuUntil) > 0) menuActive = false;
  if (statsScreen && (int32_t)(now - statsUntil) > 0) statsScreen = false;
  if (subtitle[0]) {
    uint32_t dur = subDur ? subDur : (uint32_t)textLen(subtitle) * 80;
    if (now - subStart > dur + 1500) subtitle[0] = 0;
  }
  uint8_t want = overrideAnim != 255 ? overrideAnim : autoAnim;
  if (want != curAnim) { curAnim = want; frameT = 0; }
  if (recording && now - recStart > 15000UL) stopTalk();  // limite de 15 s
  if (pcLink && now - lastPc > 10000UL) pcLink = false;
  if (now - lastStatsTx > 5000UL) sendStats();
}

// ------------------------------------------------------------- setup/loop
void setup() {
  Serial.begin(SERIAL_BAUD);
  for (uint8_t i = 0; i < 3; i++) pinMode(btns[i].pin, INPUT_PULLUP);
  randomSeed(analogRead(A3) ^ micros());
  EEPROM.get(0, st);
  if (st.magic != STATS_MAGIC) resetStats();
  // todos os CS do barramento SPI desligados antes de iniciar a tela
  pinMode(VS_PIN_XCS, OUTPUT); digitalWrite(VS_PIN_XCS, HIGH);
  pinMode(VS_PIN_XDCS, OUTPUT); digitalWrite(VS_PIN_XDCS, HIGH);
  pinMode(SD_PIN_CS, OUTPUT); digitalWrite(SD_PIN_CS, HIGH);
  dispInit();
  if (st.sleeping) dispBrightness(8);
  vsInit();
  sendHello();
}

void loop() {
  serviceSerial();
  if (vsState == VS_REC) {
    uint8_t mic[32];
    if (vsReadMic(mic)) sendFrame('m', mic, 32);
  }
  if (vsServiceFill()) { talking = false; sendFrame('e', 0, 0); }
  pollButtons();
  petTick();
  serviceDisplay();
}
