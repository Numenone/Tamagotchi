// Desenho por paginas + driver minimo para OLED 128x64 I2C (SSD1306 ou SH1106).
// A TFT colorida ST7735 fica em tft.h.
// Desenhamos uma pagina de 8 linhas por vez em um buffer de 128 bytes,
// o que economiza RAM (o Uno so tem 2 KB) e deixa o loop livre para o audio.
#pragma once
#if !DISPLAY_TFT
#include <Wire.h>
#endif

static uint8_t pageBuf[128];  // camada do pet (corpo, olhos, boca)
static uint8_t fxBuf[128];    // camada de efeitos, textos e barra de status
static uint8_t* drawBuf = pageBuf;
static uint8_t curPage = 0;

#if !DISPLAY_TFT
#if OLED_SH1106
#define OLED_COL_OFS 2
#else
#define OLED_COL_OFS 0
#endif

static void oledCmds(const uint8_t* cmds, uint8_t n) {
  Wire.beginTransmission(OLED_I2C_ADDR);
  Wire.write((uint8_t)0x00);
  for (uint8_t i = 0; i < n; i++) Wire.write(cmds[i]);
  Wire.endTransmission();
}

static void oledCmd1(uint8_t c) { oledCmds(&c, 1); }

static void oledContrast(uint8_t v) {
  uint8_t c[2] = {0x81, v};
  oledCmds(c, 2);
}

static void oledInit() {
  Wire.begin();
  Wire.setClock(400000);
  delay(50);
  const uint8_t init1[] = {0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40};
  oledCmds(init1, sizeof(init1));
#if OLED_SH1106
  const uint8_t pump[] = {0xAD, 0x8B};
#else
  const uint8_t pump[] = {0x8D, 0x14, 0x20, 0x02};  // charge pump + modo pagina
#endif
  oledCmds(pump, sizeof(pump));
#if OLED_FLIP
  const uint8_t orient[] = {0xA0, 0xC0};
#else
  const uint8_t orient[] = {0xA1, 0xC8};
#endif
  oledCmds(orient, sizeof(orient));
  const uint8_t init2[] = {0xDA, 0x12, 0x81, OLED_CONTRAST, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
  oledCmds(init2, sizeof(init2));
}

static void oledSendPage(uint8_t p) {
  uint8_t c[3] = {(uint8_t)(0xB0 | p), (uint8_t)(OLED_COL_OFS & 0x0F), (uint8_t)(0x10 | (OLED_COL_OFS >> 4))};
  oledCmds(c, 3);
  for (uint8_t i = 0; i < 128; i += 16) {
    Wire.beginTransmission(OLED_I2C_ADDR);
    Wire.write((uint8_t)0x40);
    Wire.write(pageBuf + i, 16);
    Wire.endTransmission();
  }
}

static void dispInit() { oledInit(); }
static void dispBrightness(uint8_t v) { oledContrast(v); }
static void dispSendPage(uint8_t p) {
  for (uint8_t i = 0; i < 128; i++) pageBuf[i] |= fxBuf[i];  // OLED e monocromatico
  oledSendPage(p);
}
static void dispTestPattern() {}
#endif

// ---------------------------------------------------------------- desenho
static inline void px(int16_t x, int16_t y) {
  if ((uint16_t)x >= 128) return;
  int16_t r = y - (int16_t)(curPage << 3);
  if (r < 0 || r > 7) return;
  drawBuf[x] |= (uint8_t)(1 << r);
}

static void blit(uint8_t id, int16_t x, int16_t y) {
  uint8_t w = pgm_read_byte(&SPR_INFO[id].w);
  uint8_t h = pgm_read_byte(&SPR_INFO[id].h);
  uint16_t ofs = pgm_read_word(&SPR_INFO[id].ofs);
  int16_t py0 = (int16_t)curPage << 3;
  int16_t r0 = py0 - y;
  if (r0 < 0) r0 = 0;
  int16_t r1 = py0 + 8 - y;
  if (r1 > h) r1 = h;
  if (r0 >= r1) return;
  uint8_t bpr = (w + 7) >> 3;
  for (int16_t r = r0; r < r1; r++) {
    uint8_t bit = (uint8_t)(1 << (y + r - py0));
    const uint8_t* p = SPR_BITS + ofs + r * bpr;
    uint8_t b = 0;
    for (uint8_t c = 0; c < w; c++) {
      if ((c & 7) == 0) b = pgm_read_byte(p + (c >> 3));
      if (b & 0x80) {
        int16_t xx = x + c;
        if ((uint16_t)xx < 128) drawBuf[xx] |= bit;
      }
      b <<= 1;
    }
  }
}

static void fillRect(int16_t x, int16_t y, int16_t w, int16_t h) {
  int16_t py0 = (int16_t)curPage << 3;
  if (y + h <= py0 || y >= py0 + 8) return;
  for (int16_t yy = y; yy < y + h; yy++)
    for (int16_t xx = x; xx < x + w; xx++) px(xx, yy);
}

static void frameRect(int16_t x, int16_t y, int16_t w, int16_t h) {
  fillRect(x, y, w, 1);
  fillRect(x, y + h - 1, w, 1);
  fillRect(x, y, 1, h);
  fillRect(x + w - 1, y, 1, h);
}

static void drawChar(int16_t x, int16_t y, char ch) {
  uint8_t c = (uint8_t)ch;
  if (c < 32 || c > 126) c = '?';
  const uint8_t* g = FONT5X7 + (c - 32) * 5;
  for (uint8_t col = 0; col < 5; col++) {
    uint8_t bits = pgm_read_byte(g + col);
    for (uint8_t r = 0; r < 7; r++)
      if (bits & (1 << r)) px(x + col, y + r);
  }
}

static void drawText(int16_t x, int16_t y, const char* s) {
  int16_t py0 = (int16_t)curPage << 3;
  if (y + 7 <= py0 || y >= py0 + 8) return;
  for (; *s; s++, x += 6) {
    if (x <= -6) continue;
    if (x >= 128) break;
    drawChar(x, y, *s);
  }
}

static uint8_t textLen(const char* s) {
  uint8_t n = 0;
  while (s[n]) n++;
  return n;
}
