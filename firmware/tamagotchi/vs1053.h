// Driver minimo do VS1053 (shield Geeetech): toca MP3/WAV vindo do PC pela
// serial e grava o microfone em PCM 8 kHz (convertido para u-law, 8 KB/s).
#pragma once
#include <SPI.h>

#define SCI_MODE 0x00
#define SCI_STATUS 0x01
#define SCI_CLOCKF 0x03
#define SCI_WRAM 0x06
#define SCI_WRAMADDR 0x07
#define SCI_HDAT0 0x08
#define SCI_HDAT1 0x09
#define SCI_VOL 0x0B
#define SCI_AICTRL0 0x0C
#define SCI_AICTRL1 0x0D
#define SCI_AICTRL2 0x0E
#define SCI_AICTRL3 0x0F

#define SM_RESET 0x0004
#define SM_CANCEL 0x0008
#define SM_SDINEW 0x0800
#define SM_ADPCM 0x1000
#define SM_LINE1 0x4000

enum { VS_IDLE = 0, VS_PLAY, VS_FILL, VS_REC, VS_NONE };
static uint8_t vsState = VS_NONE;
static uint16_t vsFillLeft = 0;
static uint8_t vsEndFill = 0;
static uint8_t vsVersion = 0;
static uint8_t vsVolume = VS_VOLUME;
static uint32_t vsSpeed = 1000000;

static inline bool vsReady() { return digitalRead(VS_PIN_DREQ); }

static void vsWaitDreq(uint16_t ms) {
  uint32_t t0 = millis();
  while (!vsReady() && (uint16_t)(millis() - t0) < ms) {}
}

static void sciWrite(uint8_t addr, uint16_t v) {
  vsWaitDreq(50);
  SPI.beginTransaction(SPISettings(vsSpeed, MSBFIRST, SPI_MODE0));
  digitalWrite(VS_PIN_XCS, LOW);
  SPI.transfer(0x02);
  SPI.transfer(addr);
  SPI.transfer(v >> 8);
  SPI.transfer(v & 0xFF);
  digitalWrite(VS_PIN_XCS, HIGH);
  SPI.endTransaction();
}

static uint16_t sciRead(uint8_t addr) {
  SPI.beginTransaction(SPISettings(vsSpeed, MSBFIRST, SPI_MODE0));
  digitalWrite(VS_PIN_XCS, LOW);
  SPI.transfer(0x03);
  SPI.transfer(addr);
  uint16_t v = (uint16_t)SPI.transfer(0xFF) << 8;
  v |= SPI.transfer(0xFF);
  digitalWrite(VS_PIN_XCS, HIGH);
  SPI.endTransaction();
  return v;
}

static void sdiWrite(const uint8_t* d, uint8_t n) {
  SPI.beginTransaction(SPISettings(vsSpeed, MSBFIRST, SPI_MODE0));
  digitalWrite(VS_PIN_XDCS, LOW);
  for (uint8_t i = 0; i < n; i++) SPI.transfer(d[i]);
  digitalWrite(VS_PIN_XDCS, HIGH);
  SPI.endTransaction();
}

static void sdiFill(uint8_t b, uint8_t n) {
  SPI.beginTransaction(SPISettings(vsSpeed, MSBFIRST, SPI_MODE0));
  digitalWrite(VS_PIN_XDCS, LOW);
  for (uint8_t i = 0; i < n; i++) SPI.transfer(b);
  digitalWrite(VS_PIN_XDCS, HIGH);
  SPI.endTransaction();
}

static void vsSetVolume(uint8_t att) {
  vsVolume = att;
  sciWrite(SCI_VOL, ((uint16_t)att << 8) | att);
}

static void vsBootPlayback() {
  // reset por hardware deixa o chip limpo (necessario depois de gravar)
  vsSpeed = 1000000;
  digitalWrite(VS_PIN_XRESET, LOW);
  delay(2);
  digitalWrite(VS_PIN_XRESET, HIGH);
  vsWaitDreq(200);
  sciWrite(SCI_MODE, SM_SDINEW | SM_RESET);
  delay(2);
  vsWaitDreq(200);
#if VS_MIDI_FIX
  // algumas placas iniciam em modo MIDI: forca GPIO0/1 em 0 e reinicia
  sciWrite(SCI_WRAMADDR, 0xC017); sciWrite(SCI_WRAM, 3);
  sciWrite(SCI_WRAMADDR, 0xC019); sciWrite(SCI_WRAM, 0);
  delay(50);
  sciWrite(SCI_MODE, SM_SDINEW | SM_RESET);
  delay(2);
  vsWaitDreq(200);
#endif
  sciWrite(SCI_CLOCKF, 0x6000);  // 3.0x
  delay(2);
  vsSpeed = 4000000;
  vsSetVolume(vsVolume);
  vsState = VS_IDLE;
}

