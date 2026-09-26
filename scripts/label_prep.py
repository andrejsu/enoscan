#!/usr/bin/env python3
"""
label_prep.py — предобработка фото винной этикетки для OCR и визуального поиска.

    кадр ─► [0] качество кадра
         ─► [1] сегментация: SAM (ONNX) → маска этикетки + маска бутылки
         ─► [2] геометрия: наклон по боковым краям, дуги верх/низ, радиус и ось
                по силуэту бутылки → решение «развёртывать цилиндр или нет»
         ─► [3] ресэмплинг: ОДИН проход remap из исходного кадра, родное разрешение
         ─► [4] нормализация: две ветки
                  visual.png — цвет сохранён (цвет этикетки — признак для поиска)
                  ocr.png    — серое, CLAHE, блики, полярность «тёмный текст на светлом»

Нужна ли развёртка цилиндра? Решается по кадру:
  • если края этикетки видны под углом ≤ 20° от оси бутылки, сжатие по краям ≤ 6%
    и развёртка ничего не даёт, зато ошибка в радиусе её испортит → только поворот;
  • если этикетка «заворачивает» за бок бутылки — развёртка нужна, иначе текст у краёв
    сжат в 1.5–3 раза, а строки изогнуты. Ничего не обрезается: у самых краёв
    (где полное выпрямление растянуло бы пиксели в 3–10 раз) растяжение
    ограничивается max_stretch (2.5×) — края остаются чуть сжатыми, но на месте.

Допущение: бутылка на фото стоит примерно вертикально (наклон до ±45°).
Этикетка вверх ногами не определяется геометрией — это проверяет OCR (0°/180°).

Зависимости:  pip install opencv-python numpy onnxruntime
Модель SAM ViT-B (~210 МБ) скачивается при первом запуске в ~/.cache/label_preprocess/

Запуск:
  python label_prep.py photo.jpg -o out/ --debug
  python label_prep.py f1.jpg f2.jpg f3.jpg -o out/          # выберет самый резкий кадр
  python label_prep.py photo.jpg --roi 215,130,230,330        # рамка от детектора
  python label_prep.py photo.jpg --mask label_mask.png        # своя маска
  python label_prep.py photo.jpg --unwrap never|auto|always
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Config:
    sam_dir: Path = Path.home() / ".cache" / "label_preprocess" / "sam_vit_b_quant"
    grid: int = 8
    unwrap: str = "auto"
    unwrap_min_angle: float = 20.0
    max_stretch: float = 2.5
    fallback_radius: float = 1.15
    visual_size: int = 512
    ocr_height: int = 1024
    max_upscale: float = 2.0
    clahe_clip: float = 1.5
    denoise_min_sigma: float = 3.0
    min_label_height: int = 400


def sharpness(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def noise_sigma(gray: np.ndarray) -> float:
    """σ гауссова шума, метод Immerkær (1996)."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    conv = cv2.filter2D(gray.astype(np.float32), -1, k)[1:-1, 1:-1]
    return float(np.sqrt(np.pi / 2) * np.abs(conv).mean() / 6)


SAM_URL = ("https://github.com/vietanhdev/anylabeling-assets/releases/download/"
           "v0.4.0/segment_anything_vit_b_quant-r20230416.zip")


def _find_models(d: Path):
    if not d.exists():
        return None, None
    return next(d.rglob("*encoder*.onnx"), None), next(d.rglob("*decoder*.onnx"), None)


def ensure_sam(model_dir: Path) -> tuple[Path, Path]:
    enc, dec = _find_models(model_dir)
    if enc and dec:
        return enc, dec
    model_dir.mkdir(parents=True, exist_ok=True)
    zpath = model_dir / "sam.zip"
    print(f"Скачиваю SAM ViT-B (~210 МБ) в {model_dir} ...", file=sys.stderr)
    urllib.request.urlretrieve(SAM_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(model_dir)
    zpath.unlink()
    return _find_models(model_dir)


def _mask_stats(m: np.ndarray) -> dict:
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea)
    (_, _), (rw, rh), _ = cv2.minAreaRect(c)
    return {"area": float(m.mean()),
            "fill": cv2.contourArea(c) / max(rw * rh, 1.0),
            "border": int(m[0].any()) + int(m[-1].any()) + int(m[:, 0].any()) + int(m[:, -1].any())}


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max((a | b).sum(), 1))


