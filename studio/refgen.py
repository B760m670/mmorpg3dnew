#!/usr/bin/env python3
"""ГЕНЕРАТОР РЕФЕРЕНСОВ. Не материал в фильм — МИШЕНЬ, по которой мерить.

ЗАЧЕМ ОН НУЖЕН, и это единственная причина. Отличить «сносно» от «хорошо» я не
умею и за целый день не показал ни одного случая, где сумел бы. Зато отличить
«моё» от «вот этого» умею точно: пропорции, вес линии, число цветов, гистограмму,
композицию — всё это измеримо, если есть с чем сравнивать. До сих пор я целился
в картинку, которую видел только заказчик. Сгенерированный кадр даёт цель.

ЧЕГО ОН НЕ ДАЁТ И НЕ ДАСТ:
  - одинакового персонажа в тысяче кадров (генерация этого не умеет в принципе);
  - анимации;
  - 3D-модели.
То есть в производство отсюда не идёт ничего. Идёт только ЦЕЛЬ: заказчик
показывает пальцем на нужный кадр, а дальше разница между ним и нашим рендером
становится числом, и с числом я работаю.

ПРО ПРАВА. Сгенерированное используется как референс для собственной работы —
так же, как художник смотрит на фотографию. В кадр фильма эти изображения не
попадают.

МАШИНА БЕЗ ВИДЕОКАРТЫ. Всё считается на четырёх ядрах, поэтому размер и число
шагов выбраны так, чтобы кадр выходил за минуты, а не за часы.

Запуск:
  python3 studio/refgen.py "текст" --out кадр.png [--model ...] [--steps 4]
"""
import argparse
import os
import time

import torch
from diffusers import AutoPipelineForText2Image

torch.set_num_threads(os.cpu_count() or 4)

# Модели, проверенные на этой машине. sd-turbo работает за считаные шаги —
# им нащупывается композиция; анимешная SD1.5 медленнее, но даёт нужный стиль.
MODELS = {
    "turbo": ("stabilityai/sd-turbo", 2, 0.0),
    # Linaqruf/anything-v3.0 закрыта (401 без токена); MeinaMix открыта.
    "anime": ("Meina/MeinaMix_V11", 22, 7.0),
}

NEG = ("photo, 3d render, cgi, blurry, lowres, bad anatomy, extra limbs, "
       "watermark, text, signature, jpeg artifacts, deformed hands")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--out", default="/tmp/ref.png")
    ap.add_argument("--model", default="turbo", choices=list(MODELS))
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--w", type=int, default=512)
    ap.add_argument("--h", type=int, default=512)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=1)
    a = ap.parse_args()

    mid, dsteps, dcfg = MODELS[a.model]
    steps = a.steps if a.steps is not None else dsteps
    cfg = a.cfg if a.cfg is not None else dcfg

    t0 = time.time()
    pipe = AutoPipelineForText2Image.from_pretrained(mid, torch_dtype=torch.float32,
                                                     safety_checker=None)
    pipe.set_progress_bar_config(disable=True)
    print("модель %s поднята за %.0f с" % (mid, time.time() - t0))

    base = a.out.rsplit(".", 1)[0]
    for k in range(a.n):
        g = torch.Generator().manual_seed(a.seed + k)
        t1 = time.time()
        kw = dict(prompt=a.prompt, num_inference_steps=steps,
                  guidance_scale=cfg, width=a.w, height=a.h, generator=g)
        if cfg > 0:
            kw["negative_prompt"] = NEG
        im = pipe(**kw).images[0]
        path = a.out if a.n == 1 else "%s_%d.png" % (base, k)
        im.save(path)
        print("КАДР %s: %dx%d, %d шагов, зерно %d — %.0f с"
              % (path, a.w, a.h, steps, a.seed + k, time.time() - t1))


if __name__ == "__main__":
    main()