static void vsInit() {
  pinMode(SD_PIN_CS, OUTPUT);
  digitalWrite(SD_PIN_CS, HIGH);  // SD fora do barramento
  pinMode(10, OUTPUT);            // SS do Uno precisa ser saida
  pinMode(VS_PIN_XCS, OUTPUT);
  pinMode(VS_PIN_XDCS, OUTPUT);
  pinMode(VS_PIN_XRESET, OUTPUT);
  pinMode(VS_PIN_DREQ, INPUT);
  digitalWrite(VS_PIN_XCS, HIGH);
  digitalWrite(VS_PIN_XDCS, HIGH);
  SPI.begin();
  vsBootPlayback();
  vsVersion = (sciRead(SCI_STATUS) >> 4) & 0x0F;  // 4 = VS1053
}

static uint8_t vsReadEndFill() {
  sciWrite(SCI_WRAMADDR, 0x1E06);
  return sciRead(SCI_WRAM) & 0xFF;
}

static void vsStartPlay() {
  if (vsState == VS_REC || vsState == VS_NONE) vsBootPlayback();
  vsState = VS_PLAY;
}

static void vsData(const uint8_t* d, uint8_t n) {
  if (vsState == VS_PLAY) sdiWrite(d, n);
}

static void vsEndPlay() {
  if (vsState != VS_PLAY) return;
  vsEndFill = vsReadEndFill();
  vsFillLeft = 2052;
  vsState = VS_FILL;
}

static void vsAbort() {
  if (vsState != VS_PLAY && vsState != VS_FILL) return;
  sciWrite(SCI_MODE, SM_SDINEW | SM_CANCEL);
  vsEndFill = vsReadEndFill();
  vsFillLeft = 2048;
  vsState = VS_FILL;
}

// chamado no loop: termina a reproducao sem travar o resto
static bool vsServiceFill() {
  if (vsState != VS_FILL) return false;
  uint8_t guard = 4;
  while (vsFillLeft && vsReady() && guard--) {
    uint8_t n = vsFillLeft > 32 ? 32 : vsFillLeft;
    sdiFill(vsEndFill, n);
    vsFillLeft -= n;
  }
  if (!vsFillLeft) {
    if (sciRead(SCI_MODE) & SM_CANCEL) vsBootPlayback();
    vsState = VS_IDLE;
    return true;  // terminou
  }
  return false;
}

static void vsStartRecord() {
  vsBootPlayback();
  sciWrite(SCI_CLOCKF, 0xC000);  // 4.5x para gravar
  delay(2);
  sciWrite(SCI_AICTRL0, 8000);           // 8 kHz
  sciWrite(SCI_AICTRL1, VS_REC_GAIN);    // 0 = ganho automatico
  sciWrite(SCI_AICTRL2, VS_REC_MAXGAIN); // ganho automatico maximo
  sciWrite(SCI_AICTRL3, 6);              // PCM linear, canal esquerdo (mic)
  sciWrite(SCI_MODE, SM_SDINEW | SM_RESET | SM_ADPCM | (VS_REC_LINE_IN ? SM_LINE1 : 0));
  delay(2);
  vsWaitDreq(200);
  vsState = VS_REC;
}

static void vsStopRecord() {
  if (vsState == VS_REC) vsBootPlayback();
}

static uint8_t mulaw(int16_t s16) {
  int32_t s = s16;
  uint8_t sign = 0;
  if (s < 0) { s = -s; sign = 0x80; }
  if (s > 32635) s = 32635;
  s += 0x84;
  uint8_t exp = 7;
  for (int32_t m = 0x4000; (s & m) == 0 && exp > 0; m >>= 1) exp--;
  uint8_t mant = (s >> (exp + 3)) & 0x0F;
  return ~(sign | (exp << 4) | mant);
}

// retorna quantas amostras foram lidas para out (0 ou 32)
static uint8_t vsReadMic(uint8_t* out) {
  if (vsState != VS_REC) return 0;
  uint16_t n = sciRead(SCI_HDAT1);
  if (n < 32 || n > 1024) return 0;
  for (uint8_t i = 0; i < 32; i++) out[i] = mulaw((int16_t)sciRead(SCI_HDAT0));
  return 32;
}