class Segmenter:
    """
    Кодировщик SAM запускается один раз на уменьшенной копии кадра (1024 по длинной
    стороне); все переборы кандидатов идут на масках того же размера — это быстро.
    Итоговая маска этикетки декодируется повторно уже в полном разрешении.
    """
    MEAN = np.array([123.675, 116.28, 103.53], np.float32)
    STD = np.array([58.395, 57.12, 57.375], np.float32)

    def __init__(self, cfg: Config):
        import onnxruntime as ort
        enc, dec = ensure_sam(cfg.sam_dir)
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.enc = ort.InferenceSession(str(enc), so, providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(dec), so, providers=["CPUExecutionProvider"])
        self.cfg = cfg

    def set_image(self, img: np.ndarray):
        self.full = img.shape[:2]
        s = 1024 / max(self.full)
        self.s = s
        self.work = (int(round(self.full[0] * s)), int(round(self.full[1] * s)))
        small = cv2.resize(img, self.work[::-1], interpolation=cv2.INTER_AREA)
        self.small_gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        x = (cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) - self.MEAN) / self.STD
        pad = np.zeros((1024, 1024, 3), np.float32)
        pad[:self.work[0], :self.work[1]] = x
        self.emb = self.enc.run(None, {"x": pad.transpose(2, 0, 1)[None]})[0]

    def decode(self, pts_work, labels, full_res=False):
        """pts_work — координаты в уменьшенном кадре. Возвращает (маски, iou)."""
        out = self.full if full_res else self.work
        m, iou, _ = self.dec.run(None, {
            "image_embeddings": self.emb,
            "point_coords": np.asarray(pts_work, np.float32)[None],
            "point_labels": np.asarray(labels, np.float32)[None],
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.zeros(1, np.float32),
            "orig_im_size": np.array(out, np.float32),
        })
        return m[0] > 0, iou[0]

    def _candidates(self) -> list[dict]:
        h, w = self.work
        lap = cv2.Laplacian(self.small_gray, cv2.CV_32F)
        cands: list[dict] = []
        for gy in np.linspace(0.08, 0.92, self.cfg.grid):
            for gx in np.linspace(0.08, 0.92, self.cfg.grid):
                masks, iou = self.decode([[gx * w, gy * h], [0, 0]], [1, -1])
                for i in range(1, len(iou)):
                    m = masks[i]
                    if iou[i] < 0.85 or not (0.01 <= m.mean() <= 0.7):
                        continue
                    dup = next((c for c in cands if _iou(c["mask"], m) > 0.9), None)
                    if dup:
                        continue
                    st = _mask_stats(m)
                    cands.append({"mask": m, "iou": float(iou[i]), "sharp": float(lap[m].var()), **st})
        return cands

    @staticmethod
    def _score(cands: list[dict]) -> dict:
        """
        Этикетка: прямоугольная, резкая, не касается края кадра, и внутри неё нет
        другого крупного прямоугольника (иначе это, скорее всего, бутылка).
        """
        med = np.median([c["sharp"] for c in cands]) + 1e-6
        for c in cands:
            inner = any(d is not c and 0.2 <= d["area"] / c["area"] <= 0.9 and d["fill"] >= 0.88
                        and (d["mask"] & c["mask"]).sum() / max(d["mask"].sum(), 1) > 0.9
                        for d in cands)
            c["score"] = (c["fill"] ** 4 * c["iou"] * np.sqrt(c["area"])
                          * min(c["sharp"] / med, 3.0) * 0.3 ** c["border"] * (0.4 if inner else 1.0))
        return max(cands, key=lambda c: c["score"])

    def _find_bottle(self, label: np.ndarray, cands: list[dict]) -> np.ndarray | None:
        """Ближайший «контейнер» этикетки: содержит её, но больше в 1.3–10 раз."""
        ys, xs = np.nonzero(label)
        cx, cy, hh = xs.mean(), ys.mean(), ys.max() - ys.min()
        pool = list(cands)
        for dy in (-0.5, 0.0, 0.5):
            masks, iou = self.decode([[cx, cy + dy * hh * 1.1], [0, 0]], [1, -1])
            pool += [{"mask": masks[i]} for i in range(1, len(iou)) if iou[i] > 0.7]
        la = label.sum()
        best = None
        for c in pool:
            m = c["mask"]
            ratio = m.sum() / max(la, 1)
            if 1.3 <= ratio <= 10 and (m & label).sum() / la > 0.9:
                if best is None or m.sum() < best.sum():
                    best = m
        return best

    def segment(self, img: np.ndarray, roi=None) -> tuple[np.ndarray, np.ndarray | None, dict]:
        self.set_image(img)
        cands: list[dict] = []
        if roi is not None:
            x, y, w, h = (v * self.s for v in roi)
            masks, iou = self.decode([[x, y], [x + w, y + h]], [2, 3])
            label_w = masks[int(np.argmax(iou))]
            info = {"mode": "box"}
        else:
            cands = self._candidates()
            if not cands:
                raise RuntimeError("Этикетка не найдена. Передайте рамку: --roi x,y,w,h")
            best = self._score(cands)
            label_w = best["mask"]
            info = {"mode": "auto", "candidates": len(cands), "score": round(float(best["score"]), 3)}

        bottle_w = self._find_bottle(label_w, cands)

        up = cv2.resize(label_w.astype(np.uint8), self.full[::-1], interpolation=cv2.INTER_NEAREST) > 0
        ys, xs = np.nonzero(label_w)
        masks, _ = self.decode([[xs.min(), ys.min()], [xs.max(), ys.max()]], [2, 3], full_res=True)
        ious = [_iou(m, up) for m in masks]
        label = masks[int(np.argmax(ious))] if max(ious) > 0.9 else up
        bottle = (cv2.resize(bottle_w.astype(np.uint8), self.full[::-1], interpolation=cv2.INTER_NEAREST) > 0
                  if bottle_w is not None else None)
        info["bottle_found"] = bottle is not None
        return clean_mask(label), bottle, info


