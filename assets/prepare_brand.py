"""准备用户提供的品牌素材；仅素材维护时需要 Pillow，应用运行无此依赖。"""
import base64
from pathlib import Path
import sys

from PIL import Image


def main():
    root = Path(__file__).resolve().parent
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "brand.png"
    original = source.read_bytes()
    image = Image.open(source).convert("RGBA")
    (root / "brand.png").write_bytes(original)
    for scale, height in ((100, 42), (125, 53), (150, 63)):
        width = round(image.width * height / image.height)
        image.resize((width, height), Image.Resampling.LANCZOS).save(root / f"brand-header-{scale}.png")
    # 图形标识与右侧文字之间的透明留白，分离符号用于方形窗口图标。
    alpha = image.getchannel("A")
    gap_start = None
    for x in range(image.width):
        empty = alpha.crop((x, 0, x + 1, image.height)).getbbox() is None
        if empty:
            gap_start = x if gap_start is None else gap_start
            if x - gap_start >= 16:
                break
        else:
            gap_start = None
    if gap_start is None:
        raise ValueError("未找到标识图形与文字之间的透明留白")
    symbol = image.crop((0, 0, gap_start, image.height))
    symbol = symbol.crop(symbol.getbbox())
    symbol.thumbnail((216, 216), Image.Resampling.LANCZOS)
    icon = Image.new("RGBA", (256, 256))
    icon.alpha_composite(symbol, ((256-symbol.width)//2, (256-symbol.height)//2))
    icon.save(root / "icon.png")
    icon.save(root / "icon.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    encoded = base64.b64encode((root / "icon.png").read_bytes()).decode("ascii")
    (root / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        f'<image width="256" height="256" href="data:image/png;base64,{encoded}"/></svg>\n', encoding="utf-8")
    print("品牌原图、三档页眉素材及窗口图标已准备。")


if __name__ == "__main__":
    main()
