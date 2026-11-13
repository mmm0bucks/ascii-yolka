# /// script
# dependencies = ["pygame-ce", "numpy"]
# ///
"""
ASCII-ёлка из математических символов.

3D-облако точек (хвоя, гирлянды, шары, звезда, подарки, снег) каждый кадр
поворачивается, проецируется на сетку символов и через z-буфер превращается
в «картинку» из цифр и знаков. Плотность символа выбирается по освещённости
точки: тёмное -> ". : -", светлое -> "8 # @".

Запуск:   pip install -r requirements.txt   ->   python yolka/main.py
В браузере: сборка через pygbag (см. README), файл обязан называться main.py.
Клавиши:  SPACE / клик — собрать ёлку, затем пауза
          R — собрать заново · S — скриншот · мышь (тянуть) — вращать · Esc — выход
"""
import asyncio
import os
import sys
import time

import numpy as np
import pygame

# ============================================================ КРУТИЛКИ
# Всё, что хочется подстроить под себя. 1.0 = «как задумано», меньше — тише/медленнее.
GREETING = "С НОВЫМ ГОДОМ 2027"

SPEED = 0.70             # общая скорость всего: вращение, сборка, мерцание, снег
ROT_SPEED = 0.15         # вращение ёлки, рад/с (0 — стоит на месте)
SNOW_SPEED = 0.3         # скорость падения снега
SNOW_AMOUNT = 1.0        # количество снежинок

TREE_BRIGHT = 1.0        # яркость хвои
GARLAND_BRIGHT = 0.75    # золотая мишура (спирали)
BULB_BRIGHT = 1.0        # цветные лампочки
BALL_BRIGHT = 1.0        # шары
STAR_BRIGHT = 1.0        # звезда
GIFT_BRIGHT = 0.8        # коробки подарков
RIBBON_BRIGHT = 0.8      # ленточки на подарках
SNOW_BRIGHT = 1.0        # снежинки
GLOW = 1.0               # свечение вокруг ярких символов, от 0 (выключено) до 1

# ------------------------------------------------------- техническая часть

CW, CH, FONT_PX = 9, 14, 14      # размер ячейки и шрифта, px
START_SIZE = (792, 1036)         # окно при запуске на компьютере (в браузере — вся страница)
MAX_H = 1080                     # на экранах выше кадр считается в этом размере и растягивается
FPS = 30
MONO = "consolas,menlo,dejavusansmono,couriernew,monospace"
BG = (6, 8, 15)

TAU = 2 * np.pi
PITCH = np.radians(12)           # камера смотрит чуть сверху
CAM = 7.0                        # расстояние до камеры (перспектива)
LIGHT = np.array([-0.45, 0.65, 0.62]) / np.linalg.norm([-0.45, 0.65, 0.62])

Y0, Y1, RB = 0.22, 2.0, 0.80     # низ кроны, верхушка, радиус у основания

# Раскладка под размер окна — считается в set_layout(), руками не задаётся.
COLS = ROWS = W = H = 0          # сетка символов и размер кадра в px
SCALE = CX = CY = 0.0            # px на единицу мира; где на экране основание ёлки
HALF_W = SNOW_H = 0.0            # полуширина экрана и высота снегопада в единицах мира