def _largest_component(mask: np.ndarray) -> np.ndarray:
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 1:
        return mask.astype(bool)
    return lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))


def clean_mask(mask: np.ndarray) -> np.ndarray:
    """Крупнейшая компонента + заливка дыр от текста. Выпуклую оболочку НЕ берём —
    она спрямляет вогнутый край этикетки и уничтожает кривизну."""
    m = _largest_component(mask).astype(np.uint8) * 255
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(m)
    cv2.drawContours(out, cs, -1, 255, cv2.FILLED)
    return out > 0


def contour_points(mask: np.ndarray) -> np.ndarray:
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    return max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float64)


def rotate_pts(p: np.ndarray, c: np.ndarray, th: float) -> np.ndarray:
    """Кадр → «вертикальная» система: p' = R(θ)·(p − c)."""
    co, si = np.cos(th), np.sin(th)
    d = p - c
    return np.stack([co * d[:, 0] - si * d[:, 1], si * d[:, 0] + co * d[:, 1]], axis=1)


def unrotate_xy(x, y, c, th):
    """Обратно: «вертикальная» система → кадр."""
    co, si = np.cos(th), np.sin(th)
    return co * x + si * y + c[0], -si * x + co * y + c[1]


def _robust_line(t: np.ndarray, v: np.ndarray, iters=4, k=2.5):
    """v = a·t + b с отбрасыванием выбросов. Возвращает (a, b, доля инлаеров)."""
    keep = np.ones(len(t), bool)
    for _ in range(iters):
        a, b = np.polyfit(t[keep], v[keep], 1)
        r = v - (a * t + b)
        sig = 1.4826 * np.median(np.abs(r[keep])) + 0.5
        new = np.abs(r) < k * sig
        if new.sum() < 5 or np.array_equal(new, keep):
            break
        keep = new
    return a, b, keep.mean()


def side_profile(p: np.ndarray, lo=0.1, hi=0.9, bins=48):
    """Левый/правый край по горизонтальным полосам (средние 80% высоты)."""
    y0, y1 = np.quantile(p[:, 1], [lo, hi])
    edges = np.linspace(y0, y1, bins + 1)
    ys, L, R = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (p[:, 1] >= a) & (p[:, 1] < b)
        if sel.sum() >= 2:
            ys.append((a + b) / 2); L.append(p[sel, 0].min()); R.append(p[sel, 0].max())
    return np.array(ys), np.array(L), np.array(R)


