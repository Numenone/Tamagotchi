# Tamagotchi + Claude no Arduino

Um bichinho virtual que mora em um Arduino Uno com o shield **VS1053 MP3 (Geeetech)**, conversa por voz com o **Claude**, fala com uma voz neural gratuita e mostra **50 animações** de emoção em uma tela TFT colorida (ou num OLED). O mesmo pet também roda no PC como mascote virtual.

**Simulação online no Wokwi:** https://wokwi.com/projects/481585621068344321

## Três jeitos de rodar

| Jeito | Precisa de | Para quem |
|---|---|---|
| [1. No Wokwi (simulador online)](#1-no-wokwi-simulador-online) | Só o navegador | Ver o pet funcionando sem comprar nada |
| [2. No programa para desktop (Tamagotchi Studio)](#2-no-programa-para-desktop-tamagotchi-studio) | Um PC com Windows | Brincar com o pet no PC e conversar por voz |
| [3. No Arduino de verdade](#3-no-arduino-de-verdade) | As peças da lista + o Studio | Montar o bichinho físico |

O pet é o mesmo nos três: as mesmas 50 animações, o mesmo menu (Comer, Brincar, Banho, Dormir, Status, Falar) e as mesmas regras de fome, alegria, energia e higiene.

### Antes de tudo: baixar o projeto

Só é necessário para os jeitos 2 e 3 (e para conversar por voz no jeito 1).

* **Sem Git:** nesta página do GitHub, clique no botão verde **Code** e depois em **Download ZIP**. Descompacte a pasta em um lugar fácil, por exemplo na Área de Trabalho. Não rode o programa de dentro do ZIP.
* **Com Git:**
  ```
  git clone https://github.com/Numenone/Tamagotchi.git
  ```

### A chave da API (o "cérebro" do pet)

Para o pet **conversar**, ele precisa de uma chave da API da Anthropic. Sem a chave, o pet funciona normalmente (comer, brincar, dormir, animações), só não responde quando você fala com ele.

1. Entre em https://console.anthropic.com e crie uma conta.
2. Em **Billing**, coloque créditos (a API é paga por uso; cada conversa custa centavos).
3. Em **API Keys**, clique em **Create Key** e copie a chave (ela começa com `sk-ant-`).
4. Guarde a chave só para você. Nunca coloque a chave em arquivos que vão para o GitHub nem em projetos públicos do Wokwi.

---

## 1. No Wokwi (simulador online)

O Wokwi simula um ESP32 com tela colorida (ILI9341), três botões e um buzzer. Não precisa instalar nada.

### Passo a passo

1. Abra o link: https://wokwi.com/projects/481585621068344321
2. Clique no botão verde de **play** (▶) em cima do desenho do circuito.
3. Espere a compilação (na primeira vez leva cerca de um minuto). A tela simulada acende e mostra o pet.
4. Embaixo aparece o **Serial Monitor**, com as mensagens do pet. Quando aparecer que o Wi-Fi conectou, a parte de conversa já está pronta.
5. Use os botões clicando neles com o mouse, ou pelo teclado (clique uma vez em cima do circuito antes, para o teclado funcionar):

| Botão | Tecla | O que faz |
|---|---|---|
| **A** (verde) | `a` | Abre o menu e passa para o próximo item |
| **B** (azul) | `s` | Escolhe o item |
| **C** (vermelho) | `d` | Volta, para a fala ou faz carinho |

6. Também dá para mandar comandos digitando no Serial Monitor: `/comer`, `/brincar`, `/banho`, `/dormir`, `/acordar`, `/carinho`, `/status`, `/rede`, `/reset` e `/ajuda`.
7. Para parar, clique no botão de **stop** (■).

### Conversar com o pet no Wokwi

O Wokwi não tem microfone, então a conversa passa pelo [ntfy.sh](https://ntfy.sh), um serviço gratuito de mensagens. Existem dois jeitos:

**Jeito A: cérebro no PC (recomendado, com microfone e voz)**

1. Faça uma vez o passo a passo do [programa para desktop](#2-no-programa-para-desktop-tamagotchi-studio), até colar a chave da API no tutorial. Isso instala o Python do projeto e salva a chave no `settings.json`.
2. Deixe a simulação do Wokwi rodando.
3. Na pasta do projeto, entre em `wokwi` e dê dois cliques em **`CEREBRO.bat`**.
4. Abre uma página no navegador (http://localhost:8765). Use o **Chrome** ou o **Edge** e permita o microfone.
5. Fale ou digite uma frase. O PC pensa a resposta, fala com a voz do pet e manda para o Wokwi, que mostra a animação e a legenda na tela.
6. Deixe a janela preta do `CEREBRO.bat` aberta enquanto estiver usando. Para parar, feche essa janela.

**Jeito B: pelo celular**

1. Instale o app **ntfy** (Android ou iPhone).
2. Assine o tópico do pet: `tamagotchi_iot` (é o valor de `NTFY_TOPIC` no arquivo `secrets.h` do Wokwi).
3. Mande uma frase pelo app (o microfone do teclado do celular faz o ditado). A resposta do pet também chega no app.

Para o celular receber resposta, o cérebro precisa estar rodando em algum lugar: no PC (Jeito A) ou no próprio ESP32 (cole a chave em `API_KEY` no `secrets.h`; no Wi-Fi gratuito do Wokwi essa conexão costuma cair, por isso o cérebro no PC é o recomendado).

### Fazer a sua própria cópia no Wokwi

* Para mudar o código e guardar, entre na sua conta do Wokwi e use **Save a copy**.
* Se o link um dia parar de funcionar, dá para montar o projeto do zero: crie um projeto novo de **ESP32** no Wokwi e crie um arquivo para cada um destes da pasta [`wokwi/`](wokwi): `sketch.ino`, `config.h`, `secrets.h`, `anim_data.h`, `draw.h`, `prompt.h`, `diagram.json` e `libraries.txt`. Copie o conteúdo de cada um e clique em play.
* Troque o nome do tópico (`NTFY_TOPIC`) por um nome difícil de adivinhar, porque quem souber o nome consegue mandar frases para o pet.
* **Nunca salve o projeto do Wokwi com a chave da API preenchida:** qualquer pessoa com o link consegue ver os arquivos.

Mais detalhes em [`wokwi/README.md`](wokwi/README.md).

---

## 2. No programa para desktop (Tamagotchi Studio)

O **Tamagotchi Studio** é o programa do PC. Ele mostra o pet na tela do computador, conversa por voz e é também quem grava o firmware no Arduino.

### O que precisa

* PC com **Windows 10 ou 11**
* Internet (para instalar na primeira vez e para conversar)
* A [chave da API](#a-chave-da-api-o-cérebro-do-pet)
* Microfone e caixa de som ou fone (para conversar por voz; também dá para digitar)

Não precisa instalar Python nem nada antes: o programa instala tudo sozinho.

### Passo a passo

1. [Baixe o projeto](#antes-de-tudo-baixar-o-projeto) e abra a pasta.
2. Dê dois cliques em **`TAMAGOTCHI.bat`**.
   * Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**.
   * Na primeira vez abre uma janela preta que faz três coisas sozinha: procura (ou instala) o Python 3.12, instala as bibliotecas e baixa o compilador do Arduino. Isso pode levar alguns minutos. Não feche a janela.
   * Se o Python não instalar sozinho, baixe em https://www.python.org/downloads/, marque **Add Python to PATH** na instalação e abra o `TAMAGOTCHI.bat` de novo.
3. O Studio abre com um **tutorial de 8 passos**. Leia e avance. No último passo, cole a sua **chave da API** e confirme.
4. Pronto. A tela **Início** aparece, esperando um Arduino. Você não precisa ter um Arduino para usar o Studio.
5. Clique em **Brincar com o pet no PC** (ou em **Conversar**, no menu da esquerda). O pet aparece na tela do computador.
6. Para conversar, clique no botão do microfone (ou segure a tecla **ESPAÇO** enquanto fala) ou digite a mensagem. O pet responde com voz e com uma animação.

Nas próximas vezes, é só dar dois cliques no `TAMAGOTCHI.bat`: ele abre direto, sem instalar de novo.

### Telas do Studio

| Tela | Para que serve |
|---|---|
| **Início** | Espera o Arduino e grava o firmware sozinho; atalho para brincar com o pet no PC |
| **Conversar** | Conversa por voz ou por texto |
| **Animações** | Mostra as 50 animações do pet |
| **Configurações** | Nome do pet, idioma, voz, modelo, pinos, tipo de tela, volume e modo sem fio |
| **Ligações** | Desenho de como ligar os fios no Arduino |
| **Tutorial** | Abre o tutorial de novo |

---

## 3. No Arduino de verdade

### O que precisa

* As peças da [lista de peças](#peças) (Arduino Uno, shield VS1053, tela, 3 botões e fone ou caixinha de som)
* Um cabo USB para o Arduino
* O [Tamagotchi Studio](#2-no-programa-para-desktop-tamagotchi-studio) já instalado e com a chave colada

Não precisa instalar a Arduino IDE: o Studio compila e grava sozinho.

### Passo a passo

1. **Monte o circuito** com o Arduino **desligado**:
   1. Encaixe o shield VS1053 em cima do Arduino Uno.
   2. Ligue a tela e os botões seguindo as tabelas da seção [Ligações](#ligações) (também aparecem desenhadas na tela **Ligações** do Studio).
   3. Ligue o fone ou a caixinha de som na saída **SPK** do shield.
2. Abra o **`TAMAGOTCHI.bat`**. Se o seu circuito for diferente do padrão (outra tela, outros pinos, Nano ou Mega), ajuste em **Configurações** e salve.
3. Na tela **Início**, ligue o Arduino no USB do PC.
4. O Studio reconhece a placa e grava o firmware sozinho, mostrando a animação de programação. Leva uns segundos.
5. Quando termina, o pet aparece na tela do Arduino.
6. **Confira a tela:** em **Configurações**, clique em **Testar a tela no Arduino**. Deve aparecer uma moldura branca encostando nas 4 bordas e quadrados vermelho, verde e azul. Se não aparecer assim, veja o [ajuste da TFT](#ligações).
7. **Para conversar:** segure o botão **C** do Arduino, fale (até 15 segundos) e solte. O pet responde pela caixa de som. Para isso o Arduino precisa estar ligado no PC com o Studio aberto, porque é o PC que usa a internet. Sem o Studio, o pet continua vivo (menu, fome, sono, animações) e mostra "Sem PC :(" quando você tenta falar.

Mudou alguma coisa em **Configurações** (nome, idioma, pinos, display, volume)? Clique em salvar e o Studio regrava o Arduino automaticamente.

Para conversar **sem o PC**, veja o [modo sem fio com ESP32](#modo-sem-fio-esp32-conversar-sem-o-pc).

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
