#!/usr/bin/env python3
"""КЛИЕНТ ЖИВОГО КАНАЛА — разговор с УЖЕ ЗАПУЩЕННОЙ игрой.

Игра поднимается один раз (tools/live_start.sh) и живёт; здесь ей шлются
команды и принимаются ответы. Взгляд на мир стоит секунды вместо минут, и
можно ИСКАТЬ вслепую — обернуться, отойти, спросить что под ногами — а не
угадывать нужный ракурс до запуска.

Запуск:
    python3 tools/live.py "state"
    python3 tools/live.py "pos -224,30,-832" "turn 180,-15" "shot /tmp/a.png"
Несколько команд выполняются по порядку в одной сессии.
"""
import socket
import sys

HOST, PORT = "127.0.0.1", 8787
TIMEOUT = 120.0        # снимок на программном растеризаторе не мгновенный


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    try:
        s = socket.create_connection((HOST, PORT), timeout=5.0)
    except OSError as e:
        print("игра не отвечает на %s:%d (%s).\n"
              "Подними её: bash tools/live_start.sh" % (HOST, PORT, e))
        return 2
    s.settimeout(TIMEOUT)
    buf = b""
    rc = 0
    for cmd in sys.argv[1:]:
        s.sendall((cmd + "\n").encode())
        # ответ — одна строка (у state их несколько, он шлёт их одним куском)
        while b"\n" not in buf:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                print("[%s] ОТВЕТА НЕТ за %.0f с" % (cmd, TIMEOUT))
                rc = 3
                break
            if not chunk:
                print("[%s] игра закрыла канал" % cmd)
                return rc
            buf += chunk
        if b"\n" not in buf:
            break
        line, buf = buf.split(b"\n", 1)
        print("[%s] %s" % (cmd, line.decode(errors="replace").replace("\\n", "\n")))
    s.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
