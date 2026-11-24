// Desenho por paginas de 8 linhas (igual ao firmware do Uno, firmware/tamagotchi/oled.h).
#pragma once

static uint8_t pageBuf[128];  // camada do pet (corpo, olhos, boca)
static uint8_t fxBuf[128];    // camada de efeitos, textos e barra de status
static uint8_t* drawBuf = pageBuf;
static uint8_t curPage = 0;

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