def side_slope(p: np.ndarray) -> float:
    """Наклон боковых краёв (dx/dy); край, лучше лежащий на прямой, весит больше."""
    ys, L, R = side_profile(p)
    (al, _, ql), (ar, _, qr) = _robust_line(ys, L), _robust_line(ys, R)
    wl, wr = ql ** 4, qr ** 4
    return (al * wl + ar * wr) / (wl + wr)


def _edge_bins(p: np.ndarray, xl: float, xr: float, bins=64):
    x0, x1 = xl + 0.05 * (xr - xl), xr - 0.05 * (xr - xl)
    edges = np.linspace(x0, x1, bins + 1)
    xs, T, B = [], [], []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (p[:, 0] >= a) & (p[:, 0] < b)
        if sel.sum() >= 2:
            xs.append((a + b) / 2); T.append(p[sel, 1].min()); B.append(p[sel, 1].max())
    return np.array(xs), np.array(T), np.array(B)


def _fit_pair(xs, T, B, vx, iters=4, k=2.5):
    """
    Совместно: y_top = a_t·(x−vx)² + s·(x−vx) + c_t,  y_bot = a_b·(x−vx)² + s·(x−vx) + c_b.
    Кривизны свои у каждой дуги; общий только малый наклон s — остаточная
    ошибка оценки поворота (она одинаково наклоняет оба края).
    """
    n = len(xs)
    d = xs - vx
    X = np.zeros((2 * n, 5))
    X[:n, 0], X[n:, 1] = d ** 2, d ** 2
    X[:, 2] = np.tile(d, 2)
    X[:n, 3], X[n:, 4] = 1, 1
    Y = np.concatenate([T, B])
    keep = np.ones(2 * n, bool)
    for _ in range(iters):
        coef, *_ = np.linalg.lstsq(X[keep], Y[keep], rcond=None)
        r = Y - X @ coef
        sig = 1.4826 * np.median(np.abs(r[keep])) + 0.5
        new = np.abs(r) < k * sig
        if new.sum() < 8 or np.array_equal(new, keep):
            break
        keep = new
    return coef, float(np.sqrt(np.mean(r[keep] ** 2)))


def fit_arcs(p: np.ndarray, xl: float, xr: float, axis: float | None = None):
    """
    Верх и низ этикетки: y = a_top·(x − x0)² + c_top и y = a_bot·(x − x0)² + c_bot.

    Общая только вершина x0 — ось бутылки: обе дуги симметричны относительно неё.
    Кривизны РАЗНЫЕ: при съёмке с близкого расстояния работает перспектива —
    край выше уровня камеры выгибается вверх (∩), край ниже — вниз (∪), этикетка
    выглядит «бочкой». Наклон камеры добавляет к обеим дугам одинаковый изгиб.
    Итоговые знаки могут совпадать или быть разными — навязывать их нельзя.

    Если ось известна (по силуэту бутылки) — x0 фиксирован, иначе ищется перебором.
    """
    xs, T, B = _edge_bins(p, xl, xr)
    cands = [axis] if axis is not None else np.linspace(xl + 0.15 * (xr - xl), xr - 0.15 * (xr - xl), 29)
    best = None
    for vx in cands:
        coef, err = _fit_pair(xs, T, B, vx)
        if best is None or err < best[0]:
            best = (err, vx, coef)
    _, vx, (at, ab, sl, ct, cb) = best
    to_poly = lambda a, c: np.array([a, sl - 2 * a * vx, a * vx * vx - sl * vx + c])
    return to_poly(at, ct), to_poly(ab, cb), float(vx)


@dataclass
class Geometry:
    center: np.ndarray
    theta: float
    xl: float; xr: float
    top: np.ndarray; bot: np.ndarray
    axis: float; R: float
    radius_source: str
    th_l_raw: float; th_r_raw: float
    cylinder: bool
    max_stretch: float
    info: dict = field(default_factory=dict)


