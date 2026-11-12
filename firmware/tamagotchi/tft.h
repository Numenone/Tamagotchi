// Driver minimo para a TFT IPS 0.96" 80x160 (ST7735S) em SPI, deitada (160x80).
// A cena de 128x64 fica no meio da tela com uma moldura. Cada pagina de 8 linhas
// e convertida para cor na hora e enviada direto, sem precisar de framebuffer.
#pragma once
#if DISPLAY_TFT
#include <SPI.h>

#define TFT_W 160
#define TFT_H 80
#define SCENE_X 16
#define SCENE_Y 8

static inline uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return ((uint16_t)(r & 0xF8) << 8) | ((uint16_t)(g & 0xFC) << 3) | (b >> 3);
}

static const SPISettings tftSpi(8000000, MSBFIRST, SPI_MODE0);

static void tftCmd(uint8_t c) {
  digitalWrite(TFT_PIN_DC, LOW);
  SPI.transfer(c);
  digitalWrite(TFT_PIN_DC, HIGH);
}

static void tftCmdData(uint8_t c, const uint8_t* d, uint8_t n) {
  SPI.beginTransaction(tftSpi);
  digitalWrite(TFT_PIN_CS, LOW);
  tftCmd(c);
  for (uint8_t i = 0; i < n; i++) SPI.transfer(d[i]);
  digitalWrite(TFT_PIN_CS, HIGH);
  SPI.endTransaction();
}

// precisa estar dentro de uma transacao SPI com CS baixo
static void tftWindow(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1) {
  tftCmd(0x2A);
  SPI.transfer(0); SPI.transfer(x0 + TFT_XOFS); SPI.transfer(0); SPI.transfer(x1 + TFT_XOFS);
  tftCmd(0x2B);
  SPI.transfer(0); SPI.transfer(y0 + TFT_YOFS); SPI.transfer(0); SPI.transfer(y1 + TFT_YOFS);
  tftCmd(0x2C);
}

static void tftFill(uint8_t x, uint8_t y, uint8_t w, uint8_t h, uint16_t c) {
  SPI.beginTransaction(tftSpi);
  digitalWrite(TFT_PIN_CS, LOW);
  tftWindow(x, y, x + w - 1, y + h - 1);
  for (uint16_t i = (uint16_t)w * h; i; i--) { SPI.transfer(c >> 8); SPI.transfer(c & 0xFF); }
  digitalWrite(TFT_PIN_CS, HIGH);
  SPI.endTransaction();
}

#define COL_BG rgb(4, 6, 16)
#define COL_FRAME rgb(70, 50, 120)
static uint16_t colPet;
static const uint16_t PET_COLORS[] = {rgb(125, 235, 255), rgb(130, 255, 140), rgb(255, 130, 200),
                                      rgb(255, 255, 255), rgb(255, 215, 90)};

static void tftFrame() {
  tftFill(0, 0, TFT_W, TFT_H, COL_BG);
  tftFill(SCENE_X - 3, SCENE_Y - 3, 128 + 6, 1, COL_FRAME);
  tftFill(SCENE_X - 3, SCENE_Y + 64 + 2, 128 + 6, 1, COL_FRAME);
  tftFill(SCENE_X - 3, SCENE_Y - 3, 1, 64 + 6, COL_FRAME);
  tftFill(SCENE_X + 128 + 2, SCENE_Y - 3, 1, 64 + 6, COL_FRAME);
}

static void dispBrightness(uint8_t v) {
#if TFT_PIN_BLK >= 0
  analogWrite(TFT_PIN_BLK, v);
#endif
}