def set_layout(width, height):
    """Сетка символов под окно: ёлка вписана по высоте, небо и земля — на всю ширину."""
    global COLS, ROWS, W, H, SCALE, CX, CY, HALF_W, SNOW_H
    COLS, ROWS = max(40, width // CW), max(36, height // CH)
    W, H = COLS * CW, ROWS * CH
    SCALE = min(H / 3.8, W / 2.7)
    CX, CY = W / 2, H * 0.735
    HALF_W = W / 2 / SCALE
    SNOW_H = max(3.3, 1.2 * CY / SCALE)


set_layout(*START_SIZE)
WEB = sys.platform == "emscripten"
DENSITY = 0.6 if WEB else 1.0     # в браузере (WebAssembly) numpy медленнее — точек меньше

# символы «по яркости»: порядок не важен — сортируются по реальной заливке глифа
RAMP = ".·:-~+=<>^*/÷×±≈≠≤≥√∞∑∏∫∂∆πλθ0123456789%&#@$"
EXTRA = " _|[]()°—ёЁ" + "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" \
        "абвгдежзийклмнопрстуфхцчшщъыьэюяАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
CHARSET = "".join(dict.fromkeys(" " + RAMP + EXTRA + GREETING))
IDX = {c: i for i, c in enumerate(CHARSET)}

WHITE = np.array([255, 255, 255.0])
GOLD = np.array([255, 200, 70.0])
RED = np.array([255, 60, 50.0])
BLUE = np.array([70, 120, 255.0])
GREEN = np.array([60, 220, 110.0])
PINK = np.array([255, 110, 200.0])
CYAN = np.array([110, 225, 255.0])
BULBS = [RED, GOLD, BLUE, WHITE, PINK, CYAN]

# тайминги сборки, секунды от нажатия кнопки
T_NEEDLES, T_GARLAND, T_LIGHTS, T_STAR, T_GIFTS, T_TEXT = 0.2, 5.4, 6.8, 8.4, 9.0, 11.0
STATIC, SWIRL, DROP, POP = 0, 1, 2, 3   # как точка появляется


# -------------------------------------------------------------------- сцена
def unit(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def envelope(y):
    """Радиус кроны на высоте y: конус с ярусами-«юбками»."""
    u = np.clip((np.asarray(y, float) - Y0) / (Y1 - Y0), 0, 1)
    tier = 0.86 + 0.26 * (1 - (u * 7) % 1)
    return RB * (1 - u) ** 0.92 * tier + 0.015


def bounce(e):
    n, d = 7.5625, 2.75
    return np.select(
        [e < 1 / d, e < 2 / d, e < 2.5 / d],
        [n * e * e, n * (e - 1.5 / d) ** 2 + 0.75, n * (e - 2.25 / d) ** 2 + 0.9375],
        n * (e - 2.625 / d) ** 2 + 0.984375)


# свойства точки: имя -> сколько чисел в нём хранится
FIELDS = {
    "pos": 3, "nrm": 3, "col": 3, "off": 2, "shaded": 1, "base": 1, "ao": 1, "birth": 1,
    "dur": 1, "mode": 1, "swirl": 1, "tw_f": 1, "tw_p": 1, "tw_a": 1, "fch": 1, "fall": 1,
    "sway": 1, "zbias": 1, "bulb": 1, "gain": 1, "fixed": 1,
}
# значения по умолчанию (pos и col задаются всегда)
DEFAULTS = {
    "nrm": (0, 1, 0), "off": 0, "shaded": 0, "base": 1, "ao": 1, "birth": -1e9, "dur": 1,
    "mode": STATIC, "swirl": 0, "tw_f": 0, "tw_p": 0, "tw_a": 0.38, "fch": -1, "fall": 0,
    "sway": 0, "zbias": 0, "bulb": 0, "gain": 1, "fixed": 0,
}


class Parts:
    """Копилка точек: у каждой позиция, нормаль, цвет и параметры анимации."""

    def __init__(self):
        self.chunks = {k: [] for k in FIELDS}

    def add(self, pos, col, **kw):
        n = len(pos)
        kw.update(pos=pos, col=col)
        for k, dim in FIELDS.items():
            v = np.asarray(kw.get(k, DEFAULTS.get(k)), float)
            self.chunks[k].append(np.broadcast_to(v.reshape(-1, dim) if v.ndim else v,
                                                  (n, dim)).copy())

    def finish(self):
        out = {k: np.concatenate(v) for k, v in self.chunks.items()}
        return {k: (v[:, 0] if v.shape[1] == 1 else v) for k, v in out.items()}


def build(seed=7):
    rng = np.random.default_rng(seed)
    q = Parts()

    # Земля и снег не вращаются вместе с ёлкой (fixed=1) и тянутся на всю ширину экрана.
    x_max = 1.35 * HALF_W + 0.1                            # с запасом на перспективу

    # заснеженная земля
    n = int(230 * (2 * x_max) * 4.8 * DENSITY)
    x, z = rng.uniform(-x_max, x_max, n), rng.uniform(-2.4, 2.4, n)
    base = 0.05 + 0.16 * rng.random(n) ** 2 + 0.16 * np.clip(1 - np.hypot(x, z) / 1.2, 0, 1)
    fch = np.select([base > 0.2, base > 0.12, base > 0.07], [IDX[":"], IDX["-"], IDX["·"]],
                    IDX["."])
    q.add(np.c_[x, 0.01 * rng.normal(size=n), z],
          np.array([150, 172, 220.0]), base=base, fch=fch, fixed=1)

    # ствол
    n = 320
    a, y = TAU * rng.random(n), 0.36 * rng.random(n)
    d = np.c_[np.cos(a), np.zeros(n), np.sin(a)]
    q.add(d * 0.065 + np.c_[np.zeros(n), y, np.zeros(n)], np.array([135, 88, 48.0]),
          nrm=d, shaded=1, ao=0.8, mode=SWIRL, birth=0.5 * rng.random(n), dur=1.0,
          swirl=rng.choice([-1, 1], n) * rng.uniform(2, 3, n))

    # хвоя: ярусы поникающих веток, снизу длиннее и гуще
    for i, y in enumerate(np.linspace(Y0 + 0.02, Y1 - 0.05, 26)):
        u = (y - Y0) / (Y1 - Y0)
        R = float(envelope(y)) + 0.04
        nb = int(7 + 13 * (1 - u))
        for b in range(nb):
            a = TAU * (b + 0.5 * rng.random()) / nb + i * 0.77
            L = R * rng.uniform(0.85, 1.08)
            n = int((20 + 100 * L) * DENSITY)
            s = rng.random(n) ** 0.6                       # 0 ствол .. 1 кончик
            d = np.array([np.cos(a), 0, np.sin(a)])
            side = np.array([-np.sin(a), 0, np.cos(a)])
            spread = (0.025 + 0.09 * s) * rng.normal(0, 1, n)
            p = d * (s * L)[:, None] + side * spread[:, None]
            p[:, 1] = y + 0.06 * s * L - 0.20 * (s * L) ** 2 + 0.014 * rng.normal(0, 1, n)
            nrm = unit(d * 0.75 + np.array([0, 0.55, 0]) + 0.3 * rng.normal(0, 1, (n, 3)))
            snow = (s > 0.5) & (rng.random(n) < 0.07 * (0.5 + s)) & (nrm[:, 1] > 0.3)
            green = (np.array([22, 135, 50.0]) + np.array([40, 95, 40.0]) * rng.random((n, 1))
                     + np.array([18, 0, 26.0]) * rng.random((n, 1)))
            q.add(p, np.where(snow[:, None], WHITE, green), nrm=nrm, shaded=1,
                  ao=np.where(snow, 1.25, 0.42 + 0.66 * s ** 1.3), mode=SWIRL, gain=TREE_BRIGHT,
                  birth=T_NEEDLES + 4.6 * u + 0.5 * rng.random(n), dur=1.3,
                  swirl=rng.choice([-1, 1]) * rng.uniform(2.0, 3.2, n))

    def on_surface(y, a, lift=0.0):
        r = envelope(y) + lift
        return np.c_[r * np.cos(a), y - 0.2 * (r * 0.8) ** 2, r * np.sin(a)]

    # золотая мишура: две спирали с бегущей волной яркости
    for ph in (0.0, np.pi):
        n = 800
        u = np.sort(rng.random(n))
        y = Y0 + 0.06 + u * (Y1 - Y0 - 0.16)
        q.add(on_surface(y, TAU * 5.5 * u + ph, 0.03) + 0.014 * rng.normal(size=(n, 3)), GOLD,
              base=0.78 + 0.2 * rng.random(n), mode=POP, birth=T_GARLAND + 1.6 * u,
              tw_f=2.2, tw_p=-u * 38 + ph, tw_a=0.22, zbias=0.06, gain=GARLAND_BRIGHT)

    # лампочки: две спирали между мишурой + россыпь
    n_sp, n_rnd = 110, 60
    u = np.r_[np.tile(np.linspace(0.02, 0.97, n_sp // 2), 2), rng.random(n_rnd) ** 1.3]
    a = np.r_[TAU * 5.5 * u[:n_sp] + np.repeat([np.pi / 2, 3 * np.pi / 2], n_sp // 2),
              TAU * rng.random(n_rnd)]
    n = n_sp + n_rnd
    y = Y0 + 0.05 + u * (Y1 - Y0 - 0.2)
    col = np.array(BULBS)[np.arange(n) % len(BULBS)]
    q.add(on_surface(y, a, 0.05), col, base=1.0, mode=POP, birth=T_LIGHTS + 1.5 * u,
          tw_f=rng.uniform(1.5, 5, n), tw_p=TAU * rng.random(n), zbias=0.09, bulb=1,
          gain=BULB_BRIGHT)

    # шары
    for k in range(26):
        y = rng.uniform(Y0 + 0.08, Y1 - 0.3)
        c = on_surface(np.array([y]), np.array([TAU * rng.random()]), 0.02)[0]
        nrm = unit(rng.normal(size=(60, 3)))
        q.add(c + 0.068 * nrm, [RED, GOLD, BLUE, np.array([215, 220, 235.0])][k % 4],
              nrm=nrm, shaded=1, ao=1.5, mode=POP, birth=T_GARLAND + 0.5 + 2.2 * rng.random(),
              zbias=0.08, gain=BALL_BRIGHT)

    # звезда: всегда повёрнута к зрителю (off — смещение уже в плоскости экрана)
    pts = rng.uniform(-0.3, 0.3, (9000, 2))
    rr, th = np.hypot(*pts.T), np.arctan2(pts[:, 1], pts[:, 0])
    f = (th - np.pi / 2) % (TAU / 5)
    f = np.minimum(f, TAU / 5 - f)
    ro, ri = 0.29, 0.115
    edge = ro * ri * np.sin(np.pi / 5) / (ro * np.sin(f) + ri * np.sin(np.pi / 5 - f))
    keep = np.flatnonzero(rr < edge)[:900]
    n = len(keep)
    core = np.clip(1 - rr[keep] / 0.2, 0, 1)[:, None]
    q.add(np.tile([0, Y1 + 0.21, 0.0], (n, 1)), GOLD + (WHITE - GOLD) * core * 0.8,
          off=pts[keep], base=0.85 + 0.3 * core[:, 0], mode=POP, birth=T_STAR,
          tw_f=3.0, tw_a=0.12, zbias=0.3, gain=STAR_BRIGHT)

    # подарки: коробки с лентами, падают с неба
    gifts = [(-0.98, 0.42, 0.30, 0.26, RED, GOLD), (0.95, 0.50, 0.34, 0.30, RED, WHITE),
             (-0.30, 1.02, 0.26, 0.22, BLUE, GOLD), (0.45, -1.00, 0.28, 0.24, GOLD, RED),
             (-0.85, -0.70, 0.24, 0.30, GREEN, RED)]
    for k, (gx, gz, w, h, c_box, c_rib) in enumerate(gifts):
        n = 620
        face = rng.integers(0, 5, n)                       # 0 верх, 1-4 бока
        uv = rng.uniform(-0.5, 0.5, (n, 2))
        loc, nrm = np.zeros((n, 3)), np.zeros((n, 3))
        for fc, (ax, sign) in enumerate([(1, 1), (0, 1), (0, -1), (2, 1), (2, -1)]):
            m = face == fc
            others = [i for i in range(3) if i != ax]
            loc[m, ax] = 0.5 * sign
            loc[m, others[0]], loc[m, others[1]] = uv[m, 0], uv[m, 1]
            nrm[m, ax] = sign
        ribbon = (np.abs(loc[:, 0]) < 0.09) | (np.abs(loc[:, 2]) < 0.09)
        yaw = rng.uniform(0, TAU)
        c, s = np.cos(yaw), np.sin(yaw)
        rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        p = (loc * [w, h, w]) @ rot.T + [gx, h / 2, gz]
        q.add(p, np.where(ribbon[:, None], c_rib, c_box), nrm=nrm @ rot.T, shaded=1,
              ao=1.15, mode=DROP, birth=T_GIFTS + 0.35 * k, dur=0.9,
              gain=np.where(ribbon, RIBBON_BRIGHT, GIFT_BRIGHT))

    # снег: падает всегда
    n = int(12 * (2 * x_max) * 4.2 * SNOW_H * SNOW_AMOUNT)
    size = rng.random(n)
    fch = np.select([size > 0.86, size > 0.45, size > 0.2], [IDX["*"], IDX["+"], IDX["·"]],
                    IDX["."])
    q.add(np.c_[rng.uniform(-x_max, x_max, n), SNOW_H * rng.random(n),
                rng.uniform(-2.1, 2.1, n)], WHITE,
          base=0.45 + 0.55 * size, fch=fch, gain=SNOW_BRIGHT, fixed=1,
          fall=(0.14 + 0.26 * size + 0.05 * rng.random(n)) * SNOW_SPEED,
          sway=0.03 + 0.07 * rng.random(n), tw_f=rng.uniform(0.6, 1.6, n),
          tw_p=TAU * rng.random(n))

    points = q.finish()
    points["jit"] = rng.uniform(-1, 1, len(points["birth"]))
    return points


class Scene:
    def __init__(self):
        self.P = build()
        self.rng = np.random.default_rng(1)
        rng = np.random.default_rng(3)
        # далёкие звёзды прямо в экранных координатах
        self.sky = (rng.integers(0, ROWS * 6 // 10, 70), rng.integers(0, COLS, 70),
                    TAU * rng.random(70))

    def render(self, t, tt, ang, ramp):
        """-> (сетка индексов символов, сетка цветов, сколько лампочек горит)."""
        P = self.P
        age = tt - P["birth"]
        vis = age >= 0
        e = np.clip(age / P["dur"], 0, 1)
        k = (1 - e) ** 3                                    # остаток пути (ease-out)
        swirl = P["mode"] == SWIRL

        x = P["pos"][:, 0] + P["sway"] * np.sin(t * P["tw_f"] * 1.3 + P["tw_p"])
        z = P["pos"][:, 2]
        y = np.where(P["fall"] > 0, (P["pos"][:, 1] - P["fall"] * t) % SNOW_H, P["pos"][:, 1])
        y = y + swirl * k * 0.9 + (P["mode"] == DROP) * 3.2 * (1 - bounce(e))
        spread = 1 + 2.6 * k * swirl

        # поворот вокруг вертикали (+ вихрь для летящих), наклон камеры, перспектива
        a = ang * (1 - P["fixed"]) + k * P["swirl"]
        ca, sa = np.cos(a), np.sin(a)
        xr, zr = (x * ca + z * sa) * spread, (-x * sa + z * ca) * spread
        cp, sp = np.cos(PITCH), np.sin(PITCH)
        y2, z2 = y * cp - zr * sp, y * sp + zr * cp
        f = CAM / (CAM - z2)
        col = np.floor((CX + (xr + P["off"][:, 0]) * f * SCALE) / CW).astype(int)
        row = np.floor((CY - (y2 + P["off"][:, 1]) * f * SCALE) / CH).astype(int)
        ok = vis & (col >= 0) & (col < COLS) & (row >= 0) & (row < ROWS)

        # освещение: Ламберт по повёрнутой нормали + затемнение дальней стороны
        c0, s0 = np.cos(ang), np.sin(ang)
        nx, ny, nz = P["nrm"].T
        lam = np.clip((nx * c0 + nz * s0) * LIGHT[0] + ny * LIGHT[1]
                      + (-nx * s0 + nz * c0) * LIGHT[2], 0, 1)
        fog = np.clip(0.66 + 0.42 * z2, 0.38, 1)
        twinkle = np.where(P["tw_f"] > 0,
                           1 - P["tw_a"] * (1 - np.sin(t * P["tw_f"] + P["tw_p"])), 1)
        b = np.where(P["shaded"] > 0, (0.40 + 0.62 * lam) * P["ao"] * fog, P["base"] * twinkle)
        b = b * P["gain"]
        b = b + (P["mode"] == POP) * 0.7 * np.clip(1 - age / 0.4, 0, 1)   # вспышка
        flying = swirl & (e < 1)
        b = np.where(flying, np.maximum(b, 0.5), b)

        nr = len(ramp) - 1
        ci = (np.clip(b + 0.09 * P["jit"], 0, 1) * nr).astype(int)
        ci = np.where(flying, self.rng.integers(nr // 3, nr + 1, len(b)), ci)
        ch = np.where(P["fch"] >= 0, P["fch"].astype(int), ramp[ci])
        rgb = P["col"] + (CYAN - P["col"]) * (0.75 * k * swirl)[:, None]
        rgb = np.clip(rgb * (0.24 + 0.95 * np.clip(b, 0, 1.25))[:, None], 0, 255)

        # z-буфер: пишем от дальних к ближним, в ячейке остаётся ближайшая точка
        ids = np.flatnonzero(ok)
        ids = ids[np.argsort((z2 + P["zbias"])[ids])]
        cell = row[ids] * COLS + col[ids]
        chars = np.zeros(ROWS * COLS, int)
        cols = np.zeros((ROWS * COLS, 3))
        chars[cell], cols[cell] = ch[ids], rgb[ids]

        # далёкие звёзды — только в пустых ячейках
        r, c, ph = self.sky
        cell = r * COLS + c
        cell, ph = cell[chars[cell] == 0], ph[chars[cell] == 0]
        chars[cell] = IDX["."]
        cols[cell] = np.array([120, 140, 190.0]) * (0.45 + 0.4 * np.sin(t * 1.3 + ph))[:, None]

        lit = int((vis & (P["bulb"] > 0)).sum())
        return chars.reshape(ROWS, COLS), cols.reshape(ROWS, COLS, 3), lit


# ------------------------------------------------------------------ рендер
def put_text(chars, cols, row, col, text, color, gain=1.0):
    for i, c in enumerate(text):
        if c != " " and 0 <= col + i < COLS and c in IDX:
            chars[row, col + i] = IDX[c]
            cols[row, col + i] = np.clip(np.asarray(color, float) * gain, 0, 255)


def load_font(px):
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("DejaVuSansMono.ttf", "font.ttf"):       # для веб-сборки кладётся рядом
        if os.path.exists(os.path.join(here, name)):
            return pygame.font.Font(os.path.join(here, name), px)
    return pygame.font.SysFont(MONO, px)


class Renderer:
    """Глифы заранее нарисованы белым; кадр = пачка блитов глифов x картинка цветов."""

    def __init__(self):
        font = load_font(FONT_PX)
        self.glyphs = []                                 # картинка ячейки для каждого символа
        cover = np.zeros(len(CHARSET))                   # какая доля ячейки закрашена
        have = np.zeros(len(CHARSET), bool)
        for i, c in enumerate(CHARSET):
            m = font.metrics(c)
            s = pygame.Surface((CW, CH))
            self.glyphs.append(s)
            if c == " " or not m or m[0] is None:
                continue
            g = font.render(c, True, (255, 255, 255), (0, 0, 0))
            s.blit(g, ((CW - g.get_width()) // 2, (CH - g.get_height()) // 2))
            cover[i] = pygame.surfarray.array3d(s).mean()
            have[i] = cover[i] > 0
        # шкала яркости: символы, которые есть в шрифте, по возрастанию заливки
        ids = np.array([IDX[c] for c in RAMP if have[IDX[c]]])
        self.ramp = ids[np.argsort(cover[ids], kind="stable")]
        self.resize()

    def resize(self):
        """Вызывать после set_layout(): холсты под новый размер кадра."""
        self.frame = pygame.Surface((W, H))
        self.ink = pygame.Surface((W, H))
        self.tint = pygame.Surface((COLS, ROWS))         # по одному пикселю цвета на ячейку

    def draw(self, chars, cols):
        r, c = np.nonzero(chars)                                     # только непустые ячейки
        glyphs = [self.glyphs[i] for i in chars[r, c].tolist()]
        spots = zip((c * CW).tolist(), (r * CH).tolist(), strict=True)
        self.ink.fill((0, 0, 0))
        self.ink.blits(list(zip(glyphs, spots, strict=True)), doreturn=False)   # белые символы
        pygame.surfarray.blit_array(self.tint, cols.astype(np.uint8).transpose(1, 0, 2))
        self.ink.blit(pygame.transform.scale(self.tint, (W, H)), (0, 0),
                      special_flags=pygame.BLEND_RGB_MULT)                      # и их цвета
        self.frame.fill(BG)
        self.frame.blit(self.ink, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        if GLOW > 0:                                                 # дешёвое свечение:
            near = pygame.transform.smoothscale(self.ink, (W // 3, H // 3))    # уменьшить,
            far = pygame.transform.smoothscale(near, (W // 9, H // 9))
            near.blit(pygame.transform.smoothscale(far, near.get_size()), (0, 0),
                      special_flags=pygame.BLEND_RGB_ADD)
            if GLOW < 1:
                g = int(255 * GLOW)
                near.fill((g, g, g), special_flags=pygame.BLEND_RGB_MULT)
            glow = pygame.transform.smoothscale(near, (W, H))                  # растянуть
            self.frame.blit(glow, (0, 0), special_flags=pygame.BLEND_RGB_ADD)  # и сложить
        return self.frame


def draw_frame(scene, rend, t, tt, ang, paused=False, fps=FPS):
    chars, cols, lit = scene.render(t, tt, ang, rend.ramp)
    dim, accent = (92, 102, 126), (255, 200, 96)

    if tt < 0:                                                       # ждём кнопку
        pulse = 0.65 + 0.35 * np.sin(t * 3.2)
        for dr, text, color in ((0, "[ SPACE ]  собрать ёлку", accent),
                                (2, "или кликни мышью", dim)):
            put_text(chars, cols, int(ROWS * 0.4) + dr, (COLS - len(text)) // 2, text, color,
                     pulse if dr == 0 else 1)
    elif tt > T_TEXT:                                                # поздравление по буквам
        text = " ".join(GREETING)
        x0 = (COLS - len(text)) // 2
        row = min(ROWS - 6, int((CY + 0.44 * SCALE) / CH))           # чуть ниже подарков
        for i, c in enumerate(text[:int((tt - T_TEXT) * 12)]):
            tint = (RED, GOLD, GREEN)[(i // 2 + int(t * 1.5)) % 3]
            put_text(chars, cols, row, x0 + i, c, tint, 0.85 + 0.25 * np.sin(t * 5 + i))

    symbols = int((chars > 0).sum())
    put_text(chars, cols, ROWS - 4, 1, "yolka.ascii" + ("   — пауза —" if paused else ""), dim)
    put_text(chars, cols, ROWS - 3, 1, f"rotation {np.degrees(ang) % 360:06.2f}°    lights {lit:3d}"
             f"    symbols {symbols:,}".replace(",", " ") + f"    fps {fps:2.0f}", dim)
    put_text(chars, cols, ROWS - 2, 1, "SPACE пауза · R заново · S скриншот · мышь вращать · Esc",
             (64, 72, 92))
    return rend.draw(chars, cols)


# -------------------------------------------------------------------- окно
def page_size():
    """Размер страницы браузера в px (только веб-версия)."""
    import platform  # в pygbag у platform есть window — окно браузера

    return int(platform.window.innerWidth), int(platform.window.innerHeight)


def frame_size(width, height):
    """Какого размера считать кадр для окна: на больших экранах — меньше, с растяжением."""
    s = max(1.0, height / MAX_H)
    return int(width / s), int(height / s)


async def main():
    pygame.init()
    web = WEB
    if web:
        set_layout(*frame_size(*page_size()))
        win = pygame.display.set_mode((W, H))
    else:
        desk_h = pygame.display.Info().current_h
        k = min(1.0, (desk_h - 110) / START_SIZE[1]) if desk_h > 0 else 1.0   # влезть в экран
        win = pygame.display.set_mode((int(START_SIZE[0] * k), int(START_SIZE[1] * k)),
                                      pygame.RESIZABLE)
        set_layout(*frame_size(*win.get_size()))
    pygame.display.set_caption("ASCII-ёлка")
    clock = pygame.time.Clock()
    scene, rend = Scene(), Renderer()
    frames = 0

    t, tt, drag = 0.0, -1.0, 0.0        # время сцены, время с начала сборки, поворот мышью
    paused, moved, running = False, 0.0, True

    def action():                        # кнопка: сначала сборка, потом пауза
        nonlocal tt, paused
        if tt < 0:
            tt = 0.0
        else:
            paused = not paused

    while running:
        dt = min(clock.tick(FPS) / 1000, 0.1) * SPEED
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                    action()
                elif ev.key == pygame.K_r:
                    tt, paused = 0.0, False
                elif ev.key == pygame.K_s and not web:
                    name = time.strftime("yolka_%Y%m%d_%H%M%S.png")
                    pygame.image.save(rend.frame, name)
                    print("saved", name)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                moved = 0.0
            elif ev.type == pygame.MOUSEMOTION and ev.buttons[0]:
                drag += ev.rel[0] * 0.008
                moved += abs(ev.rel[0])
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and moved < 4:
                action()

        # окно или страницу растянули — пересобрать сетку и сцену под новый размер
        win = pygame.display.get_surface()
        frames += 1
        if frames % 10 == 0:
            fw, fh = frame_size(*(page_size() if web else win.get_size()))
            if (max(40, fw // CW), max(36, fh // CH)) != (COLS, ROWS):
                set_layout(fw, fh)
                scene = Scene()
                rend.resize()
                if web:
                    import platform
                    win = pygame.display.set_mode((W, H))
                    platform.window.window_resize()      # страница заново растянет холст

        if not paused:
            t += dt
            if tt >= 0:
                tt += dt
        frame = draw_frame(scene, rend, t, tt, t * ROT_SPEED + drag, paused, clock.get_fps())

        ww, wh = win.get_size()
        s = min(ww / W, wh / H)
        win.fill(BG)
        if s < 1.02:                                                 # кадр почти в размер окна
            win.blit(frame, ((ww - W) // 2, (wh - H) // 2))
        else:                                                        # большой экран: растянуть
            size = (int(W * s), int(H * s))
            win.blit(pygame.transform.smoothscale(frame, size),
                     ((ww - size[0]) // 2, (wh - size[1]) // 2))
        pygame.display.flip()
        await asyncio.sleep(0)           # нужно для запуска в браузере (pygbag)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