def estimate_geometry(label: np.ndarray, bottle: np.ndarray | None, cfg: Config) -> Geometry:
    p = contour_points(label)
    c = p.mean(axis=0)

    th = np.arctan(side_slope(p))
    for _ in range(2):
        th += np.arctan(side_slope(rotate_pts(p, c, th)))
    pu = rotate_pts(p, c, th)

    ys, L, R_ = side_profile(pu)
    xl, xr = float(np.median(L)), float(np.median(R_))
    y_lo, y_hi = np.quantile(pu[:, 1], [0.02, 0.98])

    axis, R, src = None, None, "fallback"
    if bottle is not None:
        pb = rotate_pts(contour_points(bottle), c, th)
        y_mid, hgt = (y_lo + y_hi) / 2, y_hi - y_lo
        sel = np.abs(pb[:, 1] - y_mid) < 0.3 * hgt
        if sel.sum() > 20:
            yb, Lb, Rb = side_profile(pb[sel], 0.0, 1.0, 24)
            w = float(np.quantile(Rb - Lb, 0.25))
            ax = float(np.median((Lb + Rb) / 2))
            if 0.95 * (xr - xl) <= w <= 3.0 * (xr - xl) and ax - w / 2 <= xl + 0.05 * w and ax + w / 2 >= xr - 0.05 * w:
                axis, R, src = ax, w / 2, "bottle_silhouette"

    top, bot, vx = fit_arcs(pu, xl, xr, axis)
    if axis is None:
        axis = vx
        R = max(axis - xl, xr - axis) * cfg.fallback_radius

    th_l_raw = float(np.arcsin(np.clip((axis - xl) / R, 0, 1)))
    th_r_raw = float(np.arcsin(np.clip((xr - axis) / R, 0, 1)))
    edge_deg = np.degrees(max(th_l_raw, th_r_raw))
    cylinder = {"always": True, "never": False}.get(cfg.unwrap, edge_deg > cfg.unwrap_min_angle)

    g = Geometry(c, float(th), xl, xr, top, bot, float(axis), float(R), src,
                 th_l_raw, th_r_raw, bool(cylinder), cfg.max_stretch)
    g.info = {
        "tilt_deg": round(float(np.degrees(th)), 2),
        "radius_px": round(float(R), 1), "radius_source": src,
        "edge_angles_deg": [round(float(np.degrees(th_l_raw)), 1), round(float(np.degrees(th_r_raw)), 1)],
        "unwrap": "cylinder" if cylinder else "flat",
        "edge_stretch_full": round(float(min(1 / max(np.cos(max(th_l_raw, th_r_raw)), 1e-3), 99)), 1) if cylinder else 1.0,
        "stretch_capped": bool(cylinder and 1 / max(np.cos(max(th_l_raw, th_r_raw)), 1e-3) > cfg.max_stretch),
        "arc_curvature": {"top": float(top[0]), "bottom": float(bot[0])},
    }
    return g


def resample(img: np.ndarray, g: Geometry) -> np.ndarray:
    hgt = float(np.polyval(g.bot, g.axis) - np.polyval(g.top, g.axis))
    out_h = int(round(hgt))
    if g.cylinder:
        xs = np.linspace(g.xl, g.xr, int(4 * (g.xr - g.xl)) + 2)
        sin_t = np.clip((xs - g.axis) / g.R, -1, 1)
        rate = np.minimum(1 / np.sqrt(np.maximum(1 - sin_t ** 2, 1e-9)), g.max_stretch)
        u = np.concatenate([[0], np.cumsum((rate[1:] + rate[:-1]) / 2 * np.diff(xs))])
        out_w = int(round(u[-1]))
        x = np.interp(np.linspace(0, u[-1], out_w), u, xs)
    else:
        out_w = int(round(g.xr - g.xl))
        x = np.linspace(g.xl, g.xr, out_w)
    if out_w < 16 or out_h < 16:
        raise RuntimeError("Этикетка слишком маленькая")
    yt, yb = np.polyval(g.top, x), np.polyval(g.bot, x)
    t = np.linspace(0, 1, out_h)[:, None]
    yu = yt[None, :] + t * (yb - yt)[None, :]
    xu = np.broadcast_to(x[None, :], yu.shape)
    mx, my = unrotate_xy(xu, yu, g.center, g.theta)
    return cv2.remap(img, mx.astype(np.float32), my.astype(np.float32),
                     interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)


