# -*- coding: utf-8 -*-
"""
GlowTrace-MM 证据图生成器（Pillow 版）

用途：生成 8 张演示用证据图（4 张案情图 + 3 张真实对照图 + 1 张图文不符图），
      与 annotations/bboxes/*.json 的归一化坐标严格对齐。
      画布尺寸与坐标框一一对应，生成后不要裁切或缩放。

运行（在数据集根目录 GlowTrace-MM 的上一级，或在任何位置用 --root 指定）：
    <python> tools/make_images.py
    <python> tools/make_images.py --root "D:\\欧莱雅黑客松\\GlowTrace-MM" --tigas "D:\\欧莱雅黑客松\\TIGAS_data\\TIGAS_data"

依赖：仅 Pillow（比赛运行环境已带 pillow 12.3.0）。
"""
from __future__ import annotations
import argparse, hashlib, math, os, random, shutil, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:  # Windows 控制台默认可能是 GBK，打印中文会炸，这里统一转 UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------- 真实照片纹理引擎
# 用磁盘上的真实照片替换程序生成的材质，让图片更具真实感。
# 纹理来源（按优先级）：
#   textures/product/ —— 从小红书等渠道下载的真实产品照片
#   textures/skin/    —— 真实皮肤纹理照片
#   TIGAS_data/real/  —— 真人面部照片（由 --tigas 传入路径）
#   素材/图片/         —— 用户提供的参考图片
# 找不到纹理时自动回退到程序生成，保证代码始终可运行。

_TEXTURE_CACHE: dict[str, Image.Image] = {}

# 全局 TIGAS 路径，由 main() 设置，所有 make_* 与纹理加载函数共享
TIGAS_ROOT: str | None = None

