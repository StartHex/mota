#!/usr/bin/env python3
"""把 AI 生成的大图处理成 32×32 游戏精灵。

做四件事：
  1. 居中裁掉四周（默认各 17.5%），把豆包等工具的水印切掉
  2. 抠掉纯色底（品红 #FF00FF 或绿 #00FF00），带边缘去色处理
  3. 裁到内容边界
  4. 最近邻缩放到 32×32，存成 PNG

用法：
    python3 tools/prep_sprite.py raw/anglerfish.png -o assets/sprites/mon-anglerfish.png
    python3 tools/prep_sprite.py raw/*.png -o assets/sprites/ --key green --crop 0.2

不给 -o 时，输出到同目录的 <name>_32.png，方便先看效果。
"""
import argparse
import pathlib
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("需要 Pillow：pip install Pillow")


def center_crop(im, keep):
    """保留画面中央 keep 比例的区域。"""
    if keep >= 1.0:
        return im
    w, h = im.size
    nw, nh = int(w * keep), int(h * keep)
    x, y = (w - nw) // 2, (h - nh) // 2
    return im.crop((x, y, x + nw, y + nh))


def despeckle_alpha(alpha, radius=2):
    """把底色残留的孤立像素收掉，避免边缘一圈杂色。"""
    from PIL import ImageFilter
    return alpha.filter(ImageFilter.MinFilter(radius * 2 + 1)).filter(
        ImageFilter.MaxFilter(radius * 2 + 1))


def erase_corner(im, wx, wy):
    """把右下角的水印区域直接清成透明（豆包水印固定在角上）。"""
    w, h = im.size
    box = (int(w * wx), int(h * wy), w, h)
    im.paste((0, 0, 0, 0), box)
    return im


def key_out(im, color, tol, soft):
    """按颜色抠底，返回带 alpha 的 RGBA。"""
    im = im.convert("RGBA")
    rgb = im.convert("RGB")
    target = Image.new("RGB", im.size, color)
    diff = ImageChops.difference(rgb, target).convert("L")
    # 距离小于 tol 视为背景，tol~tol+soft 之间做半透明过渡
    lut = []
    for v in range(256):
        if v <= tol:
            lut.append(0)
        elif v >= tol + soft:
            lut.append(255)
        else:
            lut.append(int(255 * (v - tol) / max(1, soft)))
    alpha = diff.point(lut)
    alpha = despeckle_alpha(alpha)
    im.putalpha(alpha)
    return im


def trim(im, pad=1):
    """裁到不透明内容的边界，四周留 pad 像素。"""
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return im
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(im.width, x1 + pad), min(im.height, y1 + pad)
    return im.crop((x0, y0, x1, y1))


def fit_square(im, size):
    """等比缩放到 size，居中放进 size×size 透明画布。"""
    im.thumbnail((size, size), Image.NEAREST)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return canvas


KEYS = {
    "magenta": (255, 0, 255),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
}


def process(src, dst, key, crop, tol, soft, size, erase):
    im = Image.open(src)
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    im = key_out(im, KEYS[key], tol, soft)
    if erase:
        im = erase_corner(im, *erase)
    im = center_crop(im, 1.0 - crop * 2)
    im = trim(im)
    if im.width == 0 or im.height == 0:
        raise SystemExit(f"{src}: 抠完什么都不剩，检查底色或 --key 参数")
    im = fit_square(im, size)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=pathlib.Path)
    ap.add_argument("-o", "--out", type=pathlib.Path,
                    help="输出文件；多个输入时必须是目录")
    ap.add_argument("--key", default="magenta", choices=KEYS.keys(),
                    help="底色：magenta(#FF00FF) / green(#00FF00) / blue")
    ap.add_argument("--crop", type=float, default=0.0,
                    help="四周各裁掉的比例，默认 0（不裁）。水印用 --erase-corner 处理更安全")
    ap.add_argument("--tol", type=int, default=60, help="抠图容差，默认 60")
    ap.add_argument("--soft", type=int, default=40, help="边缘过渡宽度，默认 40")
    ap.add_argument("--size", type=int, default=32, help="输出尺寸，默认 32")
    ap.add_argument("--erase-corner", action="store_true",
                    help="先清掉右下角水印区（默认从 80%%/88%% 起），比裁边安全，不伤主体")
    args = ap.parse_args()

    multi = len(args.inputs) > 1
    if multi and args.out and not args.out.is_dir():
        sys.exit("-o 是目录才能一次处理多个文件")

    for src in args.inputs:
        if args.out is None:
            dst = src.with_name(src.stem + f"_{args.size}.png")
        elif multi:
            dst = args.out / (src.stem + ".png")
        else:
            dst = args.out
        try:
            erase = (0.80, 0.88) if args.erase_corner else None
            process(src, dst, args.key, args.crop, args.tol, args.soft, args.size, erase)
            print(f"{src.name} -> {dst}")
        except Exception as e:  # noqa: BLE001
            print(f"{src.name}: 失败 {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
