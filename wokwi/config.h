// Configuracao da versao Wokwi (ESP32 + ILI9341 + 3 botoes + buzzer).
// Mesmos valores do config.h do Uno e do bridge_config.h do ESP32.
#pragma once

#define PET_NAME "PIXO"

// tela ILI9341 (SPI padrao do ESP32: SCK 18, MOSI 23, MISO 19)
#define TFT_PIN_CS 15
#define TFT_PIN_DC 2
#define TFT_PIN_RST 4
#define TFT_PET_COLOR 0   // 0 ciano, 1 verde, 2 rosa, 3 branco, 4 amarelo

// botoes (ligados no GND, usam o pull-up interno)
#define PIN_BTN_A 32
#define PIN_BTN_B 33
#define PIN_BTN_C 27

// buzzer: faz a "voz" de bichinho enquanto a legenda passa
#define PIN_BUZZER 25
#define VOICE_BEEPS 1

// pet
#define DECAY_SECONDS 90
#define LBL_HUNGER "Fome"
#define LBL_HAPPY "Alegria"
#define LBL_ENERGY "Energia"
#define LBL_CLEAN "Higiene"
#define LBL_SLEEPING "dormindo"
#define MENU_LABELS "Comer", "Brincar", "Banho", "Dormir", "Status", "Falar"

// cerebro
#define BRAIN_MODEL "claude-haiku-5-5"
#define BRAIN_EFFORT "low"
#define HISTORY_TURNS 12
#define MSG_LISTEN "Digite no Serial Monitor"
#define MSG_LISTEN_PHONE "Fale no PC ou no celular"
#define MSG_NO_KEY "Sem chave da API"
#define MSG_NO_WIFI "Sem Wi-Fi"
#define MSG_WIFI_OK "Wi-Fi ok!"
#define MSG_BRAIN_ERR "Nao consegui pensar :("
#define MSG_BUSY "Calma, to pensando..."
#define MSG_REFUSAL "Hmm, disso eu prefiro nao falar. Vamos brincar de outra coisa?"

static const char* const ANIM_NAMES[ANIM_COUNT] = {"idle", "happy", "ecstatic", "laugh", "love", "shy", "sad", "crying", "angry", "furious", "surprised", "scared", "confused", "thinking", "idea", "sleepy", "sleeping", "yawn", "eating", "hungry", "full", "sick", "dizzy", "dancing", "singing", "playing", "excited", "proud", "cool", "wink", "bored", "annoyed", "nervous", "embarrassed", "curious", "listening", "talking", "hello", "goodbye", "ko", "cold", "hot", "bathing", "dirty", "celebrate", "grateful", "sorry", "mischief", "determined", "relaxed"};
#define ACT_COUNT 9
static const char* const ACT_NAMES[ACT_COUNT] = {"none", "feed", "play", "clean", "sleep", "wake", "stats", "talk", "pet"};