static void dispInit() {
  pinMode(TFT_PIN_CS, OUTPUT);
  pinMode(TFT_PIN_DC, OUTPUT);
  digitalWrite(TFT_PIN_CS, HIGH);
  digitalWrite(TFT_PIN_DC, HIGH);
  SPI.begin();
#if TFT_PIN_RST >= 0
  pinMode(TFT_PIN_RST, OUTPUT);
  digitalWrite(TFT_PIN_RST, HIGH); delay(5);
  digitalWrite(TFT_PIN_RST, LOW); delay(20);
  digitalWrite(TFT_PIN_RST, HIGH); delay(150);
#endif
  tftCmdData(0x01, 0, 0); delay(150);  // reset por software
  tftCmdData(0x11, 0, 0); delay(150);  // sai do modo sono
  static const uint8_t frm[] PROGMEM = {0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D};
  uint8_t b[16];
  memcpy_P(b, frm, 6);
  tftCmdData(0xB1, b, 3);
  tftCmdData(0xB2, b, 3);
  tftCmdData(0xB3, b, 6);
  b[0] = 0x07; tftCmdData(0xB4, b, 1);
  b[0] = 0xA2; b[1] = 0x02; b[2] = 0x84; tftCmdData(0xC0, b, 3);
  b[0] = 0xC5; tftCmdData(0xC1, b, 1);
  b[0] = 0x0A; b[1] = 0x00; tftCmdData(0xC2, b, 2);
  b[0] = 0x8A; b[1] = 0x2A; tftCmdData(0xC3, b, 2);
  b[0] = 0x8A; b[1] = 0xEE; tftCmdData(0xC4, b, 2);
  b[0] = 0x0E; tftCmdData(0xC5, b, 1);
  tftCmdData(TFT_INVERT ? 0x21 : 0x20, 0, 0);
  // deitada: MY|MV (ou MX|MV se girada) + ordem de cor
  b[0] = (TFT_FLIP ? 0x60 : 0xA0) | (TFT_BGR ? 0x08 : 0x00);
  tftCmdData(0x36, b, 1);
  b[0] = 0x05; tftCmdData(0x3A, b, 1);  // 16 bits por pixel
  static const uint8_t gp[] PROGMEM = {0x02, 0x1C, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2D,
                                       0x29, 0x25, 0x2B, 0x39, 0x00, 0x01, 0x03, 0x10};
  static const uint8_t gn[] PROGMEM = {0x03, 0x1D, 0x07, 0x06, 0x2E, 0x2C, 0x29, 0x2D,
                                       0x2E, 0x2E, 0x37, 0x3F, 0x00, 0x00, 0x02, 0x10};
  memcpy_P(b, gp, 16); tftCmdData(0xE0, b, 16);
  memcpy_P(b, gn, 16); tftCmdData(0xE1, b, 16);
  tftCmdData(0x13, 0, 0); delay(10);
  tftCmdData(0x29, 0, 0); delay(50);
  colPet = PET_COLORS[TFT_PET_COLOR % 5];
  tftFrame();
#if TFT_PIN_BLK >= 0
  pinMode(TFT_PIN_BLK, OUTPUT);
#endif
  dispBrightness(OLED_CONTRAST);
}

extern bool statsScreenActive();
extern bool menuIsActive();

// cor da camada de efeitos/textos conforme a regiao da cena
static uint16_t fxColor(uint8_t x, uint8_t y) {
  static const uint16_t bar[4] = {rgb(255, 159, 67), rgb(255, 111, 181), rgb(255, 209, 102), rgb(103, 232, 249)};
  if (statsScreenActive()) {
    if (y >= 12 && y < 56 && x < 8) return bar[(y - 12) / 11];
    return rgb(240, 236, 255);
  }
  if (y < 8) return menuIsActive() ? rgb(240, 236, 255) : bar[x >> 5];
  if (y >= 55) return rgb(255, 230, 150);
  return rgb(255, 120, 190);
}

static void dispSendPage(uint8_t p) {
  uint16_t bg = COL_BG;
  SPI.beginTransaction(tftSpi);
  digitalWrite(TFT_PIN_CS, LOW);
  tftWindow(SCENE_X, SCENE_Y + p * 8, SCENE_X + 127, SCENE_Y + p * 8 + 7);
  for (uint8_t r = 0; r < 8; r++) {
    uint8_t m = 1 << r;
    uint8_t y = p * 8 + r;
    for (uint8_t x = 0; x < 128; x++) {
      uint16_t c = (pageBuf[x] & m) ? colPet : ((fxBuf[x] & m) ? fxColor(x, y) : bg);
      SPI.transfer(c >> 8);
      SPI.transfer(c & 0xFF);
    }
  }
  digitalWrite(TFT_PIN_CS, HIGH);
  SPI.endTransaction();
}

// teste de tela: moldura branca nas bordas + faixas vermelha, verde e azul
static void dispTestPattern() {
  tftFill(0, 0, TFT_W, TFT_H, 0);
  tftFill(0, 0, TFT_W, 1, 0xFFFF);
  tftFill(0, TFT_H - 1, TFT_W, 1, 0xFFFF);
  tftFill(0, 0, 1, TFT_H, 0xFFFF);
  tftFill(TFT_W - 1, 0, 1, TFT_H, 0xFFFF);
  tftFill(10, 20, 40, 40, rgb(255, 0, 0));
  tftFill(60, 20, 40, 40, rgb(0, 255, 0));
  tftFill(110, 20, 40, 40, rgb(0, 0, 255));
}
#endif
