# -*- coding: utf-8 -*-
r"""证据自检：用像素运算验证 annotations 里「可复现的观察」是否真的成立。

不依赖任何模型，只用 Pillow。每一项对应 rationale 里的一条证据：
  C1  三个平台面板的画面同源（除水印/头像/标签区）
  C2  抖音面板左边缘的 6px 像素带确实与左右两侧不一致；小红书水印位在抖音面板确实为空
  C3  微博贴纸盖住了与小红书水印相同的位置
  B1  四张投诉缩略图像素完全一致
  A5  左右两支瓶子的瓶盖颜色确实不同
  A6  拼接缝与红描边确实在 A6 框内

用法：python evidence_check.py --root D:\欧莱雅黑客松\GlowTrace-MM
"""

import argparse
import os
import sys
from itertools import combinations

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image, ImageChops, ImageStat
import numpy as np


def diff_ratio(im_a, im_b, box):
    """两个同尺寸裁剪块中「明显不同」的像素占比（任一通道差 > 18）。"""
    a = im_a.crop(box).convert("RGB")
    b = im_b.crop(box).convert("RGB")
    d = ImageChops.difference(a, b).convert("L")
    hist = d.histogram()
    total = sum(hist)
    diff = sum(hist[19:])
    return diff / total if total else 0.0


