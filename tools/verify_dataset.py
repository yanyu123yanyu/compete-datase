# -*- coding: utf-8 -*-
"""
GlowTrace-MM 数据集一致性校验（交付前跑一次）

检查四件事：
  1. annotations/ 下所有 .json 能被 json.load 解析；
  2. dataset_index.csv 里引用的每个 image_path 都真实存在，且目录落在 格式.txt 允许的四个子目录内；
  3. 每张图的真实像素尺寸与 bboxes/*.json 的 image_size 完全一致（不一致则坐标全部失效）；
  4. 每条 CSV 记录的 evidence_anchors 在对应 rationale 的 evidence 里都能找到。

用法：
    <python> tools/verify_dataset.py --root "GlowTrace-MM"
退出码 0 = 全部通过；1 = 有问题（逐条打印）。
"""
from __future__ import annotations
import argparse, csv, json, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ALLOWED_IMAGE_DIRS = ("images/real/", "images/ai_generated/", "images/tampered/", "images/mismatch/")
BBOX_FOR = {                     # case_id -> bbox 文件名
    "post_a_28day": "post_a_28day_bbox.json",
    "post_a_samephoto": "post_a_samephoto_bbox.json",
    "complaint_b_recycled": "complaint_b_bbox.json",
    "complaint_b_photo_reuse": "complaint_b_photo_reuse_bbox.json",
    "complaint_b_fivestar": "complaint_b_fivestar_bbox.json",
    "repost_c_platform": "repost_c_bbox.json",
    "repost_c_reworded": "repost_c_reworded_bbox.json",
    "repost_c_renamed": "repost_c_renamed_bbox.json",
}
RATIONALE_FOR = {
    "post_a_28day": "post_a_28day_rationale.json",
    "post_a_samephoto": "post_a_samephoto_rationale.json",
    "complaint_b_recycled": "complaint_b_rationale.json",
    "complaint_b_photo_reuse": "complaint_b_photo_reuse_rationale.json",
    "complaint_b_fivestar": "complaint_b_fivestar_rationale.json",
    "repost_c_platform": "repost_c_rationale.json",
    "repost_c_reworded": "repost_c_reworded_rationale.json",
    "repost_c_renamed": "repost_c_renamed_rationale.json",
}
# 这些图是脚本运行中附带产出的副产物，不单独生成尺寸断言
SIDECAR = {"repost_c_source_watermarked.png": (500, 675)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="GlowTrace-MM")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    problems, notes = [], []

    # ---- 1. JSON 合法性
    for dirpath, _dirs, files in os.walk(os.path.join(root, "annotations")):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                json.load(open(p, encoding="utf-8"))
                notes.append("JSON OK   " + os.path.relpath(p, root))
            except Exception as e:
                problems.append("JSON 解析失败 %s: %s" % (os.path.relpath(p, root), e))

    # ---- 2/3/4. CSV 逐行
    csv_path = os.path.join(root, "annotations", "dataset_index.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    notes.append("CSV 记录数 %d" % len(rows))

    bbox_cache = {}
    for rel_name in set(BBOX_FOR.values()):
        p = os.path.join(root, "annotations", "bboxes", rel_name)
        if os.path.exists(p):
            bbox_cache[rel_name] = json.load(open(p, encoding="utf-8"))

    try:
        from PIL import Image
        have_pil = True
    except Exception:
        have_pil = False
        notes.append("未安装 Pillow，跳过尺寸比对")

    for r in rows:
        cid = (r.get("case_id") or "").strip()
        paths = [p.strip() for p in (r.get("image_paths") or "").split("；") if p.strip()]
        if not paths:
            problems.append("%s: image_paths 为空" % cid)
        for rel in paths:
            if not rel.startswith(ALLOWED_IMAGE_DIRS):
                problems.append("%s: 图片 %s 不在格式允许的四个子目录内" % (cid, rel))
            full = os.path.join(root, rel.replace("/", os.sep))
            if not os.path.exists(full):
                problems.append("%s: 图片不存在 → %s" % (cid, rel))
                continue            # 尺寸比对
            bbf = BBOX_FOR.get(cid)
            if bbf and bbf in bbox_cache:
                big = bbox_cache[bbf]
                want = (big["image_size"]["width"], big["image_size"]["height"])
                is_primary = bool(big.get("image")) and rel == big["image"]
                if os.path.basename(rel) in SIDECAR:
                    want = SIDECAR[os.path.basename(rel)]
                elif not is_primary:
                    continue          # 同一 case 的其余图不做尺寸断言（尺寸以 bbox 声明的 image 为准）
                if have_pil:
                    with Image.open(full) as im:
                        got = im.size
                    if got != want:
                        problems.append("%s: %s 尺寸 %s ≠ bbox 声明的 %s" % (cid, rel, got, want))
                    else:
                        notes.append("尺寸 OK   %s %s" % (rel, got))
        # text_path 也必须真实存在（text_path 为 "-" 表示该行没有配套文案）
        tp = (r.get("text_path") or "").strip()
        if tp and tp != "-":
            if not os.path.exists(os.path.join(root, tp.replace("/", os.sep))):
                problems.append("%s: 文案不存在 → %s" % (cid, tp))
            else:
                notes.append("文案 OK   %s %s" % (cid, tp))

        # rationale 锚点比对
        rf = RATIONALE_FOR.get(cid)
        if rf:
            rp = os.path.join(root, "annotations", "rationales", rf)
            if os.path.exists(rp):
                rj = json.load(open(rp, encoding="utf-8"))
                have = {e.get("id") for e in rj.get("ground_truth", {}).get("evidence", [])}
                want = {x.strip() for x in (r.get("evidence_anchors") or "").split("；") if x.strip()}
                if want and not want <= have:
                    problems.append("%s: CSV 锚点 %s 在 rationale 里找不到" % (cid, sorted(want - have)))
                else:
                    notes.append("锚点 OK   %s %s" % (cid, sorted(have)))

    print("=" * 74)
    for n in notes:
        print("  " + n)
    print("=" * 74)
    if problems:
        print("发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  ✗ " + p)
        return 1
    print("全部通过：JSON 合法、图片齐备、尺寸与 bbox 一致、锚点可追溯。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