def glare_mask(img: np.ndarray) -> np.ndarray:
    """
    Блики: почти пересвеченные пиксели, заметно ярче своего окружения.
    Второе условие важно — иначе белая бумага этикетки целиком сойдёт за блик.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = max(15, (min(gray.shape) // 20) | 1)
    local = cv2.medianBlur(gray, min(k, 255) if k <= 255 else 255)
    m = ((gray >= 245) & (gray.astype(np.int16) - local > 20)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return cv2.dilate(m, np.ones((5, 5), np.uint8))


def _resize(img, scale, max_up):
    if scale < 1:
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), scale
    scale = min(scale, max_up)
    if scale > 1.01:
        return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4), scale
    return img, 1.0


def normalize(flat: np.ndarray, cfg: Config) -> tuple[np.ndarray, np.ndarray, dict]:
    gray0 = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    sigma = noise_sigma(gray0)
    info = {"label_px": [int(flat.shape[1]), int(flat.shape[0])],
            "noise_sigma": round(sigma, 2), "sharpness": round(sharpness(gray0), 1)}

    base = flat
    if sigma > cfg.denoise_min_sigma:
        h = float(min(0.6 * sigma, 8.0))
        base = cv2.fastNlMeansDenoisingColored(flat, None, h, h, 7, 21)
        info["denoised"] = True

    s = cfg.visual_size / max(base.shape[:2])
    visual, _ = _resize(base, s, cfg.max_upscale)

    L = cv2.cvtColor(base, cv2.COLOR_BGR2LAB)[..., 0]
    gm = glare_mask(flat)
    info["glare_frac"] = round(float(gm.mean()), 3)
    if 0 < gm.mean() < 0.15:
        L = cv2.inpaint(L, gm, 3, cv2.INPAINT_TELEA)
    tiles = int(np.clip(round(min(L.shape) / 128), 2, 8))
    L = cv2.createCLAHE(cfg.clahe_clip, (tiles, tiles)).apply(L)
    thr, _ = cv2.threshold(L, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if (L > thr).mean() < 0.4:
        L = 255 - L
        info["inverted"] = True
    ocr, sc = _resize(L, cfg.ocr_height / L.shape[0], cfg.max_upscale)
    if sc <= 1.0:
        blur = cv2.GaussianBlur(ocr, (0, 0), 1.0)
        ocr = cv2.addWeighted(ocr, 1.4, blur, -0.4, 0)
    info["ocr_scale"] = round(float(sc), 2)
    return visual, ocr, info


def debug_segmentation(img, label, bottle):
    vis = img.copy()
    vis[label] = (0.5 * vis[label] + [0, 110, 0]).astype(np.uint8)
    t = max(2, int(max(img.shape[:2]) / 400))
    if bottle is not None:
        cs, _ = cv2.findContours(bottle.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, cs, -1, (255, 120, 0), t)
    return vis


def debug_geometry(img, g: Geometry):
    """Кадр, повёрнутый в «вертикальную» систему, с найденными краями, дугами и осью."""
    hgt = np.polyval(g.bot, g.axis) - np.polyval(g.top, g.axis)
    x0, x1 = min(g.xl, g.axis - g.R) - 0.1 * hgt, max(g.xr, g.axis + g.R) + 0.1 * hgt
    y0 = np.polyval(g.top, g.axis) - 0.25 * hgt
    y1 = np.polyval(g.bot, g.axis) + 0.25 * hgt
    W, H = int(x1 - x0), int(y1 - y0)
    xs, ys = np.meshgrid(np.arange(W) + x0, np.arange(H) + y0)
    mx, my = unrotate_xy(xs, ys, g.center, g.theta)
    vis = cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT)
    t = max(2, int(H / 300))
    X = np.linspace(g.xl, g.xr, 200)
    for poly, col in ((g.top, (0, 0, 255)), (g.bot, (255, 0, 0))):
        pts = np.stack([X - x0, np.polyval(poly, X) - y0], 1).astype(np.int32)
        cv2.polylines(vis, [pts], False, col, t)
    for x, col in ((g.xl, (0, 200, 255)), (g.xr, (0, 200, 255)), (g.axis, (0, 255, 255)),
                   (g.axis - g.R, (255, 120, 0)), (g.axis + g.R, (255, 120, 0))):
        cv2.line(vis, (int(x - x0), 0), (int(x - x0), H - 1), col, max(1, t // 2))
    return vis


def process(img: np.ndarray, cfg: Config, roi=None, mask=None, segmenter: Segmenter | None = None):
    warns: list[str] = []
    debug: dict[str, np.ndarray] = {}

    if mask is not None:
        label, bottle, seg = clean_mask(mask), None, {"mode": "external_mask"}
    else:
        label, bottle, seg = (segmenter or Segmenter(cfg)).segment(img, roi)
    st = _mask_stats(label)
    if st["fill"] < 0.8:
        warns.append(f"маска этикетки непрямоугольная (заполнение {st['fill']:.0%}) — проверьте 1_segmentation")
    if st["border"]:
        warns.append("этикетка касается края кадра — часть может быть обрезана")
    debug["1_segmentation"] = debug_segmentation(img, label, bottle)

    g = estimate_geometry(label, bottle, cfg)
    if g.info.get("stretch_capped") and g.info["edge_stretch_full"] > 1.5 * cfg.max_stretch:
        warns.append(f"этикетка заходит за бок бутылки — у краёв растяжение ограничено {cfg.max_stretch}×, "
                     "текст там останется немного сжатым")
    if g.radius_source == "fallback" and g.cylinder:
        warns.append("силуэт бутылки не найден, радиус оценён грубо — развёртка может растягивать края")
    debug["2_geometry"] = debug_geometry(img, g)

    flat = resample(img, g)
    debug["3_flat_native"] = flat
    if flat.shape[0] < cfg.min_label_height:
        warns.append(f"этикетка всего {flat.shape[0]} px по высоте — мелкий текст не восстановить, снимайте ближе")

    visual, ocr, norm = normalize(flat, cfg)
    if norm["glare_frac"] > 0.15:
        warns.append(f"много бликов ({norm['glare_frac']:.0%}) — смените угол съёмки")

    meta = {"segmentation": {**seg, "rect_fill": round(st["fill"], 3)},
            "geometry": g.info, "normalize": norm, "warnings": warns}
    return visual, ocr, meta, debug


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Предобработка фото винной этикетки")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    ap.add_argument("--roi", help="x,y,w,h — рамка этикетки от детектора")
    ap.add_argument("--mask", type=Path, help="готовая маска этикетки (белое = этикетка)")
    ap.add_argument("--unwrap", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--max-stretch", type=float, default=2.5,
                    help="предел растяжения у краёв при развёртке (больше — ровнее края, но мыльнее)")
    ap.add_argument("--ocr-height", type=int, default=1024)
    ap.add_argument("--max-upscale", type=float, default=2.0)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)

    frames = [cv2.imread(str(f)) for f in a.images]
    if any(f is None for f in frames):
        print("Не удалось прочитать изображение", file=sys.stderr)
        return 1
    idx = int(np.argmax([sharpness(f) for f in frames])) if len(frames) > 1 else 0
    img = frames[idx]

    cfg = Config(unwrap=a.unwrap, max_stretch=a.max_stretch, ocr_height=a.ocr_height, max_upscale=a.max_upscale)
    mask = None
    if a.mask:
        m = cv2.imread(str(a.mask), cv2.IMREAD_GRAYSCALE)
        mask = cv2.resize(m, img.shape[1::-1], interpolation=cv2.INTER_NEAREST) > 127
    roi = tuple(int(v) for v in a.roi.split(",")) if a.roi else None

    try:
        visual, ocr, meta, debug = process(img, cfg, roi=roi, mask=mask)
    except ImportError:
        print("Нужен onnxruntime: pip install onnxruntime (или передайте --mask)", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2

    a.out.mkdir(parents=True, exist_ok=True)
    stem = a.images[idx].stem
    cv2.imwrite(str(a.out / f"{stem}_visual.png"), visual)
    cv2.imwrite(str(a.out / f"{stem}_ocr.png"), ocr)
    if a.debug:
        for k, v in debug.items():
            cv2.imwrite(str(a.out / f"{stem}_{k}.png"), v)
    meta["source"] = str(a.images[idx])
    for w in meta["warnings"]:
        print(f"ВНИМАНИЕ: {w}", file=sys.stderr)
    try:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
