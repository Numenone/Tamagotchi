# PIXO no Wokwi

Versão do Tamagotchi para o simulador [Wokwi](https://wokwi.com): o mesmo bichinho do Arduino Uno (50 animações, menu, fome, sono, banho e tela de status) rodando em um ESP32 com tela ILI9341, três botões e buzzer.

## Arquivos

| Arquivo | O que é |
|---|---|
| `sketch.ino` | firmware do ESP32 (pet, tela, botões, ntfy e cérebro opcional) |
| `config.h` | nome, pinos, textos e modelo |
| `secrets.h` | Wi-Fi do simulador, tópico do ntfy e chave da API (opcional) |
| `anim_data.h`, `draw.h`, `prompt.h` | animações, desenho e prompt, copiados do firmware do Uno |
| `diagram.json`, `libraries.txt` | circuito e bibliotecas do Wokwi |
| `CEREBRO.bat`, `cerebro_pc.py`, `cerebro_pc.html` | cérebro no PC com microfone e voz |

No Wokwi, crie um arquivo para cada um dos `.ino`, `.h`, `diagram.json` e `libraries.txt`.

## Botões

- **A** (verde, tecla `a`): abre o menu e passa para o próximo item
- **B** (azul, tecla `s`): escolhe
- **C** (vermelho, tecla `d`): volta, para a fala ou faz carinho

No Serial Monitor: `/comer /brincar /banho /dormir /acordar /carinho /status /rede /reset /ajuda`.

## Conversar

O Wokwi não tem microfone, então a conversa passa pelo [ntfy.sh](https://ntfy.sh), no tópico definido em `secrets.h` (`NTFY_TOPIC`).

**Cérebro no PC (recomendado).** Deixe `API_KEY` comentado no `secrets.h` e rode `CEREBRO.bat` no computador. Ele abre `http://localhost:8765` com microfone (Chrome ou Edge), usa o mesmo cérebro e a mesma voz do Tamagotchi Studio e a chave do `settings.json`. O PC responde e o ESP32 mostra a animação e a legenda.

```
microfone do PC / app ntfy no celular / Serial do Wokwi
      -> CEREBRO.bat (cérebro + voz no PC)
      -> ntfy.sh/<tópico>_pc -> ESP32 no Wokwi
      -> ntfy.sh/<tópico>    -> celular
```

**Pelo celular.** Instale o app ntfy, assine o tópico e mande a frase (o microfone do teclado faz o ditado).

**Cérebro no ESP32.** Com `API_KEY` no `secrets.h`, o ESP32 chama a API direto. No gateway gratuito do Wokwi essa conexão costuma cair, então prefira o cérebro no PC.

## Cuidados

- Projetos do Wokwi ficam visíveis para quem tiver o link: não salve o projeto com a chave no `secrets.h`.
- Quem souber o nome do tópico do ntfy consegue mandar frases para o PIXO. Use um nome difícil de adivinhar.
- O ESP32 precisa do Wi-Fi do Wokwi (gateway público). Se ele cair, reinicie a simulação mais tarde.