def _find_texture(candidates: list[str], size: tuple[int,int] | None = None,
                  crop_center: bool = True) -> Image.Image | None:
    """从文件列表中加载第一张存在的图片，缓存并缩放到 size。
    
    candidates: 候选绝对路径列表，按优先级排列。
    size:       目标尺寸 (w, h)，None 表示原尺寸。
    crop_center: True 时居中裁剪以匹配宽高比，否则拉伸。
    
    返回 Image 或 None（所有候选路径都不存在时）。
    """
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in _TEXTURE_CACHE:
            im = _TEXTURE_CACHE[norm]
            break
        if os.path.isfile(norm):
            try:
                im = Image.open(norm).convert("RGB")
                _TEXTURE_CACHE[norm] = im
                break
            except Exception:
                continue
    else:
        return None
    if size is None:
        return im.copy()
    tw, th = size
    if crop_center:
        iw, ih = im.size
        scale = max(tw / iw, th / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        im2 = im.resize((nw, nh), Image.LANCZOS)
        left = (nw - tw) // 2
        top = (nh - th) // 2
        return im2.crop((left, top, left + tw, top + th))
    else:
        return im.resize(size, Image.LANCZOS)

def load_real_face(tigas_root: str | None = None, size: tuple[int,int] | None = None,
                   face_id: str = "00002") -> Image.Image | None:
    """加载一张真实人脸照片，缩放到指定尺寸。
    
    搜索顺序：textures/skin/ → TIGAS_data/real/ → 素材/图片/
    tigas_root 为 None 时使用全局 TIGAS_ROOT。全部不可用时返回 None（走程序生成兜底）。
    size 为 None 时返回原图尺寸。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    candidates = []
    # 1) textures/skin/ —— 下载的高清皮肤/人脸特写
    skin_dir = os.path.join(project_root, "textures", "skin")
    if os.path.isdir(skin_dir):
        for f in sorted(os.listdir(skin_dir)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                candidates.append(os.path.join(skin_dir, f))
    # 2) TIGAS_data/real/
    root = tigas_root or TIGAS_ROOT
    if root:
        base = os.path.join(root, "real")
        for suffix in (".jpeg", ".jpg", ".png"):
            candidates.append(os.path.join(base, f"{face_id}{suffix}"))
    # 3) 素材/图片/
    mtl_base = r"D:\欧莱雅黑客松\素材\图片"
    for fname in ("real_001.jpg", "fake_001.jpg"):
        candidates.append(os.path.join(mtl_base, fname))
    return _find_texture(candidates, size, crop_center=True)

def load_real_product(tigas_root: str | None = None, size: tuple[int,int] | None = None,
                      variant: str = "default") -> Image.Image | None:
    """加载一张真实产品/商品照片，缩放到指定尺寸并做 photo_finish 处理。
    
    搜索顺序：textures/product/ → 素材/图片/ → TIGAS_data/real/
    tigas_root 为 None 时使用全局 TIGAS_ROOT。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    candidates = []
    # 1) textures/product/ —— 从小红书/Unsplash 下载的真实产品图
    product_dir = os.path.join(project_root, "textures", "product")
    if os.path.isdir(product_dir):
        for f in sorted(os.listdir(product_dir)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                candidates.append(os.path.join(product_dir, f))
    # 2) 素材/图片/
    mtl_base = r"D:\欧莱雅黑客松\素材\图片"
    for fname in ("fake_001.jpg", "real_001.jpg"):
        candidates.append(os.path.join(mtl_base, fname))
    # 3) TIGAS_data/real/（兜底，但 TIGAS 主要是人脸，优先级最低）
    root = tigas_root or TIGAS_ROOT
    if root:
        base = os.path.join(root, "real")
        for fname in ("00002.jpeg", "00003.jpeg", "00004.jpeg"):
            candidates.append(os.path.join(base, fname))
    im = _find_texture(candidates, size, crop_center=True)
    if im is not None:
        im = photo_finish(im, warmth=1.02, grain=5, vignette=0.12, seed=hash(variant) % 1000)
    return im

def load_real_skin_texture(size: tuple[int,int] | None = None, seed: int = 42,
                           tigas_root: str | None = None) -> Image.Image:
    """加载真实皮肤纹理照片。优先 textures/skin/，其次 TIGAS 面部图 / 素材，最后程序生成兜底。
    
    tigas_root 为 None 时使用全局 TIGAS_ROOT。size 为 None 时用 256×256 兜底。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    sz = size or (256, 256)
    candidates = []
    # 1) textures/skin/ —— 下载的皮肤/面部特写照片
    skin_dir = os.path.join(project_root, "textures", "skin")
    if os.path.isdir(skin_dir):
        for f in sorted(os.listdir(skin_dir)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                candidates.append(os.path.join(skin_dir, f))
    # 2) TIGAS_data/real/
    root = tigas_root or TIGAS_ROOT
    if root:
        base = os.path.join(root, "real")
        for i in range(2, 20):
            candidates.append(os.path.join(base, f"{i:05d}.jpeg"))
    # 3) 素材/图片/
    mtl_base = r"D:\欧莱雅黑客松\素材\图片"
    for fname in ("real_001.jpg", "fake_001.jpg"):
        candidates.append(os.path.join(mtl_base, fname))
    im = _find_texture(candidates, sz, crop_center=True)
    if im is not None:
        im = photo_finish(im, warmth=1.01, grain=4, vignette=0.08, seed=seed)
        return im
    # 4) 程序生成兜底
    return skin_patch((0, 0, sz[0], sz[1]), seed=seed)

# ---------------------------------------------------------------- 基础工具

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]
_font_cache: dict = {}

def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """按字号取中文字体；找不到就用 Pillow 默认位图字体兜底。"""
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    order = FONT_CANDIDATES[1::2] + FONT_CANDIDATES[0::2] if bold else FONT_CANDIDATES
    for path in order:
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size)
                _font_cache[key] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f

def rr(draw: ImageDraw.ImageDraw, box, r: int, fill=None, outline=None, width: int = 1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def _ramp(top, bottom) -> Image.Image:
    """1×256 的小渐变，用来放大或调色。"""
    r = Image.new("RGB", (1, 256))
    px = r.load()
    for i in range(256):
        t = i / 255
        px[0, i] = tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3))
    return r

def vgrad(size, top, bottom) -> Image.Image:
    """竖直渐变底。"""
    w, h = size
    return _ramp(top, bottom).resize((w, h), Image.BILINEAR)

def dgrad(size, c1, c2) -> Image.Image:
    """对角渐变（用于桌布/木纹底）。"""
    w, h = size
    m = Image.linear_gradient("L").transpose(Image.Transpose.TRANSPOSE).resize((w, h), Image.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), c2), Image.new("RGB", (w, h), c1), m)

def noise_layer(size, amount=26, seed=7) -> Image.Image:
    """细颗粒噪点（叠加到皮肤上模拟毛孔/绒毛）。"""
    w, h = size
    rnd = random.Random(seed)
    img = Image.new("L", (w, h))
    d = img.load()
    for y in range(h):
        for x in range(w):
            d[x, y] = 128 + rnd.randint(-amount, amount)
    return img

def paste_rr(base: Image.Image, box, r: int, fill_img: Image.Image):
    """把一张图按圆角矩形蒙版贴到 base 上（等价于 canvas 的 rr + fill + clip）。"""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    base.paste(fill_img.resize((w, h), Image.BILINEAR), (x0, y0), mask)

def _round_corner_mask(w: int, h: int, r: int) -> Image.Image:
    """创建一张圆角矩形灰度蒙版，供 paste 使用。"""
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    return mask

def _measure(f, text: str) -> float:
    try:
        return f.getlength(text)
    except Exception:
        return len(text) * (getattr(f, "size", 10) * 0.6)

def _text(d: ImageDraw.ImageDraw, xy, text, f, fill, anchor):
    """位图兜底字体不支持 anchor，这里统一吞掉异常。"""
    try:
        d.text(xy, text, font=f, fill=fill, anchor=anchor)
    except Exception:
        x, y = xy
        w = _measure(f, text)
        off = {"m": 0.5, "r": 1.0, "l": 0.0}.get(anchor[1] if len(anchor) > 1 else "l", 0.0)
        size = getattr(f, "size", 11)
        v = {"a": 1.0, "m": 0.5, "s": 0.15, "d": 0.8}.get(anchor[0] if anchor else "a", 1.0)
        d.text((x - w * off, y - size * v), text, font=f, fill=fill)

def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list:
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        t = cur + ch
        if _measure(f, t) > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines

def draw_text(d: ImageDraw.ImageDraw, xy, text, f, fill, anchor="la", max_w=None, lh=None):
    if max_w is None:
        _text(d, xy, text, f, fill, anchor)
        return 1
    lines = wrap(text, f, max_w)
    lh = lh or int(getattr(f, "size", 14) * 1.55)
    for i, ln in enumerate(lines):
        d.text((xy[0], xy[1] + i * lh), ln, font=f, fill=fill, anchor="la")
    return len(lines)

# ================================================================
# 材质与光：让「程序画出来的东西」看起来像拍出来的。
# 真实照片的观感主要来自四件事 —— 材质渐变、高光、接触阴影、浅景深。
# 这几层都做成可复现的（固定种子 / 纯几何），所以 MD5 仍然稳定。
# ================================================================

def shadow(base, box, blur=18, alpha=90, offset=(0, 6)):
    """接触阴影：在 box 下方铺一层模糊的暗椭圆。模糊在 1/4 分辨率上做，亮度近似、速度够快。"""
    x0, y0, x1, y1 = box
    pad = blur * 1.5
    w, h = max(2, int(x1 - x0)), max(2, int(y1 - y0))
    small = Image.new("L", (max(2, w // 4), max(2, h // 4)), 0)
    ImageDraw.Draw(small).ellipse([0, 0, small.width - 1, small.height - 1], fill=alpha)
    lay = small.filter(ImageFilter.GaussianBlur(max(1, blur / 4))).resize((w, h), Image.BILINEAR)
    region = base.crop((int(x0) + offset[0], int(y0) + offset[1],
                        int(x0) + offset[0] + w, int(y0) + offset[1] + h))
    base.paste(Image.composite(Image.new("RGB", (w, h), (26, 22, 24)), region, lay),
               (int(x0) + offset[0], int(y0) + offset[1]))

def hband(base, x0, x1, y0, y1, col0, col1, alpha=90):
    """竖直方向上的高光条（玻璃/塑料瓶身的反射）。用 1×H 的细条拉伸，避免逐行画。"""
    x0, x1, y0, y1 = int(x0), int(x1), int(y0), int(y1)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    strip = Image.new("RGB", (1, h))
    sd = ImageDraw.Draw(strip)
    for yy in range(h):
        t = yy / max(1, h - 1)
        sd.point((0, yy), fill=tuple(int(col0[k] * (1 - t) + col1[k] * t) for k in range(3)))
    mask = Image.new("L", (w, h), alpha)
    base.paste(Image.blend(base.crop((x0, y0, x1, y1)), strip.resize((w, h), Image.BILINEAR), 0.85),
               (x0, y0), mask)

def soft_ellipse(base, box, col, blur=6, alpha=110):
    """晕染用的软椭圆（腮红、泛红、反光）。同样在低分辨率上做模糊。"""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(2, x1 - x0), max(2, y1 - y0)
    small = Image.new("L", (max(2, w // 8), max(2, h // 8)), 0)
    ImageDraw.Draw(small).ellipse([0, 0, small.width - 1, small.height - 1], fill=alpha)
    lay = small.filter(ImageFilter.GaussianBlur(max(1, blur / 8))).resize((w, h), Image.BILINEAR)
    region = base.crop((x0, y0, x1, y1))
    base.paste(Image.composite(Image.new("RGB", (w, h), col), region, lay), (x0, y0))

def skin_patch(box, seed=11, tone=((248, 224, 206), (198, 146, 120)),
               flush=((207, 92, 84), (196, 108, 96)), bumps=14, gloss=0.0):
    """一块「皮肤特写」：径向肤色 + 毛孔 + 细纹 + 不均匀泛红 + 可选油光。

    同一 seed 与同一尺寸 → 像素完全一致，所以「四条共用同一张照片」这类证据仍然成立。
    """
    w, h = int(box[2]), int(box[3])
    tile = Image.new("RGB", (w, h), tone[1])
    td = ImageDraw.Draw(tile)
    for i in range(30, 0, -1):
        t = i / 30
        col = tuple(int(tone[0][k] * (1 - t) + tone[1][k] * t) for k in range(3))
        td.ellipse([w / 2 - w * 0.62 * t, h / 2 - h * 0.66 * t,
                    w / 2 + w * 0.62 * t, h / 2 + h * 0.66 * t], fill=col)
    rnd = random.Random(seed)
    for _ in range(int(w * h / 90)):
        ang = rnd.random() * 6.2832
        rad = rnd.random() ** 0.5
        px = w / 2 + w * 0.46 * rad * math.cos(ang)
        py = h / 2 + h * 0.50 * rad * math.sin(ang)
        r2 = 0.6 + rnd.random() * 1.1
        k = 0.55 + rnd.random() * 0.35
        col = tuple(int(tone[1][i] * k) for i in range(3))
        td.ellipse([px - r2, py - r2, px + r2, py + r2], fill=col)
    for _ in range(9):
        yy = h * (0.12 + rnd.random() * 0.76)
        x0 = w * (0.08 + rnd.random() * 0.18)
        td.arc([x0, yy - 16, x0 + w * 0.30, yy + 16], 200, 340,
               fill=tuple(int(tone[1][i] * 0.82) for i in range(3)), width=1)
    for _ in range(int(bumps)):
        cx = w * (0.22 + rnd.random() * 0.56)
        cy = h * (0.20 + rnd.random() * 0.58)
        rr_ = w * (0.035 + rnd.random() * 0.055)
        a = int(70 + rnd.random() * 90)
        col = flush[0] if rnd.random() < 0.6 else flush[1]
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([cx - rr_, cy - rr_ * 0.82, cx + rr_, cy + rr_ * 0.82],
                                   fill=col + (a,))
        tile = Image.alpha_composite(tile.convert("RGBA"), ov).convert("RGB")
    if gloss > 0:
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([w * 0.30, h * 0.16, w * 0.70, h * 0.40],
                                   fill=(255, 250, 244, int(60 * gloss)))
        tile = Image.alpha_composite(tile.convert("RGBA"), ov).convert("RGB")
    return tile

def photo_finish(img, warmth=1.0, grain=5, vignette=0.16, seed=7):
    """统一的「拍出来」收尾：2× 降采样 + 调色 + 噪点 + 暗角。

    噪点用「稀疏点 → 模糊 → 低透明度叠加」，暗角用「小尺寸渐变蒙版直接放大」，
    全程避开百万像素级高斯模糊，否则 13 张图要跑很久。
    """
    big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    if warmth != 1.0:
        r, g, b = big.split()
        r = r.point(lambda v: min(255, int(v * warmth)))
        b = b.point(lambda v: max(0, int(v * (2.0 - warmth))))
        big = Image.merge("RGB", (r, g, b))
    if grain:
        rnd = random.Random(seed)
        n = Image.new("L", (max(2, big.width // 3), max(2, big.height // 3)), 0)
        nd = ImageDraw.Draw(n)
        for _ in range(int(n.width * n.height / 14)):
            nd.point((rnd.randrange(n.width), rnd.randrange(n.height)), fill=rnd.randrange(60, 256))
        n = n.filter(ImageFilter.GaussianBlur(0.5)).resize(big.size, Image.BILINEAR)
        n = n.point(lambda v: min(26, int(v * 0.055)))
        big = Image.composite(Image.new("RGB", big.size, (255, 255, 255)), big, n)
    if vignette:
        v = Image.new("L", big.size, 0)
        ImageDraw.Draw(v).ellipse([-big.width * 0.20, -big.height * 0.20,
                                   big.width * 1.20, big.height * 1.20],
                                  fill=int(255 * vignette))
        vs = v.resize((max(2, big.width // 8), max(2, big.height // 8)), Image.BILINEAR)
        v = vs.filter(ImageFilter.GaussianBlur(5)).resize(big.size, Image.BILINEAR)
        big = Image.composite(Image.new("RGB", big.size, (26, 22, 24)), big, v)
    return big.resize(img.size, Image.LANCZOS)

def label_block(d, cx, cy, w, lines, sub=None):
    """商品标签的排版：主标题 / 英文 / 规格，字号层级拉开。"""
    _text(d, (cx, cy), lines[0], font(17, True), (48, 50, 56), "mm")
    if len(lines) > 1:
        _text(d, (cx, cy + 24), lines[1], font(11), (128, 132, 140), "mm")
    if sub:
        _text(d, (cx, cy + 42), sub, font(8), (160, 164, 172), "mm")

def product_bottle(base, cx, base_y, bw, bh, cap_col, body_col, label=("控油精华", "ACNE SERUM"),
                   cap_shape="disc", accent=None):
    """立式精华瓶：磨砂玻璃瓶身 + 瓶肩 + 高光条 + 瓶盖 + 标签 + 接触阴影。

    cap_col 决定「白盖 / 黑盖」这类可指认差异；返回瓶盖包围盒（供证据框对齐）。
    """
    bx = int(cx - bw / 2)
    by = int(base_y - bh)
    shadow(base, (bx + bw * 0.06, base_y - 10, bx + bw * 0.94, base_y + 16), blur=14, alpha=95)
    body = vgrad((int(bw), int(bh)), tuple(min(255, c + 26) for c in body_col), body_col)
    paste_rr(base, [bx, by, bx + bw, by + bh], max(4, int(bw * 0.14)), body)
    hband(base, bx + bw * 0.02, bx + bw * 0.20, by + bh * 0.06, by + bh * 0.98,
          tuple(int(c * 0.80) for c in body_col), tuple(int(c * 0.92) for c in body_col), alpha=120)
    hband(base, bx + bw * 0.80, bx + bw * 0.98, by + bh * 0.06, by + bh * 0.98,
          tuple(int(c * 0.92) for c in body_col), tuple(int(c * 0.78) for c in body_col), alpha=120)
    hband(base, bx + bw * 0.24, bx + bw * 0.34, by + bh * 0.10, by + bh * 0.92,
          (255, 255, 255), tuple(int(c * 0.86) for c in body_col), alpha=150)
    d = ImageDraw.Draw(base)
    d.polygon([(bx + bw * 0.06, by + bh * 0.10), (bx + bw * 0.94, by + bh * 0.10),
               (bx + bw * 0.90, by), (bx + bw * 0.10, by)],
              fill=tuple(int(c * 0.94) for c in body_col))
    # 瓶盖：A5 证据要量「左盖明显亮、右盖明显暗」，所以盖子必须足够大、够平坦，
    # 高光条也要压窄压暗，否则两块窄高光会把白盖与黑盖的均值拉得差不多。
    ch = max(14, int(bh * 0.28))
    cw = bw * 0.62
    cx0, cx1 = bx + bw / 2 - cw / 2, bx + bw / 2 + cw / 2
    cy1 = by + bh * 0.06
    cy0 = cy1 - ch
    if cap_shape == "disc":
        d.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(cw * 0.28), fill=cap_col)
        if ch <= 60:   # 小盖子才加高光；大盖子保持平坦，亮/暗差异才好量
            hband(base, cx0 + cw * 0.12, cx0 + cw * 0.32, cy0 + ch * 0.15, cy1 - ch * 0.10,
                  tuple(min(255, c + 26) for c in cap_col), cap_col, alpha=110)
    else:
        d.rectangle([cx0, cy0, cx1, cy1], fill=cap_col)
    lw = bw * 0.78
    lh = bh * 0.40
    lx = bx + bw / 2 - lw / 2
    ly = by + bh * 0.42
    d = ImageDraw.Draw(base)
    rr(d, [lx, ly, lx + lw, ly + lh], max(3, int(lw * 0.06)), fill=(252, 252, 253))
    d.rectangle([lx, ly, lx + lw, ly + lh * 0.10], fill=accent or (236, 238, 242))
    label_block(d, bx + bw / 2, ly + lh * 0.40, lw, label, sub="净含量 30ml")
    if accent:
        _text(d, (bx + bw / 2, ly + lh * 0.86), "DERMATOLOGICALLY TESTED", font(6), (168, 172, 180), "mm")
    return (cx0, cy0, cx1, cy1)

def photo_product(w, h, cap_col=(43, 47, 54), body_col=(240, 232, 236),
                  label=("柔雾", "粉底液"), seed=71, object_scale=0.62):
    """一张「实拍商品图」：木纹台面 + 柔光 + 真实产品照片 + 摄影收尾。

    完全确定性（固定种子 + 纯几何），所以同一参数两次调用 → 像素完全一致，
    「多个平台逐像素复用同一张底图」这条证据仍然成立。
    """
    shot = Image.new("RGB", (w, h), (206, 196, 184))
    sd = ImageDraw.Draw(shot)
    for i in range(max(8, int(h / 3))):
        yy = int(h * 0.36) + i * 3
        sd.line([(0, yy), (w, yy)], fill=(176, 148, 118) if i % 3 else (158, 130, 100))
    rp = random.Random(seed)
    for k in range(max(6, int(w / 12))):
        xx, yy = rp.random() * w, h * 0.36 + rp.random() * (h * 0.64)
        sd.line([(xx, yy), (xx + 14 + rp.random() * 30, yy)], fill=(146, 118, 92))
    soft_ellipse(shot, [w * 0.08, h * 0.02, w * 0.92, h * 0.62], (250, 242, 226), blur=40, alpha=170)
    shot = photo_finish(shot, warmth=1.04, grain=6, vignette=0.18, seed=seed)

    # 用真实产品照片替换程序生成的瓶身渲染
    bw = int(min(w, h) * object_scale)
    bh = int(bw * 1.55)
    real_prod = load_real_product(size=(bw, bh), variant=label[0])
    if real_prod is not None:
        # 将真实产品图合成到台面上
        px = int(w / 2 - bw / 2)
        py = int(h * 0.90 - bh)
        shadow(shot, (px + bw * 0.06, py + bh - 10, px + bw * 0.94, py + bh + 16), blur=14, alpha=95)
        shot.paste(real_prod, (px, py), _round_corner_mask(bw, bh, max(4, int(bw * 0.14))))
    else:
        # 兜底：程序生成瓶身
        product_bottle(shot, int(w / 2), int(h * 0.90), bw, bh, cap_col, body_col, label=label)
    return shot

# ---------------------------------------------------------------- ① 前后对比图 1200x800

def make_beforeafter(out_path: str):
    W, H = 1200, 800
    SEAM_X, X_L, W_L, X_R, W_R = 596, 0, 588, 612, 588
    random.seed(31)
    img = Image.new("RGB", (W, H), "#c9cfd4")
    d = ImageDraw.Draw(img)
    img.paste(vgrad((W_L, H), (238, 242, 245), (142, 151, 161)), (X_L, 0))
    d.polygon([(0, 640), (300, 470), (588, 610), (588, 800), (0, 800)], fill=(154, 163, 172))
    img.paste(vgrad((W_R, H), (255, 253, 251), (230, 222, 214)), (X_R, 0))

    def face_real(cx, cy, rw, rh, face_id, warm_bias=1.0):
        """用真实照片叠入指定位置。左冷光 / 右暖光通过 warm_bias 控制。"""
        fw, fh = rw * 2, rh * 2
        real = load_real_face(TIGAS_ROOT, (fw, fh), face_id=face_id)
        if real is not None:
            r0, g0, b0 = real.split()
            warm = warm_bias
            r = r0.point(lambda v: min(255, int(v * warm)))
            b = b0.point(lambda v: max(0, int(v * (2.0 - warm))))
            real = Image.merge("RGB", (r, g0, b))
            real = real.filter(ImageFilter.GaussianBlur(0.6))
            img.paste(real, (int(cx - rw), int(cy - rh)))
            return True
        return False

    used_real_left = face_real(300, 330, 196, 250, "00002", warm_bias=0.94)
    used_real_right = face_real(912, 330, 196, 250, "00002", warm_bias=1.06)
    if not used_real_left:
        def face_fallback(cx, cy, rw, rh, light, tone, blur, pores):
            layer = Image.new("RGB", (rw * 2, rh * 2), tone)
            ld = ImageDraw.Draw(layer)
            for i in range(28, 0, -1):
                t = i / 28
                col = tuple(int(light[k] * (1 - t) + tone[k] * t) for k in range(3))
                ld.ellipse([rw - rw * t, rh - rh * t, rw + rw * t, rh + rh * t], fill=col)
            if blur:
                layer = layer.filter(ImageFilter.GaussianBlur(2.4))
            img.paste(layer, (int(cx - rw), int(cy - rh)))
            d.ellipse([cx - rw * 0.52, cy - rh * 0.20, cx - rw * 0.24, cy - rh * 0.08], fill=(70, 40, 32))
            d.ellipse([cx + rw * 0.24, cy - rh * 0.20, cx + rw * 0.52, cy - rh * 0.08], fill=(70, 40, 32))
            d.ellipse([cx - rw * 0.28, cy + rh * 0.44, cx + rw * 0.28, cy + rh * 0.60], fill=(150, 60, 50))
            d.arc([cx - rw * 0.62, cy - rh * 0.42, cx - rw * 0.18, cy - rh * 0.24], 200, 340, fill=(70, 40, 32), width=3)
            d.arc([cx + rw * 0.18, cy - rh * 0.42, cx + rw * 0.62, cy - rh * 0.24], 200, 340, fill=(70, 40, 32), width=3)
            if pores:
                for _ in range(700):
                    ang = random.random() * 6.2832
                    rad = random.random() ** 0.5
                    px = cx + rw * 0.88 * rad * math.cos(ang)
                    py = cy + rh * 0.88 * rad * math.sin(ang)
                    r2 = 0.5 + random.random() * 0.9
                    d.ellipse([px - r2, py - r2, px + r2, py + r2], fill=(122, 82, 72))
        face_fallback(300, 330, 196, 250, (246, 217, 196), (201, 138, 108), False, True)

    soft_ellipse(img, [140, 392, 296, 492], (232, 150, 146), blur=16, alpha=120)

    if not used_real_right:
        def face_fallback2(cx, cy, rw, rh, light, tone, blur, pores):
            layer = Image.new("RGB", (rw * 2, rh * 2), tone)
            ld = ImageDraw.Draw(layer)
            for i in range(28, 0, -1):
                t = i / 28
                col = tuple(int(light[k] * (1 - t) + tone[k] * t) for k in range(3))
                ld.ellipse([rw - rw * t, rh - rh * t, rw + rw * t, rh + rh * t], fill=col)
            if blur:
                layer = layer.filter(ImageFilter.GaussianBlur(2.4))
            img.paste(layer, (int(cx - rw), int(cy - rh)))
            d.ellipse([cx - rw * 0.52, cy - rh * 0.20, cx - rw * 0.24, cy - rh * 0.08], fill=(70, 40, 32))
            d.ellipse([cx + rw * 0.24, cy - rh * 0.20, cx + rw * 0.52, cy - rh * 0.08], fill=(70, 40, 32))
            d.ellipse([cx - rw * 0.28, cy + rh * 0.44, cx + rw * 0.28, cy + rh * 0.60], fill=(150, 60, 50))
            d.arc([cx - rw * 0.62, cy - rh * 0.42, cx - rw * 0.18, cy - rh * 0.24], 200, 340, fill=(70, 40, 32), width=3)
            d.arc([cx + rw * 0.18, cy - rh * 0.42, cx + rw * 0.62, cy - rh * 0.24], 200, 340, fill=(70, 40, 32), width=3)
        face_fallback2(912, 330, 196, 250, (255, 242, 230), (214, 161, 132), True, False)
        ov = Image.new("RGB", (W_R, H), (255, 245, 234))
        img.paste(Image.blend(img.crop((X_R, 0, X_R + W_R, H)), ov, 0.30), (X_R, 0))

    # 摄影收尾：先在「照片层」上做降采样/调色/噪点/暗角，再画 UI（这样字还是锐的）
    img = photo_finish(img, warmth=1.02, grain=6, vignette=0.14, seed=31)

    # 两支试用装：左白盖 / 右黑盖。瓶盖刻意落在 (340,565,420,610) 与 (690,565,760,610) 内，
    # 让 A5「两侧瓶盖不是同一支」的像素证据仍然对得上。
    product_bottle(img, 378, 750, 104, 220, (243, 245, 247), (223, 230, 236),
                   label=("控油精华", "ACNE SERUM"))
    product_bottle(img, 726, 750, 104, 220, (36, 42, 48), (206, 215, 222),
                   label=("控油精华", "ACNE SERUM"))
    d = ImageDraw.Draw(img)

    # UI 栏
    d.rectangle([0, 0, W, 54], fill=(22, 24, 29))
    d.rectangle([0, H - 64, W, H], fill=(22, 24, 29))
    _text(d, (28, 27), "Day 1", font(26, True), (255, 255, 255), "lm")
    _text(d, (X_R + 28, 27), "Day 28", font(26, True), (255, 255, 255), "lm")
    _text(d, (28, 72), "侧逆光 · 阴天", font(15), (154, 163, 172), "la")
    _text(d, (X_R + 28, 72), "正面平光 · 暖白灯", font(15), (154, 163, 172), "la")
    _text(d, (28, H - 32), '@油皮自救指南　28天实测打卡Day28｜从"痘痘脸"到被同事问是不是去做了医美',
          font(17), (230, 237, 243), "lm")
    _text(d, (W - 28, H - 32), "原相机直出 · 没开滤镜", font(14), (255, 92, 92), "rm")
    # 拼接缝（A2 证据）
    d.rectangle([SEAM_X, 54, SEAM_X + 8, H - 64], fill=(20, 22, 26))
    d.rectangle([SEAM_X - 8, 54, SEAM_X - 4, H - 64], fill=(255, 92, 92))
    img.save(out_path)

# ---------------------------------------------------------------- ② AI 开箱图 1024x1024

def make_unboxing(out_path: str):
    """AI 生成的开箱图：瓶身印「烟酰胺 控油精华」，正文却讲「维C抗氧精华」。"""
    W = H = 1024
    random.seed(99)
    img = vgrad((W, H), (243, 236, 228), (222, 210, 198))
    d = ImageDraw.Draw(img)
    # 墙与台面的交界、台面的木纹（横纹，带深浅与断纹）
    d.rectangle([0, 560, W, H], fill=(198, 168, 136))
    for i in range(120):
        y = 560 + i * 4 + random.random() * 2
        col = (176, 146, 116) if i % 3 else (152, 122, 94)
        d.line([(0, y), (W, y)], fill=col, width=1 + int(random.random() * 2))
    for _ in range(90):                                   # 木纹里的短断纹
        x = random.random() * W
        y = 560 + random.random() * (H - 560)
        d.line([(x, y), (x + 18 + random.random() * 46, y)], fill=(138, 108, 82))
    # 台面近处的暖反光
    soft_ellipse(img, [70, 620, 950, 990], (246, 228, 202), blur=52, alpha=150)

    # 牛皮纸礼盒 + 开箱折盖 + 封箱胶带（AI 出图常见的「过于工整」结构）
    box = [140, 430, 700, 860]
    shadow(img, (box[0] + 20, box[3] - 24, box[2] - 10, box[3] + 34), blur=22, alpha=120)
    d = ImageDraw.Draw(img)
    d.polygon([(box[0], box[1]), (box[2], box[1]), (box[2] - 16, box[1] + 54), (box[0] + 16, box[1] + 54)],
              fill=(222, 202, 178))
    d.rectangle([box[0], box[1] + 52, box[2], box[3]], fill=(208, 186, 160))
    d.rectangle([box[0], box[1] + 52, box[0] + 14, box[3]], fill=(186, 164, 140))
    d.rectangle([box[0], box[1] + 52, box[2], box[1] + 58], fill=(240, 232, 220))
    d.rectangle([386, box[1] + 52, 458, box[3]], fill=(231, 196, 212))      # 缎带
    d.polygon([(386, box[1] + 52), (458, box[1] + 52), (444, box[1] + 34), (400, box[1] + 34)],
              fill=(221, 180, 200))
    # 盒内衬纸（粉色薄纸的褶皱）
    d.polygon([(box[0] + 22, box[1] + 62), (box[2] - 22, box[1] + 62),
               (box[2] - 40, box[1] + 128), (box[0] + 40, box[1] + 128)], fill=(246, 224, 232))

    # 立式精华瓶（材质渲染）+ 标签
    product_bottle(img, 812, 812, 148, 360, (43, 47, 54), (232, 214, 224),
                   label=("烟酰胺", "NIACINAMIDE 10%"), accent=(238, 214, 226))
    d = ImageDraw.Draw(img)
    # 瓶身把四行信息补全（净含量、检测宣称、以及那行过密的英文小字）
    _text(d, (812, 706), "控油精华", font(15, True), (59, 59, 59), "mm")
    _text(d, (812, 728), "NIACINAMIDE 10%", font(10), (122, 122, 122), "mm")
    _text(d, (812, 744), "净含量 30ml", font(9), (154, 154, 154), "mm")
    _text(d, (812, 762), "DERMATOLOGICALLY TESTED · HYPOALLERGENIC", font(7), (120, 120, 120), "mm")

    img = photo_finish(img, warmth=1.05, grain=6, vignette=0.18, seed=99)
    d = ImageDraw.Draw(img)
    rr(d, [800, 930, 990, 974], 10, fill=(255, 255, 255))
    _text(d, (895, 952), "AI 生成 · 演示用", font(13), (138, 138, 138), "mm")
    img.save(out_path)

# ---------------------------------------------------------------- ③ 四账号同图 1200x1600

ACCTS = [
    ("@小美不熬夜", "22:41", "肌活源 水杨酸净痘精华 30ml", (229, 139, 139)),
    ("@A护肤日记", "22:58", "肌活源 烟酰胺修护乳 100ml", (139, 176, 229)),
    ("@柠檬tea",   "23:12", "澜本 氨基酸洁面慕斯 150ml", (159, 212, 168)),
    ("@柒柒子",   "23:28", "素研集 玻尿酸补水面膜 10片", (211, 176, 229)),
]
BODY = "我用了第三天脸就红肿刺痛，已经停药了，客服一直让我先寄回检测，想问问有没有姐妹跟我一样？我们一起维权。"

# 三种投诉墙形态：同一批账号、同一张照片，差别只在「发布时间怎么摆」
ACCTS = {
    "dense": ACCTS,
    "staggered": [
        ("@小美不熬夜", "2026-02-16 21:03", "肌活源 水杨酸净痘精华 30ml", (229, 139, 139)),
        ("@A护肤日记", "2026-02-17 09:47", "肌活源 烟酰胺修护乳 100ml", (139, 176, 229)),
        ("@柠檬tea",   "2026-02-19 20:31", "澜本 氨基酸洁面慕斯 150ml", (159, 212, 168)),
        ("@柒柒子",   "2026-02-21 22:06", "素研集 玻尿酸补水面膜 10片", (211, 176, 229)),
    ],
}
ACCTS["fivestar"] = ACCTS["staggered"]

SUBTITLE = {
    "dense": "同一商品的 4 条用户反馈",
    "staggered": "4 个账号的投诉记录（跨 5 天）",
    "fivestar": "4 个账号的投诉记录（跨 5 天）",
}
SUBTITLE2 = {
    "dense": "4 条集中在 47 分钟内",
    "staggered": "4 条被摊到 4 个不同日期，但配图是同一个文件",
    "fivestar": "4 条分散发布，但历史评价与投诉结论互斥",
}
PHOTO_AT = {
    "dense": ["IMG_2026-02-18_2241.jpg"] * 4,
    "staggered": ["IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                  "IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                  "IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                  "IMG_2026-02-18_2241.jpg（拍摄于 02-18）"],
    "fivestar": ["IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                 "IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                 "IMG_2026-02-18_2241.jpg（拍摄于 02-18）",
                 "IMG_2026-02-18_2241.jpg（拍摄于 02-18）"],
}

def _shared_photo(img, box, seed=4242, zoom=1.0, jitter=False):
    """同一段绘制代码 + 固定种子 → 传同一个 seed 时两次调用的像素完全一致。

    传 jitter=True 时改成「同一张照片的不同裁切」（内容同源、取景略有偏移），
    用来复现「每条投诉的配图各不相同，靠图片哈希查不出来」这种手法。
    """
    x, y, w, h = [int(v) for v in box]
    if jitter:
        rnd0 = random.Random(seed)
        z = 1.0 + rnd0.random() * 0.12
        cap = 1.0 / z
        ox = rnd0.uniform(0, 1 - cap)
        oy = rnd0.uniform(0, 1 - cap)
        paste_box = (int(x - ox * w), int(y - oy * h), int(w / cap), int(h / cap))
    else:
        paste_box = (x, y, w, h)
    px, py, pw, ph = paste_box
    # 照片本体：真实皮肤纹理照片（优先 TIGAS 真人面部），固定种子可复现
    tile = load_real_skin_texture(size=(w, h), seed=seed)
    if jitter:
        tile = tile.resize((max(1, int(w / cap)), max(1, int(h / cap))), Image.LANCZOS)
    img.paste(tile, (px, py))
    ImageDraw.Draw(img).rectangle([x, y, x + w, y + h], outline=(216, 219, 224), width=2)

def make_complaint_wall(out_path: str, mode: str = "dense"):
    """投诉墙。mode 决定这一版展示的是哪一种造假手法：

      dense      4 条集中在 47 分钟内，配图是同一个文件（原始案例）
      staggered  4 条被摊到 5 个日期上，但配图仍然是同一个文件（时间一改就能绕开「集中发布」这条规则）
      fivestar   4 条分散发布，其中 @柠檬tea 自己的历史评价全是五星（靠账号历史打脸）
    """
    W, H = 1200, 1600
    img = Image.new("RGB", (W, H), (242, 243, 245))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 70], fill=(255, 255, 255))
    _text(d, (24, 34), "售后投诉 · " + SUBTITLE[mode], font(20, True), (22, 24, 29), "lm")
    _text(d, (24, 56), "按发布时间排序 · " + SUBTITLE2[mode], font(12), (139, 152, 165), "lm")
    if mode == "staggered":
        d.rectangle([0, 70, W, 300], fill=(255, 251, 247))
        d.rectangle([0, 296, W, 300], fill=(240, 222, 210))
        _shared_photo(img, (40, 92, 420, 292))
        d = ImageDraw.Draw(img)
        _text(d, (452, 104), "上方这张图 = 4 条投诉共用的同一张照片", font(17, True), (22, 24, 29), "la")
        _text(d, (452, 138), "拍摄时间 2026-02-18（原帖日期）", font(13), (139, 152, 165), "la")
        for k, (lab, val) in enumerate((("投诉覆盖日期", "2026-02-16 / 17 / 19 / 21"), ("发布时间", "四个不同日期"), ("照片数量", "1 张"))):
            _text(d, (452, 178 + k * 30), lab + "：" + val, font(13), (90, 96, 104), "la")
    top = [int(0.06 * H), int(0.27 * H), int(0.48 * H), int(0.69 * H)]
    CH = int(0.19 * H)
    for i, (name, ts, prod, col) in enumerate(ACCTS[mode]):
        y = top[i]
        rr(d, [24, y, W - 24, y + CH], 10, fill=(255, 255, 255))
        if mode == "fivestar":
            # 同一张照片的不同裁切：看起来是四张不同的照片，实际同源
            _shared_photo(img, (40, y + 10, 260, CH - 20), seed=5000 + i * 17, jitter=True)
        else:
            _shared_photo(img, (40, y + 10, 260, CH - 20))
        d = ImageDraw.Draw(img)
        d.ellipse([330 - 17, y + 34 - 17, 330 + 17, y + 34 + 17], fill=col)
        _text(d, (358, y + 28), name, font(17, True), (22, 24, 29), "la")
        _text(d, (358, y + 50), "已购 · " + prod, font(12), (139, 152, 165), "la")
        draw_text(d, (358, y + 80), BODY, font(14), (51, 56, 63), max_w=700, lh=23)
        _text(d, (W - 44, y + 30), ts, font(13), (139, 152, 165), "ra")
        if mode in ("dense", "fivestar") and i == 2:
            _text(d, (W - 44, y + 52), "历史评价全五星", font(11), (210, 153, 34), "ra")
        _text(d, (40, y + CH - 26), PHOTO_AT[mode][i], font(11), (120, 124, 130), "la")
        if mode in ("dense", "staggered"):
            _text(d, (40, y + CH - 10), "（4 条的配图都是这同一个文件）", font(11), (214, 74, 74), "la")
        else:   # fivestar：四张配图是同一张照片的不同裁切，肉眼看着并不一样
            _text(d, (40, y + CH - 10), "（四条配图肉眼不同，但同源）", font(11), (214, 74, 74), "la")
    if mode == "staggered":  # 同一张照片被投放到 4 个不同日期上
        for i in range(3):
            y1, y2 = top[i] + CH, top[i + 1]
            d.line([40, (y1 + y2) / 2, 300, (y1 + y2) / 2], fill=(214, 74, 74), width=2)
        _text(d, (W - 44, top[3] + CH - 46), "提交日期各不相同，但照片完全一致", font(12), (214, 74, 74), "ra")
    if mode == "fivestar":   # 同一天/同一账号的「五星好评」与「烂脸投诉」并列
        y3 = top[2] + CH
        d.line([330, y3 - 34, W - 44, y3 - 34], fill=(210, 153, 34), width=2)
        _text(d, (W - 44, y3 - 44), "同一账号 · 2026-02-18 19:02 五星好评（回购第三瓶）", font(12), (210, 153, 34), "ra")
    img.save(out_path)

def make_complaint_staggered(out_path: str):
    make_complaint_wall(out_path, "staggered")

def make_complaint_fivestar(out_path: str):
    make_complaint_wall(out_path, "fivestar")

# ---------------------------------------------------------------- ④ 三平台并排 1600x900

PANELS = [
    (30,   "小红书", "@美妆阿May", "2026-03-02  20:15", (255, 46, 77),  "#底妆 #粉底液 #测评 #干皮 #油皮"),
    (550,  "抖音",   "@Mia酱",     "2026-03-09  21:40", (22, 24, 29),    "#底妆分享 #粉底液 #好用 #测评"),
    (1070, "微博",   "@小鹿护肤",  "2026-03-15  19:05", (230, 162, 60),  "#底妆 #护肤 #测评 #种草"),
]
C_TEXT = "妆效是半哑光的柔雾质感，上脸不拔干，持妆六小时鼻翼才轻微出油。学生党和新手不用花大价钱试错。"

def make_platform_compare(out_path: str):
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), (236, 238, 241))
    d = ImageDraw.Draw(img)
    for x, pf, name, ts, col, tags in PANELS:
        y, w, h = 135, 500, 675
        desk = dgrad((w, h), (203, 183, 156), (168, 145, 122))
        dd = ImageDraw.Draw(desk)
        random.seed(777)
        for i in range(40):
            yy = i * (h / 40) + random.random() * 2
            dd.rectangle([0, yy, w, yy + 2 + random.random() * 3],
                         fill=(120, 95, 70) if i % 2 else (230, 210, 185))
        img.paste(desk, (x, y))
        d = ImageDraw.Draw(img)
        d.rectangle([x, y, x + w, y + 64], fill=(250, 250, 250))
        _text(d, (x + 18, y + 22), pf, font(18, True), col, "lm")
        _text(d, (x + 18, y + 50), name, font(14), (51, 56, 63), "lm")
        _text(d, (x + w - 18, y + 34), ts, font(13), (139, 152, 165), "rm")
        # 头像（第三个换猫）
        ac = (240, 196, 106) if pf == "微博" else ((229, 139, 139) if pf == "小红书" else (139, 176, 229))
        d.ellipse([x + w - 60, y + 28, x + w - 20, y + 68], fill=ac)
        if pf == "微博":
            _text(d, (x + w - 40, y + 48), "猫", font(16, True), (138, 106, 47), "mm")
        # 同源商品图
        bx, by, bw, bh = int(x + w * 0.30), int(y + 150), 200, 330
        img.paste(photo_product(bw, bh, label=("柔雾", "粉底液")), (bx, by))
        d = ImageDraw.Draw(img)
        draw_text(d, (x + 22, y + 540), C_TEXT, font(15), (43, 48, 56), max_w=456, lh=26)
        _text(d, (x + 22, y + 628), tags, font(13), (47, 127, 214), "la")
    # C2：小红书原始水印
    _text(d, (30 + 500 - 40, 135 + 675 - 34), "@美妆阿May", font(22, True), (255, 255, 255), "rm")
    _text(d, (30 + 500 - 40, 135 + 675 - 12), "拍摄花絮 · 原图直发", font(13), (235, 235, 235), "rm")
    # C2：抖音面板保留了同源的完整画面，但原水印位置是空的（对照小红书面板右下角）
    d.rectangle([866, 684, 984, 748], outline=(255, 92, 92), width=3)
    _text(d, (872, 716), "原水印被裁掉（此处为空）", font(12), (255, 92, 92), "lm")
    # C2：抖音面板左边缘的裁切像素带（原水印被裁切后留下的边）
    d.rectangle([550, 199, 556, 810], fill=(240, 238, 234))
    d.rectangle([556, 199, 560, 810], fill=(120, 95, 70))
    for yy in range(199, 810, 6):
        d.line([549, yy, 561, yy], fill=(255, 92, 92), width=1)
    # C3：微博面板用贴纸盖住原水印位置（与小红书面板右下角水印同位置）
    sx, sy, sw, sh = 1304, 706, 253, 162
    rr(d, [sx, sy, sx + sw, sy + sh], 16, fill=(247, 240, 228))
    _text(d, (sx + sw / 2, sy + 44), "今日份好物", font(20, True), (230, 162, 60), "mm")
    _text(d, (sx + sw / 2, sy + 78), "整理自网络 · 侵删", font(13), (138, 122, 95), "mm")
    _text(d, (sx + sw / 2, sy + 106), "@小鹿护肤", font(13), (138, 122, 95), "mm")
    _text(d, (sx + sw / 2, sy + 134), "贴纸盖住了原水印位置", font(11), (185, 166, 132), "mm")
    img.save(out_path)
    # C2 单独出一张：小红书首发原图（带原始水印），供 dataset_index 的第二个 image_path 引用
    src = os.path.join(os.path.dirname(out_path), "repost_c_source_watermarked.png")
    img.crop((30, 135, 530, 810)).save(src)

# ---------------------------------------- ⑩ 改了文案、没换图（三平台并排，文案相似度 ≈70%）

C2_TEXT = {
    "小红书": C_TEXT,
    "抖音": "妆感是柔雾半哑光，上脸不拔干，持妆六小时鼻翼才轻微出油。学生党试错成本低。",
    "微博": "柔雾半哑光的妆感，长时间下来鼻翼只轻微出油，上脸不拔干，学生党和新手不怕试错。",
}
C2_TAGS = {
    "小红书": "#底妆 #粉底液 #测评 #干皮 #油皮",
    "抖音": "#底妆分享 #粉底液 #好用 #测评",
    "微博": "#底妆 #护肤 #测评 #种草",
}

def make_repost_reworded(out_path: str):
    """三平台：文案被改写了，但画面是同一张图（不只是没有水印——像素级同源）。"""
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), (236, 238, 241))
    d = ImageDraw.Draw(img)
    for x, pf, name, ts, col, _tags in PANELS:
        y, w, h = 135, 500, 675
        desk = dgrad((w, h), (203, 183, 156), (168, 145, 122))
        dd = ImageDraw.Draw(desk)
        random.seed(777)
        for i in range(40):
            yy = i * (h / 40) + random.random() * 2
            dd.rectangle([0, yy, w, yy + 2 + random.random() * 3],
                         fill=(120, 95, 70) if i % 2 else (230, 210, 185))
        img.paste(desk, (x, y))
        d = ImageDraw.Draw(img)
        d.rectangle([x, y, x + w, y + 64], fill=(250, 250, 250))
        _text(d, (x + 18, y + 22), pf, font(18, True), col, "lm")
        _text(d, (x + 18, y + 50), name, font(14), (51, 56, 63), "lm")
        _text(d, (x + w - 18, y + 34), ts, font(13), (139, 152, 165), "rm")
        ac = (240, 196, 106) if pf == "微博" else ((229, 139, 139) if pf == "小红书" else (139, 176, 229))
        d.ellipse([x + w - 60, y + 28, x + w - 20, y + 68], fill=ac)
        if pf == "微博":
            _text(d, (x + w - 40, y + 48), "猫", font(16, True), (138, 106, 47), "mm")
        # 商品图：材质渲染 + 摄影收尾的「实拍图」（三平台逐像素同一个文件）
        bx, by, bw, bh = int(x + w * 0.30), int(y + 150), 200, 330
        img.paste(photo_product(bw, bh, label=("柔雾", "粉底液")), (bx, by))
        d = ImageDraw.Draw(img)
        # 三个面板的配图区域完全一致 → 用同一个红框标注
        d.rectangle([int(bx), int(by), int(bx) + bw, int(by) + bh], outline=(255, 92, 92), width=3)
        draw_text(d, (x + 22, y + 540), C2_TEXT[pf], font(15), (43, 48, 56), max_w=456, lh=26)
        _text(d, (x + 22, y + 628), C2_TAGS[pf], font(13), (47, 127, 214), "la")
    d = ImageDraw.Draw(img)
    _text(d, (30, 828), "三个平台的配图区域逐像素一致（红框内），只有正文与话题标签被改写：文字相似度约 70%，图片相似度 100%",
          font(16, True), (214, 74, 74), "la")
    _text(d, (30, 856), "改文案可以骗过「文案查重」，改不了底图：商品本体、桌面木纹、投影方向与噪点分布完全相同",
          font(13), (120, 124, 130), "la")
    img.save(out_path)

# ---------------------------------------- ⑪ 换号改名再发（相同底图 + 改名自述 + 评论被抓）

def make_repost_renamed(out_path: str):
    """投稿者把同一组图换账号、换昵称再发一次，还在评论里自述「原号改名了」。"""
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), (236, 238, 241))
    d = ImageDraw.Draw(img)
    hands = ["@小雨的梳妆台", "@小雨的梳妆台", "@柚子不熬夜"]
    profs = ["2026-03-08 19:40", "2026-03-12 21:15", "2026-03-02 20:15（原账号 @小鹿护肤）"]
    for k, (x, pf, name, ts, col, _tags) in enumerate(PANELS):
        y, w, h = 135, 500, 675
        desk = dgrad((w, h), (203, 183, 156), (168, 145, 122))
        dd = ImageDraw.Draw(desk)
        random.seed(777)
        for i in range(40):
            yy = i * (h / 40) + random.random() * 2
            dd.rectangle([0, yy, w, yy + 2 + random.random() * 3],
                         fill=(120, 95, 70) if i % 2 else (230, 210, 185))
        img.paste(desk, (x, y))
        d = ImageDraw.Draw(img)
        d.rectangle([x, y, x + w, y + 64], fill=(250, 250, 250))
        _text(d, (x + 18, y + 22), pf, font(18, True), col, "lm")
        _text(d, (x + 18, y + 50), hands[k], font(14), (51, 56, 63), "lm")
        _text(d, (x + w - 18, y + 34), profs[k], font(13), (139, 152, 165), "rm")
        ac = (240, 196, 106) if pf == "微博" else ((229, 139, 139) if pf == "小红书" else (139, 176, 229))
        d.ellipse([x + w - 60, y + 28, x + w - 20, y + 68], fill=ac)
        if pf == "微博":
            _text(d, (x + w - 40, y + 48), "猫", font(16, True), (138, 106, 47), "mm")
        bx, by, bw, bh = int(x + w * 0.30), int(y + 150), 200, 330
        img.paste(photo_product(bw, bh, label=("柔雾", "粉底液")), (bx, by))
        d = ImageDraw.Draw(img)
        draw_text(d, (x + 22, y + 540), C2_TEXT[pf], font(15), (43, 48, 56), max_w=456, lh=26)
        _text(d, (x + 22, y + 628), C2_TAGS[pf], font(13), (47, 127, 214), "la")
        d.rectangle([bx, by, bx + bw, by + bh], outline=(255, 92, 92), width=3)
    d = ImageDraw.Draw(img)
    _text(d, (30, 826), "底图仍然逐像素一致；但面板上的署名与时间对不上——画面最早的一条（03-02）反而挂在「原账号」名下",
          font(15, True), (214, 74, 74), "la")
    _text(d, (30, 852), "评论区（抖音面板下方）：「这张图 @小鹿护肤 两周前就发过吧」　作者回复：「是我，原号改名了」",
          font(13), (60, 64, 72), "la")
    img.save(out_path)

def _status_bar(img, d, w, y=0, fg=(38, 40, 46)):
    """手机状态栏：信号 / WiFi / 电量。真实感的第一眼就来自这一条。"""
    d.rectangle([0, y, w, y + 46], fill=(252, 253, 254))
    for k in range(4):
        h = 8 + k * 4
        d.rounded_rectangle([28 + k * 11, y + 30 - h, 34 + k * 11, y + 30], radius=2, fill=fg)
    d.arc([96, y + 12, 126, y + 40], 300, 60, fill=fg, width=3)
    d.ellipse([106, y + 26, 116, y + 36], fill=fg)
    d.rounded_rectangle([w - 78, y + 14, w - 40, y + 34], radius=5, outline=fg, width=2)
    d.rectangle([w - 74, y + 18, w - 48, y + 30], fill=fg)
    d.rectangle([w - 38, y + 20, w - 34, y + 28], fill=fg)
    _text(d, (w / 2, y + 24), "9:41", font(13, True), fg, "mm")

def _nav_icons(d, x, y, col=(52, 54, 60), gap=62):
    """评论区那排图标：点赞 / 收藏 / 评论 / 分享（用几何近似，不用 emoji）。"""
    d.ellipse([x, y, x + 22, y + 22], outline=col, width=2)
    d.polygon([(x + 11, y + 6), (x + 17, y + 12), (x + 5, y + 12)], fill=col)
    x2 = x + gap
    d.polygon([(x2, y + 2), (x2 + 20, y + 2), (x2 + 20, y + 16), (x2 + 8, y + 16),
               (x2 + 2, y + 22), (x2 + 2, y + 16), (x2, y + 16)], outline=col, width=2)
    x3 = x + gap * 2
    d.polygon([(x3 + 10, y), (x3 + 20, y + 10), (x3 + 10, y + 20), (x3, y + 10)], outline=col, width=2)
    x4 = x + gap * 3
    d.line([(x4, y + 16), (x4 + 18, y + 2)], fill=col, width=2)
    d.line([(x4, y + 16), (x4 + 18, y + 20)], fill=col, width=2)

def _phone(w=800, h=1180):
    """小红书风格的单条笔记页：状态栏 + 顶部导航 + 大图 + 正文 + 标签 + 底部互动栏。"""
    img = Image.new("RGB", (w, h), (247, 248, 250))
    d = ImageDraw.Draw(img)
    _status_bar(img, d, w)
    d.rectangle([0, 46, w, 100], fill=(252, 253, 254))
    rr(d, [28, 60, 76, 88], 14, fill=(240, 242, 246))
    d.ellipse([38, 68, 50, 80], fill=(120, 126, 134))
    d.line([(41, 77), (52, 66)], fill=(120, 126, 134), width=2)
    _text(d, (w / 2, 74), "笔记详情", font(15, True), (38, 40, 46), "mm")
    d.ellipse([w - 74, 64, w - 46, 92], fill=(244, 245, 248))
    d.ellipse([w - 156, 64, w - 128, 92], fill=(244, 245, 248))
    d.ellipse([w - 142, 76, w - 138, 80], fill=(60, 64, 70))
    d.rectangle([w - 148, 76, w - 132, 79], fill=(60, 64, 70))
    d.rectangle([0, 100, w, 105], fill=(238, 240, 244))
    return img, d

def make_control_unboxing(out_path: str):
    """负样本 A：真实开箱晒单 —— 有时间线、无修图、正文主动标注赠品。"""
    W, H = 800, 1180
    img, d = _phone(W, H)
    # 大图：台灯下的真实产品照（木桌面 + 真实产品照片 + 柔光）
    ph0, ph1 = 130, 706
    d.rounded_rectangle([32, ph0, W - 32, ph1], radius=18, fill=(206, 196, 186))
    shot = Image.new("RGB", (W - 64, ph1 - ph0), (206, 196, 186))
    sd = ImageDraw.Draw(shot)
    for i in range(120):
        yy = 250 + i * 3.6
        sd.line([(0, yy), (shot.width, yy)], fill=(176, 148, 118) if i % 3 else (158, 130, 100))
    for _ in range(50):
        xx, yy = random.random() * shot.width, 250 + random.random() * (shot.height - 250)
        sd.line([(xx, yy), (xx + 30 + random.random() * 40, yy)], fill=(146, 118, 92))
    soft_ellipse(shot, [60, 20, shot.width - 60, 420], (250, 240, 220), blur=60, alpha=190)
    shot = photo_finish(shot, warmth=1.05, grain=6, vignette=0.20, seed=41)
    # 用真实产品照片替换程序生成的瓶身
    real_prod = load_real_product(size=(210, 240), variant="control_unbox")
    if real_prod is not None:
        px, py = int(shot.width / 2 - 105), int(580 - 240)
        shadow(shot, (px + 12, py + 230, px + 198, py + 256), blur=14, alpha=95)
        shot.paste(real_prod, (px, py), _round_corner_mask(210, 240, 16))
    else:
        product_bottle(shot, shot.width / 2, 580, 210, 240, (58, 62, 70), (246, 240, 238),
                       label=("粉底液", "30ml"), accent=(240, 226, 224))
    img.paste(shot, (32, ph0))
    d = ImageDraw.Draw(img)
    _text(d, (W - 62, ph0 + 26), "1/3", font(12, True), (255, 255, 255), "ra")
    _text(d, (400, ph0 + 500), "首发 2026-09-12 20:41", font(13), (250, 250, 250), "mm")
    _text(d, (400, ph0 + 522), "实拍：台灯下原图，无滤镜无磨皮", font(12), (120, 120, 126), "mm")
    # 作者行
    d.ellipse([36, 726, 88, 778], fill=(198, 176, 168))
    _text(d, (104, 740), "小满·干皮护肤记录", font(15, True), (34, 38, 44), "lm")
    _text(d, (104, 764), "关注", font(12), (255, 92, 92), "lm")
    d.rounded_rectangle([W - 106, 736, W - 34, 768], radius=16, outline=(255, 92, 92), width=2)
    _text(d, (W - 70, 752), "+ 关注", font(12, True), (255, 92, 92), "mm")
    # 正文
    lines = ["干皮自用两支的成绩单，没有修图，毛孔和干纹都在。",
             "上脸偏干，鼻翼会轻微起皮，需要先上保湿。",
             "利益相关：品牌方寄的样品，没收钱，说不好的地方也照说。"]
    y = 800
    for ln in lines:
        n = draw_text(d, (40, y), ln, font(16), (34, 38, 44), max_w=W - 80, lh=26)
        y += max(1, n) * 26 + 6
    d.rounded_rectangle([40, y + 4, 300, y + 46], radius=12, fill=(240, 242, 246))
    _text(d, (170, y + 25), "#真实开箱  #干皮粉底", font(13), (110, 114, 120), "mm")
    # 底部互动栏
    d.rectangle([0, H - 74, W, H], fill=(255, 255, 255))
    d.rectangle([0, H - 74, W, H - 72], fill=(236, 238, 242))
    d.rounded_rectangle([36, H - 58, 320, H - 18], radius=20, fill=(244, 245, 248))
    _text(d, (58, H - 38), "说点什么…", font(13), (150, 154, 160), "lm")
    _nav_icons(d, 430, H - 56)
    img.save(out_path)

def make_control_complaint(out_path: str):
    """负样本 B：真实投诉 —— 订单号齐、时间分散、有客服对话。"""
    W, H = 800, 1180
    img, d = _phone(W, H)
    # 唯一的一张现场照：浴室白光下的泛红特写（无修图）
    d.rounded_rectangle([32, 130, W - 32, 520], radius=18, fill=(232, 226, 222))
    shot = load_real_skin_texture(size=(W - 64, 390), seed=77)
    shot = photo_finish(shot, warmth=1.0, grain=7, vignette=0.24, seed=77)
    img.paste(shot, (32, 130))
    d = ImageDraw.Draw(img)
    _text(d, (400, 536), "本人照片，拍摄于 2026-02-13", font(13), (130, 134, 140), "mm")
    # 订单详情行
    rows = [("订单号", "2026020937710284", (34, 38, 44)),
            ("下单 / 收货", "2026-02-09 下单 · 2026-02-11 收货", (34, 38, 44)),
            ("首次使用", "2026-02-12 晚首次上脸（耳后测试无反应）", (34, 38, 44)),
            ("客服受理", "2026-02-13 中午受理，提供退款入口", (28, 118, 76)),
            ("退款状态", "2026-02-14 上午已原路退回", (28, 118, 76))]
    y = 590
    for k, v, c in rows:
        d.rounded_rectangle([32, y, W - 32, y + 68], radius=12, fill=(255, 255, 255))
        _text(d, (52, y + 34), k, font(14, True), (130, 134, 140), "lm")
        _text(d, (200, y + 34), v, font(14), c, "lm")
        y += 72
    # 客服对话气泡
    d.rounded_rectangle([32, y + 6, W - 32, y + 190], radius=12, fill=(255, 255, 255))
    d.rounded_rectangle([52, y + 22, 520, y + 76], radius=14, fill=(244, 245, 248))
    draw_text(d, (70, y + 38), "用了两天脸颊泛红，能退吗？附订单截图。", font(14), (34, 38, 44), max_w=430, lh=24)
    d.rounded_rectangle([240, y + 92, W - 52, y + 166], radius=14, fill=(212, 238, 220))
    draw_text(d, (258, y + 106), "已为您申请退款，产品不用寄回，请注意查收。", font(14), (28, 92, 60), max_w=470, lh=24)
    img.save(out_path)

def make_control_repost(out_path: str):
    """负样本 C：真实跨平台同步 —— 同名同头像、注明首发、文案有改写。"""
    W, H = 1200, 900
    img = Image.new("RGB", (W, H), (240, 242, 245))
    d = ImageDraw.Draw(img)
    panels = [("小红书", "@Cici的实验室", "2026-03-02 20:15", "小红书首发"),
              ("抖音",   "@Cici的实验室", "2026-03-09 21:40", "同步更新"),
              ("微博",   "@Cici的实验室", "2026-03-15 19:05", "同步更新")]
    # 同一张实拍图（三平台共用，但这是作者自己的号 —— 负样本的关键差别）
    shot = Image.new("RGB", (302, 360), (228, 226, 224))
    sd = ImageDraw.Draw(shot)
    for i in range(90):
        yy = 120 + i * 2.7
        sd.line([(0, yy), (shot.width, yy)], fill=(178, 152, 124) if i % 3 else (160, 134, 106))
    soft_ellipse(shot, [30, 10, 272, 250], (250, 244, 232), blur=44, alpha=180)
    shot = photo_finish(shot, warmth=1.04, grain=6, vignette=0.20, seed=52)
    real_prod = load_real_product(size=(112, 220), variant="control_repost")
    if real_prod is not None:
        px, py = int(151 - 112 / 2), int(330 - 220)
        shadow(shot, (px + 6, py + 210, px + 106, py + 236), blur=14, alpha=95)
        shot.paste(real_prod, (px, py), _round_corner_mask(112, 220, 12))
    else:
        product_bottle(shot, 151, 330, 112, 220, (232, 226, 220), (246, 240, 238),
                       label=("粉底液", "30ml"))
    for i, (pf, name, ts, tag) in enumerate(panels):
        x = 30 + i * 390
        d.rounded_rectangle([x, 60, x + 350, 840], radius=18, fill=(255, 255, 255))
        d.rounded_rectangle([x, 60, x + 350, 158], radius=18, fill=(250, 251, 253))
        d.ellipse([x + 24, 84, x + 84, 144], fill=(150, 176, 208))
        _text(d, (x + 96, 100), pf, font(18, True), (40, 44, 52), "lm")
        _text(d, (x + 96, 128), name, font(14), (110, 116, 124), "lm")
        _text(d, (x + 24, 176), ts, font(13), (150, 156, 164), "lm")
        d.rounded_rectangle([x + 24, 206, x + 326, 566], radius=14, fill=(228, 226, 224))
        img.paste(shot, (x + 24, 206))
        d = ImageDraw.Draw(img)
        _text(d, (x + 175, 596), "同一张实拍图", font(13), (140, 144, 150), "mm")
        d.rounded_rectangle([x + 24, 626, x + 326, 676], radius=10,
                            fill=(232, 244, 236) if i == 0 else (240, 242, 246))
        _text(d, (x + 175, 651), tag, font(14, True),
              (28, 118, 76) if i == 0 else (110, 116, 124), "mm")
        bodies = [["测了两周，记录一下使用感，图都是原图。"],
                  ["测了两周，记录一下使用感～ 视频版明天发。"],
                  ["测了两周，记录一下使用感。同步自小红书。"]]
        yy = 706
        for ln in bodies[i]:
            n = draw_text(d, (x + 28, yy), ln, font(14), (52, 56, 62), max_w=294, lh=24)
            yy += max(1, n) * 24 + 6
        _nav_icons(d, x + 40, 790, col=(150, 154, 160), gap=52)
    _text(d, (W / 2, 34), "同一作者 · 同名同头像 · 主动注明首发平台 · 文案按平台改写", font(16), (110, 116, 124), "mm")
    img.save(out_path)

# ---------------------------------------------------------------- ⑤ 图文不符 1024x1024

MISMATCH = {
    "product": "澜本 氨基酸洁面慕斯",
    "slogan": "温和清洁 · 敏感肌可用",
    "claim": "维C抗氧精华 · 提亮肤色",
}

def make_mismatch(out_path: str):
    """AI 生成的美妆产品图：瓶身文字是「氨基酸洁面慕斯」，配文却写成「维C抗氧精华」。"""
    W = H = 1024
    img = vgrad((W, H), (243, 232, 240), (208, 186, 205))
    d = ImageDraw.Draw(img)
    # 台面：一块磨砂玻璃/亚克力台面
    d.rectangle([0, 706, W, H], fill=(196, 176, 186))
    d.rectangle([0, 706, W, 716], fill=(232, 218, 226))
    soft_ellipse(img, [80, 700, 944, 900], (250, 240, 246), blur=60, alpha=150)

    # 主瓶身：材质渲染（磨砂玻璃 + 金属盖 + 高光 + 接触阴影）
    product_bottle(img, 512, 720, 216, 380, (58, 62, 70), (236, 232, 240),
                   label=("洁面慕斯", "AMINO ACID"), accent=(226, 232, 244), cap_shape="disc")
    d = ImageDraw.Draw(img)
    rr(d, [462, 421, 562, 474], 26, fill=(252, 252, 253))
    _text(d, (512, 446), "澜本", font(19, True), (52, 54, 60), "mm")
    _text(d, (512, 470), "温和清洁 · 敏感肌可用", font(10), (150, 152, 158), "mm")
    _text(d, (512, 662), "国妆网备字 2026XXXXXX", font(8), (150, 152, 160), "mm")
    rr(d, [W - 300, H - 92, W - 40, H - 40], 12, fill=(255, 255, 255))
    _text(d, (W - 170, H - 66), "AI 生成 · 演示用", font(13), (140, 140, 146), "mm")
    img.save(out_path)

# ------------------------------------------------ ⑨ 同一张照片冒充「28 天前后对比」1200x800

def make_same_photo_sidebyside(out_path: str):
    """左「第 1 天」右「第 28 天」：两张其实是同一张照片，右图只套了一层暖色滤镜。

    与 post_a_28day_beforeafter.png 的区别：那张是「磨皮 + 拼接缝合成的假对比」，
    这张更便宜也更常见——同一张图用两次，右边加滤镜。
    证据就落在「两侧底图逐像素相同」和「滤镜参数单一（整体线性提亮 + 暖色调）」上。
    """
    W, H = 1200, 800
    random.seed(2404)
    img = Image.new("RGB", (W, H), (32, 34, 39))
    d = ImageDraw.Draw(img)
    fw, fh = 356, 540
    fx, fy = 202, 98

    # 背景：办公室墙角（米色墙 + 冷灰地面 + 一扇门 + 一个挂钟）
    d.rectangle([0, 0, W, 632], fill=(207, 203, 196))
    d.rectangle([0, 632, W, H], fill=(120, 122, 126))
    d.rectangle([876, 132, 1168, 560], fill=(178, 174, 168))
    d.rectangle([70, 150, 172, 246], fill=(150, 152, 152))
    d.ellipse([96, 170, 148, 222], fill=(226, 226, 224))

    # 真实人脸照片作为基底，左原图 / 右暖色滤镜
    base = load_real_face(size=(fw, fh), face_id="00002")
    if base is not None:
        edited = Image.blend(base, Image.new("RGB", (fw, fh), (255, 245, 232)), 0.22)
    else:
        # 兜底：程序生成
        base = Image.new("RGB", (fw, fh), (206, 160, 130))
        bd = ImageDraw.Draw(base)
        for i in range(26, 0, -1):
            t = i / 26
            col = tuple(int((247, 219, 200)[k] * (1 - t) + (203, 156, 126)[k] * t) for k in range(3))
            bd.ellipse([fw / 2 - 158 * t, fh / 2 - 240 * t,
                        fw / 2 + 158 * t, fh / 2 + 240 * t], fill=col)
        bd.ellipse([16, -70, 340, 118], fill=(46, 36, 32))
        bd.ellipse([84, 210, 146, 236], fill=(58, 42, 36))
        bd.ellipse([210, 210, 272, 236], fill=(58, 42, 36))
        bd.line([144, 300, 212, 300], fill=(150, 96, 84), width=9)
        bd.arc([112, 286, 246, 356], 15, 165, fill=(146, 78, 70), width=7)
        for _ in range(58):
            a = random.random() * 6.2832
            rad = random.random() ** 0.5
            x = fw / 2 + 140 * rad * math.cos(a)
            y = fh / 2 + 220 * rad * math.sin(a)
            r2 = 1.6 + random.random() * 2.2
            bd.ellipse([x - r2, y - r2, x + r2, y + r2], fill=(166, 84, 78))
        for dx, dy in ((-70, -60), (58, -22), (18, 92), (-30, 168), (86, 140)):
            bd.ellipse([fw / 2 + dx - 13, fh / 2 + dy - 13,
                        fw / 2 + dx + 13, fh / 2 + dy + 13], fill=(180, 92, 86))
        bd.rectangle([fw / 2 - 8, fh / 2 - 100, fw / 2 + 8, fh / 2 + 150], fill=(255, 255, 255))
        edited = Image.blend(base, Image.new("RGB", (fw, fh), (255, 245, 232)), 0.22)

    img.paste(base, (fx, fy))
    img.paste(edited, (fx + 452, fy))

    _text(d, (fx + fw / 2, 62), "Day 1 · 2026-09-05", font(20, True), (238, 238, 238), "mm")
    _text(d, (fx + 452 + fw / 2, 62), "Day 28 · 2026-10-01", font(20, True), (238, 238, 238), "mm")
    d.rectangle([fx + fw + 48, 98, fx + fw + 50, 638], fill=(70, 72, 78))

    d.rectangle([0, H - 62, W, H], fill=(22, 24, 29))
    _text(d, (28, H - 31), "@小鹿的日常号　28 天皮肤变化记录｜左边第 1 天，右边今天",
          font(17), (230, 237, 243), "lm")
    _text(d, (W - 28, H - 31), "同一部手机 · 同一个位置", font(14), (255, 92, 92), "rm")
    img.save(out_path)

# ---------------------------------------------------------------- 主流程

JOBS = [
    ("images/tampered/post_a_28day_beforeafter.png",   make_beforeafter,      (1200, 800)),
    ("images/ai_generated/post_a_28day_unboxing.png",  make_unboxing,         (1024, 1024)),
    ("images/tampered/post_a_samephoto_sidebyside.png", make_same_photo_sidebyside, (1200, 800)),
    ("images/tampered/complaint_b_multiaccount_wall.png", make_complaint_wall, (1200, 1600)),
    ("images/tampered/repost_c_platform_comparison.png",  make_platform_compare, (1600, 900)),
    ("images/tampered/repost_c_reworded_compare.png",     make_repost_reworded,  (1600, 900)),
    ("images/tampered/repost_c_renamed_compare.png",      make_repost_renamed,   (1600, 900)),
    ("images/tampered/complaint_b_photo_reuse.png",       make_complaint_staggered, (1200, 1600)),
    ("images/tampered/complaint_b_fivestar_conflict.png", make_complaint_fivestar,  (1200, 1600)),
    ("images/mismatch/post_a_28day_wrong_product.png",     make_mismatch,         (1024, 1024)),
    ("images/real/post_a_28day_control.jpg",             make_control_unboxing,  (800, 1180)),
    ("images/real/complaint_b_control.jpg",              make_control_complaint, (800, 1180)),
    ("images/real/repost_c_control.jpg",                 make_control_repost,    (1200, 900)),
]

def main():
    global TIGAS_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="GlowTrace-MM 数据集根目录")
    ap.add_argument("--tigas", default=None, help="TIGAS_data 目录（含 real/ 与 fake/）")
    ap.add_argument("--only", default=None, help="只重新生成名字里含该子串的图（例如 --only samephoto）")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    TIGAS_ROOT = os.path.abspath(a.tigas) if a.tigas else None
    for sub in ("images/real", "images/ai_generated", "images/tampered", "images/mismatch",
                "texts/real_reviews", "texts/fake_reviews", "texts/mismatched_prompts",
                "annotations/bboxes", "annotations/rationales"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    report = []
    for rel, fn, size in JOBS:
        if a.only and a.only not in rel:
            continue
        out = os.path.join(root, rel)
        fn(out)
        with Image.open(out) as im:
            got = im.size
        md5 = hashlib.md5(open(out, "rb").read()).hexdigest()
        report.append((rel, got, got == size, os.path.getsize(out), md5))

    # TIGAS 两张样张：直接复制，不改名以外的任何处理
    if a.tigas:
        pairs = [("real/00002.jpeg", "images/real/tigas_real_face_00002.jpeg"),
                 ("fake/image-2019-02-17_000907.jpeg", "images/ai_generated/tigas_fake_face_000907.jpeg")]
        for src_rel, dst_rel in pairs:
            src = os.path.join(a.tigas, src_rel)
            dst = os.path.join(root, dst_rel)
            if os.path.exists(src):
                shutil.copyfile(src, dst)
                report.append((dst_rel, "copied", True, os.path.getsize(dst),
                               hashlib.md5(open(dst, "rb").read()).hexdigest()))
            else:
                report.append((dst_rel, "MISSING SRC: " + src, False, 0, ""))

    print("=" * 78)
    print("GlowTrace-MM 图片生成报告")
    print("=" * 78)
    for rel, size, ok, nbytes, md5 in report:
        print(("  OK  " if ok else " FAIL ") + rel)
        print("        尺寸/状态: %s   字节: %s" % (size, nbytes))
        print("        MD5: %s" % md5)
    print("=" * 78)
    print("提示：complaint_b_multiaccount_wall.png 就是 4 条投诉共用的那张照片的容器图；")
    print("      若要把真实 MD5 回填到 annotations/timeline_complaint_b.json 的 shared_photo.md5，")
    print("      请对 4 条缩略图裁剪出的单张照片取哈希，或直接记录本图的 MD5 并在 note 中说明口径。")
    return 0 if all(r[2] for r in report) else 1

if __name__ == "__main__":
    sys.exit(main())
