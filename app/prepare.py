"""Prepara o compilador do Arduino (roda pelo TAMAGOTCHI.bat na primeira vez)."""
import sys

from . import firmware_tools as F
from . import settings as SET


def main():
    s = SET.load()
    print("  Preparando o compilador do Arduino (arduino-cli + placas AVR)...")
    try:
        ok = F.ensure_cli(lambda m: print("   ", m))
    except Exception as e:
        print("   Nao consegui preparar agora:", e)
        print("   Sem problema: o Studio tenta de novo quando voce ligar o Arduino.")
        return 0
    if ok:
        print("  Compilando uma vez para deixar tudo pronto...")
        F.compile_fw(s, lambda m: None)
        print("  Pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
