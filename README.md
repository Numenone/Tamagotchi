# Tamagotchi + Claude no Arduino

Um bichinho virtual que mora em um Arduino Uno com o shield **VS1053 MP3 (Geeetech)**, conversa por voz com o **Claude**, fala com uma voz neural gratuita e mostra **50 animações** de emoção em uma tela TFT colorida (ou num OLED). O mesmo pet também roda no PC como mascote virtual.

## Como usar

1. Dê dois cliques em **`TAMAGOTCHI.bat`**.
   * Na primeira vez ele instala tudo sozinho: Python (se faltar), bibliotecas e o compilador do Arduino.
2. Faça o **tutorial** (8 passos). No final, cole a sua **chave do Claude** (console.anthropic.com, em API Keys).
3. A tela principal fica **esperando o Arduino**. Ligue o cabo USB e pronto: o Studio gera as configurações, compila e grava o firmware sozinho, mostrando a animação de programação. Quando termina, o pet aparece no display.
4. Para conversar: **segure o botão C** do Arduino e fale. Ou use a tela **Conversar** do Studio (botão de microfone, tecla ESPAÇO ou digitando).

Mudou alguma coisa em **Configurações** (nome, idioma, pinos, display, volume)? Clique em salvar e o Studio regrava o Arduino automaticamente.

## Peças

| Peça | Observação |
|---|---|
| Arduino Uno | Nano e Mega também têm opção em Configurações |
| Shield VS1053 MP3 Geeetech | Encaixado em cima do Uno. Tem microfone, MIC, SPK e SD |
| Tela TFT IPS 0.96" 80x160 colorida (ST7735S, 8 pinos) | Padrão. Um OLED I2C 128x64 (SSD1306/SH1106) também funciona |
| 3 botões | A, B e C |
| Fone ou caixinha de som P2 | Na saída SPK do shield |

## Ligações

O shield usa os pinos 2 (DREQ), 6 (XCS), 7 (XDCS), 8 (XRESET), 9 (SD CS), 11, 12 e 13 (SPI). A TFT divide o SPI com o shield (cada um com o seu CS):

| Pino da TFT | Arduino |
|---|---|
| GND | GND |
| VCC | 3.3V |
| SCL (é o clock SPI) | D13, com resistor de 1k em série |
| SDA (é o MOSI SPI) | D11, com resistor de 1k em série |
| RES | D5, com resistor de 1k em série |
| DC | D4, com resistor de 1k em série |
| CS | D10, com resistor de 1k em série |
| BLK (luz de fundo) | D3 (controla o brilho) ou direto no 3.3V |

A tela trabalha em 3.3 V e o Uno em 5 V: os resistores de 1k protegem as entradas dela (um conversor de nível também serve).

| Botões | Arduino |
|---|---|
| Botão A | A0 e GND |
| Botão B | A1 e GND |
| Botão C | A2 e GND |

Os botões usam o resistor interno (INPUT_PULLUP), então não precisa de resistor.

Usando um OLED I2C no lugar da TFT: VCC no 5V, GND no GND, SDA no A4, SCL no A5, e escolha o modelo em Configurações.

**Ajuste da TFT:** existem várias versões dessa tela. Em Configurações use "Testar a tela no Arduino": deve aparecer uma moldura branca encostando nas 4 bordas e quadrados vermelho, verde e azul. Se estiver cortada, mude os ajustes horizontal/vertical; se o fundo ficar branco, mude "inverter cores"; se o vermelho sair azul, mude "trocar vermelho e azul".

## Controles do pet

* **A**: abre o menu ou passa para o próximo item
* **B**: escolhe o item (Comer, Brincar, Banho, Dormir, Status, Falar)
* **C**: volta, para a fala, ou faz carinho
* **Segurar C**: grava a sua voz (até 15 s). Ao soltar, o Claude responde.

Fome, alegria, energia e higiene caem com o tempo (a velocidade é configurável) e ficam salvas na EEPROM, então o pet lembra de tudo mesmo desligado.

## Como funciona por dentro

```
 Arduino (corpo)                 PC: Tamagotchi Studio (ponte)             Internet
 display, botoes, fome,   USB    entende a fala (Google, gratis)    --->  Claude (cerebro)
 mic do VS1053 (8 kHz)  ------>  pergunta ao Claude: fala + emocao  <---  escolhe 1 de 50 animacoes
 alto-falante do VS1053 <------  voz neural gratis (Edge TTS, MP3)
```

* **Claude**: o modelo padrão é o Claude Opus 5.5 com esforço baixo (resposta rápida para voz). Dá para trocar para Sonnet 5.5 ou Haiku 5.5. A resposta vem em JSON com a fala, a animação, uma ação (comer, dormir...) e a mudança de humor. Também liga o fallback automático do servidor, que tenta outro modelo se um filtro de segurança recusar.
* **Voz**: Edge TTS (vozes neurais gratuitas, como a pt-BR Francisca, com o tom mais agudo para ficar fofinha). Sem internet, dá para usar a voz do Windows.
* **Ouvido**: reconhecimento do Google gratuito, ou Whisper local (instale com `.venv\Scripts\pip install faster-whisper`).
* **Áudio pelo USB**: o microfone do VS1053 grava em PCM 8 kHz, o Arduino comprime em µ-law (8 KB/s) e manda ao PC. A voz volta como MP3 de 48 kbps em blocos de 32 bytes com controle de fluxo, e o VS1053 decodifica sozinho.
* **Tela**: driver próprio por páginas de 8 linhas (economiza RAM do Uno). Na TFT cada página é colorida na hora (pet, efeitos e barra de status com cores diferentes) e enviada pelo SPI entre um bloco de áudio e outro. As animações são montadas com olhos, bocas, movimentos e efeitos definidos em `app/animations.py`. O mesmo arquivo gera o `anim_data.h` do firmware, por isso o pet do PC e o do Arduino são idênticos.

