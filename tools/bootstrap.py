# -*- coding: utf-8 -*-
"""
一键落地脚本（在 shell 恢复后运行）

背景：文本与标注（21 个文件）已经直接用编辑器写入 DST，所以本脚本**不再从工作区复制**，
      只做三件还不能用编辑器完成的事：生成图片、写控制图时间戳、跑交付前校验。

  1. 在 DST 内生成 8 张合成图 + 1 张副产物，并按需从 TIGAS 复制 2 张样张；
  2. 给 3 张控制图写入文件时间戳（st_mtime），让 mtime 与正文声明的时间线自洽；
  3. 把 dataset_index.csv 里负样本行的 evidence_anchors 占位符统一成"无"的写法；
  4. 跑 DST/tools/verify_dataset.py 做交付前校验。

用法：
    python bootstrap.py --dst "D:\\欧莱雅黑客松\\GlowTrace-MM" \
                        --tigas "D:\\欧莱雅黑客松\\TIGAS_data\\TIGAS_data"
"""
from __future__ import annotations
import argparse, csv, os, subprocess, sys, time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 控制图 → 应写入的 mtime（与各案例正文里的时间线一致）
MTIME = {
    "images/real/post_a_28day_control.jpg": "2026-10-05 09:12",
    "images/real/complaint_b_control.jpg": "2026-02-14 10:20",
    "images/real/repost_c_control.jpg": "2026-03-21 20:05",
}
# CSV 里负样本行的 evidence_anchors 占位符（统一写成同一种"无"，避免出现 3 种写法）
PLACEHOLDER = "-"
NEGATIVE_VALUE = "—（负样本，无可指认的伪造区域）"

CONTROL_DIRS = ("images/real", "images/ai_generated", "images/tampered", "images/mismatch",
                "texts/real_reviews", "texts/fake_reviews", "texts/mismatched_prompts",
                "annotations/bboxes", "annotations/rationales")


def gen_images(dst: str, tigas: str | None) -> None:
    """直接 import 生成器的 main，避免子进程；也可换成 subprocess。"""
    sys.path.insert(0, os.path.join(dst, "tools"))
    import make_images  # noqa: E402
    argv = sys.argv
    sys.argv = ["make_images.py", "--root", dst] + (["--tigas", tigas] if tigas else [])
    try:
        make_images.main()
    finally:
        sys.argv = argv
    print("[1/4] 图片生成完成")


def stamp_controls(dst: str) -> None:
    for rel, ts in MTIME.items():
        p = os.path.join(dst, rel.replace("/", os.sep))
        if not os.path.exists(p):
            print("      ! 缺文件，跳过时间戳：" + rel)
            continue
        t = time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M"))
        os.utime(p, (t, t))
        print("      时间戳 %s → %s" % (rel, ts))
    print("[2/4] 控制图时间戳写入完成")


def fill_csv(dst: str) -> None:
    p = os.path.join(dst, "annotations", "dataset_index.csv")
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    fields = list(rows[0].keys())
    changed = 0
    for r in rows:
        cid = r.get("case_id", "")
        is_negative = cid.endswith("_control") or cid.startswith("tigas_")
        if is_negative and (r.get("evidence_anchors") or "").strip() in ("-", "", "—"):
            r["evidence_anchors"] = NEGATIVE_VALUE
            changed += 1
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("[3/4] CSV 负样本行锚点规范完成，修改 %d 行" % changed)


def verify(dst: str) -> int:
    script = os.path.join(dst, "tools", "verify_dataset.py")
    print("[4/4] 运行校验：" + script)
    r = subprocess.run([sys.executable, script, "--root", dst], cwd=dst)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=r"D:\欧莱雅黑客松\GlowTrace-MM", help="GlowTrace-MM 数据集根目录")
    ap.add_argument("--tigas", default=None, help="TIGAS_data 目录（含 real/ 与 fake/）")
    ap.add_argument("--skip-images", action="store_true", help="只做校验与回填，不重新生成图片")
    a = ap.parse_args()
    dst = os.path.abspath(a.dst)
    for sub in CONTROL_DIRS:
        os.makedirs(os.path.join(dst, sub.replace("/", os.sep)), exist_ok=True)
    if a.skip_images:
        print("[1/4] 已跳过图片生成（--skip-images）")
    else:
        gen_images(dst, a.tigas)
    stamp_controls(dst)
    fill_csv(dst)
    rc = verify(dst)
    print("完事。DST = %s，校验退出码 = %d" % (dst, rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