def diff_ratio_blocks(block_a, block_b):
    """两个已经是裁剪块的图像之间「明显不同」的像素占比（任一通道差 > 18）。"""
    d = ImageChops.difference(block_a.convert("RGB"), block_b.convert("RGB")).convert("L")
    hist = d.histogram()
    total = sum(hist)
    diff = sum(hist[19:])
    return diff / total if total else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\欧莱雅黑客松\GlowTrace-MM")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    def P(*parts):
        return os.path.join(root, *parts)

    fails = []
    checks = []

    def check(name, ok, detail):
        checks.append((name, ok, detail))
        if not ok:
            fails.append(name)

    # ---------------------------------------------------------------- C1/C2/C3
    cmp_img = Image.open(P("images", "tampered", "repost_c_platform_comparison.png")).convert("RGB")
    side = Image.open(P("images", "tampered", "repost_c_source_watermarked.png")).convert("RGB")

    check("副产物尺寸 500x675", side.size == (500, 675), f"实际 {side.size}")

    # 三块面板：x=30/550/1070，y=135，w=500，h=675
    px = [30, 550, 1070]
    panels = [cmp_img.crop((x, 135, x + 500, 135 + 675)) for x in px]

    # C1：面板主体（避开底部文字带与顶部水印/头像区）应几乎完全一致
    body = (20, 30, 480, 520)
    pair_diffs = {}
    for i, j in combinations(range(3), 2):
        pair_diffs[f"{i}-{j}"] = diff_ratio(panels[i], panels[j], body)
    worst = max(pair_diffs.values())
    check("C1 三面板主体同源（差异<2%）", worst < 0.02,
          "主体区差异占比 " + ", ".join(f"{k}={v:.4%}" for k, v in pair_diffs.items()))

    # C2-a：抖音面板左边缘 6px 带（面板内 x 0..10）与紧邻右侧（10..20）差异应明显
    band = (0, 64, 10, 675)
    right = (10, 64, 20, 675)
    far = (120, 64, 130, 675)
    d_band = diff_ratio(panels[1], panels[1], band)  # 占位，下面直接用像素统计
    a = ImageStat.Stat(panels[1].crop(band)).mean
    b = ImageStat.Stat(panels[1].crop(right)).mean
    c = ImageStat.Stat(panels[1].crop(far)).mean
    gap = sum(abs(x - y) for x, y in zip(a, b)) / 3.0
    far_gap = sum(abs(x - y) for x, y in zip(a, c)) / 3.0
    check("C2 抖音像素带与紧邻像素存在亮度差", gap > 8, f"带内均值 { [round(v,1) for v in a] }，紧邻 { [round(v,1) for v in b] }，差 {gap:.1f}；更远处差 {far_gap:.1f}")

    # C2-b：小红书面板水印位 (460..500, 641..675) 在抖音面板应更「干净」——与首发版差异明显
    wm_box = (430, 615, 500, 675)
    d_wm = diff_ratio(panels[0], panels[1], wm_box)
    d_bg = diff_ratio(panels[1], panels[2], wm_box)
    check("C2 抖音面板水印位与首发版不同", d_wm > 0.02,
          f"首发 vs 抖音 差异 {d_wm:.2%}；抖音 vs 微博 差异 {d_bg:.2%}")

    # C3：微博贴纸区（面板内 x 1254-1070=184.., y 706-135=571..）与首发版同位置差异明显
    sticker_box = (184, 571, 437, 733)
    d_st = diff_ratio(panels[0], panels[2], sticker_box)
    check("C3 微博贴纸覆盖区与首发版不同", d_st > 0.05, f"差异 {d_st:.2%}")

    # ---------------------------------------------------------------- B1
    wall = Image.open(P("images", "tampered", "complaint_b_multiaccount_wall.png")).convert("RGB")
    thumbs = []
    for y_norm in (0.06, 0.27, 0.48, 0.69):
        y = int(y_norm * 1600)
        thumbs.append(wall.crop((40, y + 10, 260, y + int(0.19 * 1600) - 20)))
    t_diffs = [diff_ratio(thumbs[0], t, (6, 6, 214, 268)) for t in thumbs[1:]]
    check("B1 四张缩略图像素一致（差异=0）", max(t_diffs) == 0.0,
          "缩略图两两差异 " + ", ".join(f"{v:.4%}" for v in t_diffs))

    # ---------------------------------------------------------------- A5
    before = Image.open(P("images", "tampered", "post_a_28day_beforeafter.png")).convert("RGB")
    # 量的是两支瓶子瓶盖的中间一段。坐标不能靠公式推，必须实测：
    # probe_caps.py 在 y=440..700 上滑动取样带后，最大亮差出现在 y≈493；
    # 瓶盖实测包围盒为 (693,482,758,543)（高 61 = int(220*0.28)），
    # 所以取样带取 y=493..533 —— 完全落在盖体内，不碰瓶身与背景。
    cap_l = ImageStat.Stat(before.crop((346, 493, 410, 533))).mean
    cap_r = ImageStat.Stat(before.crop((694, 493, 758, 533))).mean
    lum_l = sum(cap_l) / 3.0
    lum_r = sum(cap_r) / 3.0
    check("A5 左瓶盖亮、右瓶盖暗", lum_l - lum_r > 100,
          f"左瓶盖亮度 {lum_l:.0f}，右瓶盖亮度 {lum_r:.0f}")

    # ---------------------------------------------------------------- A6
    seam = ImageStat.Stat(before.crop((596, 480, 604, 576))).mean
    red = ImageStat.Stat(before.crop((588, 480, 592, 576))).mean
    check("A6 拼接缝与红描边在框内", sum(seam) / 3.0 < 60 and red[0] - (red[1] + red[2]) / 2 > 40,
          f"缝亮度 {sum(seam)/3.0:.0f}；红描边 R={red[0]:.0f} G={red[1]:.0f} B={red[2]:.0f}")

    # ---------------------------------------------------------------- A1（同一底图 ＋ 滤镜）
    # post_a_samephoto：左右两半是同一张照片，右半只套了一层暖色滤镜。
    # 判定方式：把右半按整体亮度对齐后，两半的结构差异应该接近于零。
    sp = Image.open(P("images", "tampered", "post_a_samephoto_sidebyside.png")).convert("RGB")
    L = sp.crop((201, 98, 557, 638))
    R = sp.crop((653, 98, 1009, 638))
    lab_l = np.asarray(L.convert("LAB"), dtype=np.float32)
    lab_r = np.asarray(R.convert("LAB"), dtype=np.float32)
    # 去掉亮度通道（L）后比较色度结构：只比 a/b 的「形状」，所以各自减去均值
    la = lab_l[:, :, 1] - lab_l[:, :, 1].mean()
    lb = lab_l[:, :, 2] - lab_l[:, :, 2].mean()
    ra = lab_r[:, :, 1] - lab_r[:, :, 1].mean()
    rb = lab_r[:, :, 2] - lab_r[:, :, 2].mean()
    chroma_dist = float((np.abs(la - ra).mean() + np.abs(lb - rb).mean()) / 2.0)
    lmean = float(lab_l[:, :, 0].mean())
    rmean = float(lab_r[:, :, 0].mean())
    check("A1 两侧为同一底图（去亮度后色度结构一致）", chroma_dist < 6.0,
          f"色度平均距离 {chroma_dist:.2f}（阈值 6.0）；" +
          f"整体亮度 左 {lmean:.0f} vs 右 {rmean:.0f}（差值 {rmean - lmean:+.0f}）")
    check("A2 差异是整体线性偏移", abs(rmean - lmean) > 12,
          f"整体亮度差 {rmean - lmean:+.0f}，而色度结构几乎不变 → 属于整体套滤镜")

    # ---------------------------------------------------------------- B1（照片复用：时间被打散）
    reuse = Image.open(P("images", "tampered", "complaint_b_photo_reuse.png")).convert("RGB")
    r_thumbs = []
    for y_norm in (0.06, 0.27, 0.48, 0.69):
        y = int(y_norm * 1600)
        r_thumbs.append(reuse.crop((40, y + 10, 260, y + int(0.19 * 1600) - 20)))
    r_diffs = [diff_ratio(r_thumbs[0], t, (6, 6, 214, 268)) for t in r_thumbs[1:]]
    check("B1-photo_reuse 四张缩略图像素一致（差异=0）", max(r_diffs) == 0.0,
          "缩略图两两差异 " + ", ".join(f"{v:.4%}" for v in r_diffs))

    # ------------------------------------------- B2（五条？不：配图不同、文案同批）
    five = Image.open(P("images", "tampered", "complaint_b_fivestar_conflict.png")).convert("RGB")
    f_thumbs = []
    for y_norm in (0.06, 0.27, 0.48, 0.69):
        y = int(y_norm * 1600)
        f_thumbs.append(five.crop((40, y + 10, 260, y + int(0.19 * 1600) - 20)))
    f_diffs = [diff_ratio(f_thumbs[0], t, (6, 6, 214, 268)) for t in f_thumbs[1:]]
    check("B2-fivestar 四张缩略图各不相同（每张差异>2%）", min(f_diffs) > 0.02,
          "缩略图两两差异 " + ", ".join(f"{v:.2%}" for v in f_diffs))
    gold_band = five.crop((330, 990, 1156, 1058)).convert("RGB")
    ga = np.asarray(gold_band).astype(int)
    gold_mask = (ga[:, :, 0] > 170) & (ga[:, :, 1] > 110) & (ga[:, :, 1] < 200) & (ga[:, :, 2] < 110)
    check("B3-fivestar 金色对照说明确实为金色（该带内存在金色像素）",
          int(gold_mask.sum()) > 300,
          f"金色像素 {int(gold_mask.sum())} 个（该带覆盖第3卡与第4卡之间、标着「同一账号 · 五星好评」的横线与文字）")

    # ---------------------------------------------------------------- C5（改文案 + 同一张图）
    rw = Image.open(P("images", "tampered", "repost_c_reworded_compare.png")).convert("RGB")
    rw_imgs = [rw.crop((x + 150, 285, x + 350, 615)) for x in (30, 550, 1070)]
    rw_diffs = [diff_ratio(rw_imgs[0], t, (10, 10, 190, 320)) for t in rw_imgs[1:]]
    check("C5-reworded 三面板配图逐像素一致（差异<1%）", max(rw_diffs) < 0.01,
          "配图两两差异 " + ", ".join(f"{v:.4%}" for v in rw_diffs))
    rw_text_a = rw.crop((52, 675, 508, 745)).convert("RGB")
    rw_text_b = rw.crop((572, 675, 1028, 745)).convert("RGB")
    t_diff = diff_ratio_blocks(rw_text_a, rw_text_b)
    check("C5-reworded 正文区确实被改写（差异>3%）", t_diff > 0.03, f"正文区差异 {t_diff:.2%}")
    edge = ImageStat.Stat(rw.crop((179, 300, 181, 600))).mean
    inner = ImageStat.Stat(rw.crop((200, 320, 300, 580))).mean
    check("C6-reworded 红框确实存在且框内是画面",
          edge[0] - (edge[1] + edge[2]) / 2 > 40 and inner[0] - inner[1] < 30,
          f"框线均值 R={edge[0]:.0f} G={edge[1]:.0f} B={edge[2]:.0f}；框内均值 R={inner[0]:.0f} G={inner[1]:.0f} B={inner[2]:.0f}")

    # ---------------------------------------------------------------- C7（换号改名 + 同一张图）
    rn = Image.open(P("images", "tampered", "repost_c_renamed_compare.png")).convert("RGB")
    rn_imgs = [rn.crop((x + 150, 285, x + 350, 615)) for x in (30, 550, 1070)]
    rn_diffs = [diff_ratio(rn_imgs[0], t, (10, 10, 190, 320)) for t in rn_imgs[1:]]
    check("C7-renamed 三面板配图逐像素一致（差异<1%）", max(rn_diffs) < 0.01,
          "配图两两差异 " + ", ".join(f"{v:.4%}" for v in rn_diffs))
    sig1 = rn.crop((48, 180, 480, 200)).convert("RGB")
    sig3 = rn.crop((1088, 180, 1520, 200)).convert("RGB")
    s_diff = diff_ratio_blocks(sig1, sig3)
    check("C8-renamed 署名/时间行确实不同（差异>5%）", s_diff > 0.05, f"署名行差异 {s_diff:.2%}")

    # ---------------------------------------------------------------- 尺寸
    for rel, size in (("images/tampered/post_a_28day_beforeafter.png", (1200, 800)),
                      ("images/tampered/post_a_samephoto_sidebyside.png", (1200, 800)),
                      ("images/ai_generated/post_a_28day_unboxing.png", (1024, 1024)),
                      ("images/tampered/complaint_b_multiaccount_wall.png", (1200, 1600)),
                      ("images/tampered/complaint_b_photo_reuse.png", (1200, 1600)),
                      ("images/tampered/complaint_b_fivestar_conflict.png", (1200, 1600)),
                      ("images/tampered/repost_c_platform_comparison.png", (1600, 900)),
                      ("images/tampered/repost_c_reworded_compare.png", (1600, 900)),
                      ("images/tampered/repost_c_renamed_compare.png", (1600, 900)),
                      ("images/mismatch/post_a_28day_wrong_product.png", (1024, 1024)),
                      ("images/real/post_a_28day_control.jpg", (800, 1180)),
                      ("images/real/complaint_b_control.jpg", (800, 1180)),
                      ("images/real/repost_c_control.jpg", (1200, 900))):
        s = Image.open(P(*rel.split("/"))).size
        check(f"尺寸 {rel}", s == size, f"{s} vs 期望 {size}")

    # ------------------------------------------------- 负样本图的文件时间戳
    # 三张控制图代表「真实用户自己发的帖」，它们的文件时间就是帖子时间，必须与正文一致：
    # 重新生成图片会把 mtime 刷成生成时刻，所以这里显式检查（同步脚本的 ⑤ 步负责写回）。
    from datetime import datetime
    for rel, want in (("images/real/post_a_28day_control.jpg", "2026-10-05 09:12"),
                      ("images/real/complaint_b_control.jpg", "2026-02-14 10:20"),
                      ("images/real/repost_c_control.jpg", "2026-03-21 20:05")):
        p = P(*rel.split("/"))
        got = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
        check(f"控制图文件时间 {rel}", got == want, f"{got} vs 期望 {want}")

    print("=" * 74)
    print("  GlowTrace-MM 证据自检（像素级）")
    print("=" * 74)
    for name, ok, detail in checks:
        print(f"  {'OK  ' if ok else 'FAIL'} {name}")
        print(f"        {detail}")
    print("=" * 74)
    if fails:
        print(f"未通过 {len(fails)} 项：" + "、".join(fails))
        return 1
    print(f"全部 {len(checks)} 项通过：annotations 里的可复现观察在像素层面成立。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
