# GlowTrace-MM 纹理素材说明

## 目录结构

```
textures/
├── product/           # 真实产品照片（护肤品瓶、精华、面霜等）
│   ├── beauty-product-table-1.jpg
│   ├── cosmetic-bottle-elegant-1.jpg
│   ├── cosmetic-bottle-white-1.jpg
│   ├── foundation-bottle-dropper-1.jpg
│   ├── serum-bottle-dropper-1.jpg
│   ├── serum-dropper-product-1.jpg
│   ├── skincare-bottle-amber-1.jpg
│   ├── skincare-marble-bottle-1.jpg
│   └── skincare-product-group-1.jpg
├── skin/              # 真实皮肤纹理照片（面部特写、皮肤细节）
│   ├── face-skincare-application-1.jpg
│   ├── skin-care-routine-1.jpg
│   ├── skin-macro-pores-1.jpg
│   ├── skin-texture-cheek-1.jpg
│   ├── skin-texture-closeup-1.jpg
│   └── skin-texture-face-1.jpg
└── README.md          # 本文件
```

## 素材来源

- **product/** — Unsplash, Pexels 免费商用的护肤品/美妆产品实拍照片
- **skin/** — Unsplash 免费商用的面部皮肤特写照片

## 使用说明

`tools/make_images.py` 中的纹理引擎会自动按以下优先级搜索素材：

1. `textures/product/` 或 `textures/skin/`（最高优先级）
2. `TIGAS_data/real/`（TIGAS 真实人脸）
3. `素材/图片/`（素材图片）
4. 程序生成兜底（当所有真实照片都无法加载时）

如需补充素材，直接将图片放入对应目录即可，无需修改代码。