## Arquivos

```
TAMAGOTCHI.bat            abre tudo (instala na primeira vez)
settings.json             suas configurações (criado pelo Studio)
app/                      programa do PC (pygame)
  main.py, screens.py     telas: tutorial, início, conversar, animações, configurações, ligações
  animations.py           as 50 animações (fonte única para PC e Arduino)
  sprites.py              pixel art e fonte 5x7
  brain.py                integração com o Claude
  voice.py                voz, reconhecimento de fala e microfone
  serial_link.py          protocolo USB com o Arduino
  firmware_tools.py       gera config.h/anim_data.h e grava com o arduino-cli
firmware/tamagotchi/      firmware do Arduino (tamagotchi.ino, tft.h, oled.h, vs1053.h)
firmware/esp32_bridge/    firmware do ESP32 para o modo sem fio (secrets.h com as chaves fica fora do Git)
data/                     memória da conversa e estado do pet virtual
```

## Modo sem fio (ESP32): conversar sem o PC

Um **ESP32** ligado na serial do Uno faz o papel do PC: ouve pelo **Google Speech-to-Text**, pensa com o **Claude** e fala pelo **Google Text-to-Speech**. O firmware do Uno, o shield e a tela continuam iguais.

**Atenção:** a chave do Claude e a do Google ficam gravadas dentro do ESP32. Quem pegar a placa consegue extrair as duas. Use chaves só para isso, com limite de gasto: no console da Anthropic, um workspace com spend limit baixo; no Google Cloud, a chave restrita às duas APIs de voz. A conexão HTTPS também não confere o certificado do servidor (é um protótipo).

**O que precisa:**
* Placa ESP32 DevKit (ESP32-WROOM-32; a versão com PSRAM, WROVER, também serve)
* 2 resistores (1k e 2k) para o divisor de tensão
* Chave do Google Cloud: crie um projeto em console.cloud.google.com, ative a cobrança, ative as APIs **Cloud Speech-to-Text** e **Cloud Text-to-Speech** e crie uma chave de API em Credenciais. As duas têm cota gratuita mensal.
* Wi-Fi de 2,4 GHz sem página de login (o roteador do celular é o mais garantido)

**Como gravar:**
1. Grave o Uno pelo Studio como sempre (cabo USB no PC).
2. Em **Configurações > Sem fio (ESP32)**, preencha o Wi-Fi e a chave do Google. A chave do Claude é a mesma do Studio.
3. Ligue **só o ESP32** no USB, escolha a porta dele e clique em **Gravar o ESP32**. Na primeira vez o Studio baixa o suporte ao ESP32 (é grande, uns 10 minutos). Se a gravação travar em "Connecting", segure o botão **BOOT** da placa.

**Ligações (com tudo desligado):**

| ESP32 | Uno |
|---|---|
| GPIO17 (TX2) | pino 0 (RX) |
| GPIO16 (RX2) | pino 1 (TX), passando pelo divisor: Uno TX, resistor 1k, GPIO16, resistor 2k, GND |
| VIN (ou 5V) | 5V |
| GND | GND |

O divisor baixa os 5 V do Uno para 3,3 V. Sem ele o ESP32 pode queimar.

Alimente o Uno por um power bank ou carregador USB. Quando o ESP32 conecta no Wi-Fi, o pet mostra "Wi-Fi ok!". Segure o botão C e fale. Se aparecer "Sem PC :(" ou "Sem Wi-Fi", o ESP32 não está conectado.

Para regravar o Uno depois, tire o fio do pino 0 antes (o ESP32 atrapalha a gravação).

**Para ver o que está acontecendo:** com o ESP32 no USB do PC, abra um monitor serial em 115200. Ele mostra o Wi-Fi, o que entendeu, a resposta do pet e os erros (sem mostrar as chaves).

**Diferenças em relação ao PC:** a memória da conversa fica só na RAM (some quando desliga), e a voz é a do Google em vez da Edge TTS.

## Problemas comuns

* **TFT branca, cortada ou com cores trocadas**: use "Testar a tela no Arduino" e os ajustes da TFT em Configurações.
* **OLED apagado**: troque o endereço para 0x3D, ou o modelo para SH1106.
* **Sem som**: confira o fone na saída SPK e o volume. Se o shield ficar mudo, ligue o "Ajuste MIDI do VS1053".
* **Microfone não entende**: aumente o ganho do microfone, ou desligue "Usar o microfone do shield" para gravar pelo microfone do PC enquanto segura o C.
* **Erro ao gravar o Arduino**: feche a Arduino IDE ou qualquer Monitor Serial aberto na mesma porta.
* **Compilar pela Arduino IDE**: funciona, mas o áudio fica mais lento porque a IDE não aumenta o buffer serial. Prefira o Studio (ele compila com `-DSERIAL_RX_BUFFER_SIZE=256`).
