# GlowTrace-MM 数据集说明书

> 欧莱雅美妆科技黑客松 · 赛题二「信任守护师」配套数据集
> 版本 v0.5（demo 版：3 个场景 × 每个 3 个实例 = **9 个伪造案例 + 3 个真实对照**，另有 2 行 TIGAS 样张）

本数据集是「信任守护师」美妆内容鉴真 Agent 的评测集与答题卡（ground truth）。
Agent 读取 `images/ + texts/` 中的内容，输出风险判定；`annotations/` 中给出标准答案，
两者逐条比对即可得到准确率、误报率与证据召回率。

---

## 0. 为什么要有这个数据集

美妆是内容种草的信任密度最高的品类之一，也因此是 AI 造假与账号矩阵套利的重灾区。
公开治理数据说明这不是假想问题：

| 事实 | 来源 |
|---|---|
| 近一年平台处置确认的 AI 虚假种草笔记**超 330 万篇**，并对 **18 款**利用 AI 涉嫌侵权的主体采取法律维权 | [极目新闻/网易（2026-05-16）](https://www.163.com/dy/article/KT135FHU051494GR.html) |
| 全国首例「AI 批量代写种草笔记」案由杭州中院披露，被告被认定构成**不正当竞争** | 同上 |
| 平台处置 **1.1 万个**虚假仿冒号、**71.4 万个**水下商家 | [楚天都市报（2026-08）](https://www.ctdsb.net/c1716_202608/2841307.html) |
| AI 托管账号 **超 110 万个**、AI 造假笔记近 **18 万篇** | [极目新闻/网易](https://www.163.com/dy/article/KT135FHU051494GR.html) |

现有鉴真能力大多只回答「图是不是 AI 生成的」。但真实作弊里有大量**图片本身真实、撒谎的是叙事**的情况：
同一张过敏照片被四个账号当成各自的遭遇、同一篇测评换个头像就宣称原创。
本数据集把这类样本单独建模（`recycled` / `reposted`），用来检验 Agent 是否具备
**跨帖比对、时间线分析、账号行为画像**的能力，而不只是单图分类。

---

## 1. 目录结构

```
GlowTrace-MM/
├── images/                     # 图像数据
│   ├── real/                   # 真实美妆图（含 3 张负样本示意图 + 1 张 TIGAS 真样本）
│   ├── ai_generated/           # AI 生成的美妆图（含 1 张 TIGAS 假样本）
│   ├── tampered/               # PS 篡改图 / 伪造截图
│   └── mismatch/               # 图文不符用的图（图A配文B）
├── texts/                      # 文本数据
│   ├── real_reviews/           # 真实的种草文案/评论
│   ├── fake_reviews/           # 大模型生成的虚假评论 / 伪造叙事
│   └── mismatched_prompts/     # 与 mismatch 图片配套的错误文案
├── annotations/                # 核心！所有的"大脑"
│   ├── dataset_index.csv       # 主索引表（最关键的表格）
│   ├── bboxes/                 # 伪造区域的坐标文件（json格式）
│   └── rationales/             # 可解释性判定依据（json格式）
└── README.md                   # 数据集说明书
```

**命名规则**：每个案例的所有文件共用同一个 `case_id` 前缀，例如
`case_id = post_a_28day` 对应：

| 文件 | 路径 |
|---|---|
| 伪造文案 | `texts/fake_reviews/post_a_28day.txt` |
| 对比图 | `images/tampered/post_a_28day_beforeafter.png` |
| 开箱图 | `images/ai_generated/post_a_28day_unboxing.png` |
| 图文矛盾图 | `images/mismatch/post_a_28day_wrong_product.png` |
| 坐标 | `annotations/bboxes/post_a_28day_bbox.json` |
| 判定依据 | `annotations/rationales/post_a_28day_rationale.json` |

这样任何一条 CSV 记录都能顺着 `case_id` 找到全部证据，不需要额外的映射表。

> **关于 `annotations/` 里的额外文件**：目录骨架严格按团队统一的 `格式.txt`（`dataset_index.csv` + `bboxes/` + `rationales/`）。
> 此外 `annotations/` 里还有**八个**约定之外的辅助文件，用来承载"叙事型造假"的结构化证据，不影响原有结构：
> - `timeline_post_a.json`、`timeline_post_a_samephoto.json`：商品晒单两个实例的账号注册与发帖时间线；
> - `timeline_complaint_b.json`、`timeline_complaint_b_photo_reuse.json`、`timeline_complaint_b_fivestar.json`：售后投诉三个实例的发布时间、集中度与账号历史；
> - `provenance_repost_c.json`、`provenance_repost_c_reworded.json`、`provenance_repost_c_renamed.json`：跨平台搬运三个实例的发布顺序、账号注册时间与文本/图片相似度。
>
> 需要回到最小结构时，删掉这八个文件、并移除 CSV 对应行的 `source` 引用即可（`verify_dataset.py` 不会因此报错）。

---

## 2. 三个场景 × 各 3 个实例

| case_id | 场景 | label_type | 造假机制（这个实例考什么） |
|---|---|---|---|
| `post_a_28day` | 商品晒单 | `ai_generated` | 4 天新号发「28 天实测」+ AI 开箱照 + 磨皮修图 + 图文语义矛盾 |
| `post_a_samephoto` | 商品晒单 | `tampered` | **同一张照片加一层暖色滤镜**，拆成「Day 1 / Day 28」冒充前后对比 |
| `complaint_b_recycled` | 售后投诉 | `recycled` | 4 个账号用同一张问题照片，**47 分钟内集中发布** |
| `complaint_b_photo_reuse` | 售后投诉 | `recycled` | 同一张照片**摊到 5 天分散发布**，且照片拍摄日期晚于第一条投诉 |
| `complaint_b_fivestar` | 售后投诉 | `recycled` | 四条配图**各不相同**（绕开图片查重），但正文同批、账号历史评价自相矛盾 |
| `repost_c_platform` | 跨平台搬运 | `reposted` | 换头像、**裁掉/遮挡原水印**，把同一测评冒充原创 |
| `repost_c_reworded` | 跨平台搬运 | `reposted` | **改写文案**（相似度约 0.70）但底图逐像素一致，水印处理干净 |
| `repost_c_renamed` | 跨平台搬运 | `reposted` | **换号改名**重新投放，头像相同、账号注册时间晚于画面最早的发布 |

每个场景另有 1 个**负样本对照**（`*_control` 系列），用来验证 Agent 不会「见到种草就报警」。
三组实例的设计意图是：**同一个场景里换个手法，检测思路就得跟着换**——集中发布改成发散发布、
修图痕迹改成整体调色、图片复用改成文本复用、裁水印改成改写文案。只堆同一种手法的样本，
考不出泛化能力。

---

## 3. annotations 字段定义

### 3.1 `dataset_index.csv` 主索引表

| 列名 | 含义 | 取值 |
|---|---|---|
| `case_id` | 案例唯一 ID | 字符串，同时是文件名前缀 |
| `scene` | 业务场景 | 商品晒单 / 售后投诉 / 跨平台搬运 / 负样本 |
| `label_type` | **伪造类型**（核心列） | `real` / `ai_generated` / `tampered` / `mismatch` / `recycled` / `reposted` |
| `label` | 二分类标签，供模型训练使用 | 0=真实，1=伪造 |
| `risk_level` | 风险等级 | 低风险 / 中风险 / 高风险 |
| `image_paths` | 相关图片，多张用 `；` 分隔 | 相对本目录的路径 |
| `text_path` | 配套文案（`-` 表示该行无文案，如 TIGAS 样张） | 相对本目录的路径 |
| `evidence_anchors` | 证据锚点编号，与 rationale 对应 | 如 `A1；A3；A6` |
| `fake_design` | 造假样本是怎么设计的（一句话） | 字符串 |
| `agent_expected` | 期望 Agent 找出的结论 | 字符串 |
| `source` | 图片/文案的原始出处或生成方式 | 平台链接 / 【本地合成】 |

> **为什么增加 `label_type` 而不只保留 `label`**：
> 「售后投诉」和「跨平台搬运」用的照片本身是真实的，撒谎的是"多账号独立遭遇"和"原创作者"
> 这两个叙事。若只用 0/1，这类样本会被迫归入 `real`，与"伪造"标签自相矛盾。
> `label_type` 显式区分「来源真伪」与「是否被滥用」，这是本数据集相对通用 deepfake 数据集的关键差异点。

### 3.2 `annotations/bboxes/*.json` — 篡改区域坐标

```json
{
  "case_id": "post_a_28day",
  "image": "images/tampered/post_a_28day_beforeafter.png",
  "image_size": { "width": 1200, "height": 800 },
  "coord": "normalized",
  "boxes": [
    {
      "box_id": "A1",
      "bbox": [0.52, 0.08, 0.46, 0.84],
      "region_type": "skin",
      "evidence": "右侧磨皮导致毛孔纹理完全消失",
      "confidence": 0.92
    }
  ]
}
```

- `coord` 取值 `normalized` 时 `bbox = [x, y, w, h]`，均为 0–1 相对值，与图片分辨率无关；
- `region_type ∈ {skin, label, watermark, tampering, ui, timeline, full}`（`tampering` 用于裁切像素带这类局部二次加工痕迹）；
- `evidence` 必须写成**能被复现的观察**（"毛孔纹理消失"），不能写成结论（"这是假的"）。

> **`box_id` 与 rationale 的 `evidence.id` 是交错关系，不是一一对应。**
> `bboxes/` 只收「能被像素与几何验证的篡改区域」（如 `A1` 磨皮、`A2` 光照不一致、`A5` 两瓶不是同一支、`A6` 拼接缝；
> 搬运案例里的 `C2-抖音像素带`、`C2-抖音空水印位`、`C3` 贴纸）；
> 而「产品名与配文不是同一个产品」（`A4`）这类语义证据没有坐标可言，只在 `rationales/` 里出现，
> 由它自己的 `anchor` 指向具体文件。三张 `*_control` 负样本图**故意不提供 bbox**，
> 因为「没有可指认的篡改区域」正是它的标注含义。

### 3.3 `annotations/rationales/*.json` — 判定依据

```json
{
  "case_id": "post_a_28day",
  "ground_truth": {
    "label_type": "ai_generated",
    "risk_level": "高风险",
    "evidence": [
      { "id": "A1", "type": "image", "anchor": "images/tampered/...png", "finding": "..." }
    ]
  },
  "expected_agent_output": {
    "ai_generated_probability": "高",
    "exaggerated_claims": [],
    "fake_endorsements": [],
    "image_tampering_suspected": true,
    "text_image_consistency": "不一致",
    "risk_level": "高风险",
    "reasoning": {
      "ai_detection_reason": "...",
      "exaggeration_reason": "...",
      "overall_reason": "..."
    },
    "suggestions": ["..."]
  }
}
```

`expected_agent_output` 的字段与 `content_verifier.py` 的输出**完全一致**，
因此 demo 时可以直接做结构化比对，不需要额外适配层。

---

## 4. 图片合成声明

本数据集 `images/` 下的图分三类，来源必须分开看：

| 目录 | 来源 | 说明 |
|---|---|---|
| `images/real/`、`images/ai_generated/` 中的 TIGAS 样张 | 比赛提供数据 | `tigas_real_face_00002.jpeg`、`tigas_fake_face_000907.jpeg`，**直接复制、不做任何处理**，用于「AI 生成人脸」这一独立检测维度 |
| `images/tampered/`、`images/mismatch/`、`images/ai_generated/post_a_28day_unboxing.png` | **本地程序合成**（Pillow） | 前后对比图、同图冒充对比图、开箱图、投诉墙 ×3、三平台并排图 ×3、图文矛盾图 |
| `images/real/*_control.jpg` | **本地程序合成**（Pillow） | 3 张负样本对照图，是「真实帖子长什么样」的示意图，**不是真实平台截图** |
| `images/tampered/repost_c_source_watermarked.png` | **本地程序合成**（Pillow） | 三平台并排图的**裁切件**（取小红书面板，500×675），用来单独展示带原始水印的首发版本 |

合成参数、随机种子与每张图的造假手法逐条记录在 `annotations/generation_meta.json`，
由 `tools/make_images.py` 一次生成，**可复现、可审计**：脚本里所有涉及随机性的绘制都固定了种子
（开箱图 `random.seed(99)`、投诉墙 `random.Random(4242)`、三平台并排图 `random.seed(777)`、
前后对比图的毛孔点 `random.seed(31)`、同图冒充对比图 `random.seed(2404)`），连跑两次得到**完全相同的 MD5**。
交付前另跑一遍 `tools/evidence_check.py`，用 Pillow/numpy 在像素层面复核本文档与 `rationales/` 里
「可复现的观察」是否真的成立（**34 项全过**，实测数字见其输出）。

> **合成图里刻意留下的可指认痕迹**（`annotations/bboxes/*.json` 的框就落在这些位置上）：
> - 前后对比图右侧的磨皮区与 8px 拼接缝；
> - 同图冒充对比图：左右两半底图逐像素同源（色度距离 1.35），差异只是整体亮暖偏移（右半亮度 +20）；
> - 开箱图纸盒结构、约 7px 的过密英文小字、右下角「AI 生成 · 演示用」角标；
> - 投诉墙左侧**四张像素一致的缩略图**（集中版与跨 5 天版两两差异 0.0000%）；五星冲突版刻意做成
>   **四条各不相同**（两两差异 40%+），并在卡间加金色对照说明；
> - 三平台并排图里小红书面板右下角的原始水印、抖音面板左边缘约 6px 的裁切像素带、微博面板右下角盖住水印位置的贴纸；
>   改写版的三块配图区逐像素一致（0.0000%）而正文区差异 14.93%；改名版配图区同样 0.0000%、署名行差异 8.84%。

> **合规说明**：合成图中出现的品牌名（澜本、肌活源、素研集、柔雾等）、账号名、用户昵称、"备案号"均为虚构，与真实品牌和个人无关；
> 所有"伪造"内容仅用于鉴真技术演示，不指向任何真实商品或商家。

---

## 5. 已知局限

1. 虽然是 3 个场景 × 3 个实例（共 9 个伪造 case + 3 个真实对照），**样本量仍不足以支撑统计结论**，
   demo 定位是「能力演示」而非「benchmark」；覆盖的是机制而不是场景全集（队友负责的另外五个场景不在此目录）。
2. **3 张负样本对照图（`images/real/*_control.jpg`）是示意图，不是真实平台截图**；
   时间线矛盾、账号历史等证据目前也只以 `annotations/` 中的结构化元数据（`timeline_*.json`、`provenance_*.json`）形式给出，
   尚未做成可截图的真实平台页面。因此 Agent 对这类证据的读取依赖我们提供的结构化输入，
   demo 时必须明确说明这一点，不能宣称"模型直接从原始网页推理出了时间线矛盾"。
3. 合成图的视觉真实度低于真实帖子，模型可能"靠画风"而不是"靠痕迹"判断，需要在 demo 中说明；
   真要把 visual realism 提上去，见文末「两种填充方式」——用真实帖子截图覆盖同名文件即可，`annotations/` 的结构不用动。
4. `images/` 下的合成图**不要裁切或缩放**：`annotations/bboxes/*.json` 用的是归一化坐标，
   但 `verify_dataset.py` 会校验实际像素尺寸与 `image_size` 一致，改尺寸会直接报错。
5. 图片是**程序合成**（Pillow 几何图形 + 程序排版）而非真实照片或生成模型输出，
   画风上更像「示意图」而不是「网图」，因此本数据集用于检验**证据链推理能力**（图文矛盾、素材复用、
   时间线冲突、水印处理、文本改写），**不适合**用来衡量模型对真实照片的感知鲁棒性。

> **交付前建议跑的两条命令**（都应退出码 0）：
>
> ```powershell
> $py = "<你的 Python 解释器路径>"   # 例如 (Get-Command python).Source
> & $py "tools/verify_dataset.py" --root "D:\欧莱雅黑客松\GlowTrace-MM"
> & $py "tools/evidence_check.py" --root "D:\欧莱雅黑客松\GlowTrace-MM"
> ```
>
> `verify_dataset.py` 检查五项：JSON 可解析、图片存在且在四个允许目录内、**`text_path` 指向的文案存在**、
> 图片像素尺寸与 bbox 声明一致、CSV 锚点能被 rationale 覆盖（当前：CSV 13 行、全部通过）。

> **关于图片素材的两种填充方式**（本 demo 允许任选其一，不影响 `annotations/` 的结构）：
>
> - **方式 A（推荐，真实感强）**：按各案例的「证据锚点」在小红书/抖音/微博上找到对应真实帖子，
>   用浏览器截图存入 `images/` 对应子目录，文件名与 `dataset_index.csv` 的 `image_paths` 保持一致。
>   此时 `source` 列填写真实帖子链接，`annotations/` 中的 `bbox` 坐标按截图实际尺寸重新归一化。
> - **方式 B（离线可复现）**：本地程序合成（Pillow / 截图合成页），
>   合成参数与随机种子记录在 `annotations/generation_meta.json`，`source` 列填【本地合成】。

## 附：图片可复现性（本轮重做材质渲染后的种子清单）

`tools/make_images.py` 全程只用 Pillow，且所有随机性都来自固定种子，同一份代码连跑两次
MD5 完全相同（已实测）。各图的种子/口径：

| 图 | 随机性来源 |
|---|---|
| `post_a_28day_beforeafter.png` | 毛孔点 `random.seed(31)`；`photo_finish(seed=31)` |
| `post_a_samephoto_sidebyside.png` | `random.seed(2404)`（脸只画一次，右半只加一层暖色滤镜） |
| `post_a_28day_unboxing.png` | `random.seed(99)`；`photo_finish(seed=99)` |
| `complaint_b_*.png`（3 张投诉墙） | 配图 `random.Random(4242)`；`fivestar` 的四格是"同源不同裁切"（`seed=5000+i*17`，`jitter=True`） |
| `repost_c_*.png`（3 张跨平台图） | `random.seed(777)`；商品图 `photo_product(seed=71)` |
| `post_a_28day_control.jpg` | `photo_finish(seed=41)` |
| `complaint_b_control.jpg` | `photo_finish(seed=77)` |
| `repost_c_control.jpg` | 商品图 `product_bottle` |
| `post_a_28day_wrong_product.png` | `photo_finish(seed=63)` |
| TIGAS 两张 | 直接从比赛数据复制，未做任何处理 |

校验层共 **34 项**（`tools/evidence_check.py`），其中 3 项检查三张控制图的文件时间是否等于
帖子时间 —— 重生成图片会把 mtime 刷掉，所以这两件事必须成对做。
