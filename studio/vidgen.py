#!/usr/bin/env python3
"""ГЕНЕРАТОР КЛИПОВ-РЕФЕРЕНСОВ. Как и refgen.py — мишень, а не материал.

ВЫБОР МОДЕЛИ, и он продиктован машиной. Видеокарты нет, четыре ядра.
  AnimateDiff-Lightning (ByteDance) — 4 шага вместо 20, поверх обычной аниме-
    модели SD1.5. Модуль движения 1.7 ГБ. ЭТО ЕДИНСТВЕННОЕ, что здесь считается
    за минуты.
  Stable Video Diffusion — 9.5 ГБ, часы на клип, и лицензия некоммерческая.
  CogVideoX-2B, LTX-Video, Wan 2.1 — все от 2 млрд параметров и десятки кадров;
    на процессоре это часы. Отброшены не по вкусу, а по арифметике.

ЗАЧЕМ ВИДЕО, А НЕ ТОЛЬКО КАРТИНКА. Картинка даёт цель по кадру: тон, цвет,
композиция. Видео даёт цель по ДВИЖЕНИЮ — как ведёт себя пола пальто, с какой
частотой идёт рябь, сколько держится поза. Это то, чего из статичного референса
не вынуть, и то, чего у нас нет вовсе.

ЧЕГО ОНО НЕ ДАЁТ: годного в фильм кадра. Персонаж поплывёт между кадрами,
разрешение низкое, длительность около секунды. В производство отсюда не идёт
ничего — только мера, к которой стремиться.

Запуск:
  python3 studio/vidgen.py "текст" --out клип.mp4 [--frames 16] [--steps 4]
"""
import argparse
import os
import time

import torch
from diffusers import AnimateDiffPipeline, MotionAdapter, EulerDiscreteScheduler
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file

torch.set_num_threads(os.cpu_count() or 4)

BASE = "Meina/MeinaMix_V11"              # аниме-основа SD1.5, открытая
# Linaqruf/anything-v3.0 оказалась ЗАКРЫТОЙ репой (401 без токена) — записано,
# чтобы не наступить второй раз.
REPO = "ByteDance/AnimateDiff-Lightning"

NEG = ("photo, 3d render, blurry, lowres, bad anatomy, extra limbs, "
       "watermark, text, deformed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--out", default="/tmp/clip.mp4")
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--steps", type=int, default=4, choices=[1, 2, 4, 8])
    ap.add_argument("--w", type=int, default=512)
    ap.add_argument("--h", type=int, default=320)
    ap.add_argument("--fps", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    t0 = time.time()
    adapter = MotionAdapter()
    ckpt = "animatediff_lightning_%dstep_diffusers.safetensors" % a.steps
    adapter.load_state_dict(load_file(hf_hub_download(REPO, ckpt)))
    pipe = AnimateDiffPipeline.from_pretrained(BASE, motion_adapter=adapter,
                                               torch_dtype=torch.float32,
                                               safety_checker=None)
    # Lightning требует именно такого расписания: с обычным DDIM четыре шага
    # дают кашу, и это не «настройка качества», а условие работы модели.
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing", beta_schedule="linear")
    pipe.set_progress_bar_config(disable=True)
    print("модель поднята за %.0f с" % (time.time() - t0))

    t1 = time.time()
    out = pipe(prompt=a.prompt, negative_prompt=NEG,
               num_frames=a.frames, num_inference_steps=a.steps,
               guidance_scale=1.0, width=a.w, height=a.h,
               generator=torch.Generator().manual_seed(a.seed))
    frames = out.frames[0]
    dt = time.time() - t1
    print("КЛИП: %d кадров %dx%d, %d шагов — %.0f с (%.1f с на кадр)"
          % (len(frames), a.w, a.h, a.steps, dt, dt / len(frames)))

    import imageio
    base = a.out.rsplit(".", 1)[0]
    imageio.mimsave(base + ".gif", [f for f in frames], duration=1.0 / a.fps, loop=0)
    try:
        imageio.mimsave(a.out, [f for f in frames], fps=a.fps, quality=8)
        print("сохранено:", a.out, "и", base + ".gif")
    except Exception as e:
        print("mp4 не собрался (%s), остался gif" % e)
    # раскладка по кадрам — чтобы можно было мерить каждый отдельно
    for i, f in enumerate(frames):
        f.save("%s_%02d.png" % (base, i))


if __name__ == "__main__":
    main()
