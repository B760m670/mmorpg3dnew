#!/usr/bin/env python3
"""ВИДЕО СО СТЕНДА — потому что походку по кадрам судить нельзя.

ЗАЧЕМ ЭТО ЕСТЬ. Всё, чем я до сих пор проверял персонажа, было одиночными
кадрами. Кадр отвечает на вопрос «какая поза», а спрашивали другое: «как он
идёт». Походка и есть то, что между позами; сколько ни снимай стоп-кадров,
движения из них не собрать. Заказчик сказал это прямо, и это верно: судить
движение может только глаз, и смотреть надо видео.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ «ПРОСТО СНЯТЬ N КАДРОВ».
1. ИЗМЕРЕНО: на программном растеризаторе кадр рисуется ~1.5 с, а движок
   сообщает, что прожил за него 0.067 с (потолок: 8 шагов физики по 1/120 с).
   То есть на СЕКУНДУ ДВИЖЕНИЯ приходится 15 кадров, и плавнее не снять ничем.
2. Поэтому мир на время съёмки ЗАМЕДЛЯЕТСЯ (команда slow). Замедлив вдвое,
   получаем 30 кадров на ту же секунду движения. Кадр честный — анимация,
   физика и камера идут своим порядком, просто медленнее.
3. Стенд пишет рядом с кадрами ВРЕМЯ КАЖДОГО КАДРА (игровое, не время
   рисования), и сборка даёт каждому кадру его длительность. Видео идёт в
   НАСТОЯЩЕМ темпе, хотя снималось в сто раз медленнее.

Запуск (игра должна быть поднята: bash tools/live_start.sh):
    python3 tools/film.py --at 18,22,150 --walk 1.0 --sec 4 --out /tmp/шаг.mp4
    python3 tools/film.py --frames 60 --out /tmp/стойка.mp4   # без движения
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys

HOST, PORT = "127.0.0.1", 8787


class Стенд:
    def __init__(self):
        try:
            self.s = socket.create_connection((HOST, PORT), timeout=5.0)
        except OSError as e:
            print("игра не отвечает на %s:%d (%s).\n"
                  "Подними её: bash tools/live_start.sh" % (HOST, PORT, e))
            sys.exit(2)
        self.s.settimeout(3600.0)
        self.buf = b""

    def __call__(self, cmd, тихо=False):
        self.s.sendall((cmd + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.s.recv(65536)
            if not chunk:
                raise SystemExit("игра закрыла канал на «%s»" % cmd)
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        ответ = line.decode(errors="replace").replace("\\n", "\n")
        if not тихо:
            print("[%s] %s" % (cmd, ответ))
        return ответ


def собрать(папка, выход, fps=30):
    """Склеить кадры в видео, дав каждому его собственную длительность."""
    тайминг = os.path.join(папка, "время.txt")
    кадры = sorted(f for f in os.listdir(папка) if f.endswith(".png"))
    if not кадры:
        raise SystemExit("в %s нет кадров" % папка)
    if os.path.exists(тайминг):
        dt = [float(x) for x in open(тайминг).read().split()]
    else:
        dt = [1.0 / fps] * len(кадры)
    # СПИСОК ДЛЯ FFMPEG с разной длительностью кадров. Последний кадр
    # приходится повторить: демуксер concat игнорирует duration последней
    # записи, и без повтора конец видео обрезается.
    список = os.path.join(папка, "склейка.txt")
    with open(список, "w") as f:
        for имя, d in zip(кадры, dt):
            f.write("file '%s'\nduration %.5f\n" % (имя, max(d, 1e-3)))
        f.write("file '%s'\n" % кадры[-1])
    длит = sum(dt)
    # ВЫХОД С ПОСТОЯННОЙ ЧАСТОТОЙ: ffmpeg сам разложит кадры разной
    # длительности по ровной сетке -r, повторяя и пропуская где надо. Темп
    # сохраняется, файл играется везде. Задавать при этом -vsync vfr нельзя —
    # два взаимно исключающих требования, ffmpeg отказывается.
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", список, "-r", str(fps), "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-crf", "18",
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", выход], check=True)
    частота = len(кадры) / длит if длит else 0.0
    print("видео: %s — %d кадров, %.2f с настоящего времени, %.1f МБ"
          % (выход, len(кадры), длит, os.path.getsize(выход) / 1e6))
    print("ЧАСТОТА СЪЁМКИ: %.1f кадра на секунду движения" % частота)
    if частота < 20:
        print("  ВНИМАНИЕ: реже 20 кадров на секунду движения — рывки в видео "
              "принадлежат СЪЁМКЕ, а не игре. Суди по позам, не по плавности.")
    return выход


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/tmp/claude-live/ходьба.mp4")
    p.add_argument("--dir", default="/tmp/claude-live/film")
    p.add_argument("--frames", type=int, default=0,
                   help="сколько кадров снять (по умолчанию из --sec)")
    p.add_argument("--sec", type=float, default=4.0,
                   help="сколько СЕКУНД ДВИЖЕНИЯ снять")
    p.add_argument("--walk", type=float, default=None,
                   help="намерение идти вперёд, 0..1 (0.5 шаг, 1.0 быстро)")
    p.add_argument("--at", default=None, help="X,Z[,АЗИМУТ] — поставить тело")
    p.add_argument("--clip", default=None,
                   help="проиграть ОДИН клип вместо смешивания")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--slow", type=float, default=0.5,
                   help="во сколько раз замедлить мир на время съёмки "
                        "(0.5 -> 30 кадров на секунду движения, 0.25 -> 60)")
    p.add_argument("--fast", action="store_true",
                   help="снять с кадра дорогие слои (GI, облака, фон, пост)")
    p.add_argument("--keep", action="store_true", help="не стирать кадры")
    a = p.parse_args()

    if os.path.isdir(a.dir):
        shutil.rmtree(a.dir)
    os.makedirs(a.dir, exist_ok=True)

    ст = Стенд()
    if a.at:
        ст("walk " + a.at)
    ст("hud off")
    if a.fast:
        ст("fast")
    if a.clip:
        ст("clip " + a.clip)
    ст("slow %.3f" % a.slow)

    # СКОЛЬКО КАДРОВ НА ЗАДАННОЕ ВРЕМЯ ДВИЖЕНИЯ. Считать по --fps нельзя:
    # игра сообщает 0.0667 с прожитого времени за кадр независимо от того,
    # сколько кадр рисовался. Значит на секунду движения приходится 15 кадров
    # при обычном ходе времени и 15/К при замедлении в К раз.
    n = a.frames
    if n <= 0:
        на_секунду = 15.0 / max(a.slow, 0.02)
        n = max(int(a.sec * на_секунду), 8)
        print("на секунду движения выходит %.0f кадров -> на %.1f с нужно %d"
              % (на_секунду, a.sec, n))

    if a.walk is not None:
        ст("go %.2f,0" % a.walk)
    # ЗАМЕР ПОХОДКИ ИДЁТ ДО СЪЁМКИ И ОТДЕЛЬНО: два отложенных ответа в одном
    # канале перепутались бы местами — стенд отвечает по готовности, а не по
    # порядку команд.
    ст("gait %d" % min(n, 90))
    print("снимаю %d кадров…" % n)
    ст("film %s %d" % (a.dir, n))
    if a.walk is not None:
        ст("go 0,0")
    ст("slow 1")
    собрать(a.dir, a.out, a.fps)
    if not a.keep:
        for f in os.listdir(a.dir):
            if f.endswith(".png"):
                os.remove(os.path.join(a.dir, f))


if __name__ == "__main__":
    main()
