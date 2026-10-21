"""Generate Dinglong Mahjong raster icons with Pillow and a system Kai font.

Run: .venv-tools/Scripts/python.exe frontend/scripts/generate-icons.py
Override font: --font C:/Windows/Fonts/STKAITI.TTF
"""

import argparse
from math import hypot
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SIZE = 2048  # Draw at 2x, then downsample for smooth small icons.
BG = "#06221D"
GOLD = "#C7A555"
OUTPUTS = []


def save(image, path, size=None, mode=None):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    if size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    if mode:
        image = image.convert(mode)
    image.save(path)
    OUTPUTS.append((path, image.size, image.mode))


def tile(font_path):
    art = Image.new("RGBA", (SIZE, SIZE))
    shadow = Image.new("RGBA", art.size)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (448, 310, 1600, 1760), radius=140, fill=(0, 0, 0, 65)
    )
    art = Image.alpha_composite(art, shadow.filter(ImageFilter.GaussianBlur(22)))
    draw = ImageDraw.Draw(art)
    draw.rounded_rectangle((448, 280, 1600, 1728), 140, fill="#184C43")
    draw.rounded_rectangle((448, 280, 1600, 1688), 140, fill="#2C7564")
    draw.rounded_rectangle((448, 280, 1600, 1638), 140, fill="#D8D4C8")
    draw.rounded_rectangle((454, 280, 1594, 1620), 136, fill="#F4F0E5")
    # Fine inset edge and upper highlight give depth without visual texture.
    draw.rounded_rectangle((474, 300, 1574, 1600), 116, outline="#DFDBCE", width=5)
    draw.line((590, 304, 1458, 304), fill="#FFFCF3", width=7)
    font = ImageFont.truetype(str(font_path), 1080)
    mask = Image.new("L", art.size)
    md = ImageDraw.Draw(mask)
    bounds = md.textbbox((0, 0), "發", font=font, stroke_width=2)
    x = (SIZE - (bounds[2] - bounds[0])) // 2 - bounds[0]
    y = (1900 - (bounds[3] - bounds[1])) // 2 - bounds[1]
    md.text((x, y), "發", font=font, fill=255, stroke_width=2)
    gradient = Image.new("RGBA", art.size)
    gd = ImageDraw.Draw(gradient)
    for row in range(SIZE):
        t = min(1, max(0, (row - 500) / 1000))
        color = tuple(round(a + (b - a) * t) for a, b in zip((25, 123, 78), (12, 81, 52)))
        gd.line((0, row, SIZE, row), fill=color + (255,))
    art.paste(gradient, (0, 0), mask)
    return art


def background(shape):
    image = Image.new("RGBA", (SIZE, SIZE))
    draw = ImageDraw.Draw(image)
    if shape == "round":
        draw.ellipse((0, 0, SIZE - 1, SIZE - 1), fill=BG)
        draw.ellipse((70, 70, SIZE - 71, SIZE - 71), outline=GOLD, width=4)
    else:
        draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), 360, fill=BG)
        draw.rounded_rectangle((70, 70, SIZE - 71, SIZE - 71), 302, outline=GOLD, width=4)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/simkai.ttf"))
    args = parser.parse_args()
    if not args.font.is_file():
        parser.error("Kai font not found; specify a system font with --font")
    art = tile(args.font)
    square = Image.alpha_composite(background("square"), art)
    circle = Image.alpha_composite(background("round"), art)
    # Clip even the shadow to the circular launcher mask.
    circle.putalpha(background("round").getchannel("A"))
    save(square, "resources/icon.png", (1024, 1024))
    # Keep the entire foreground bounding rectangle inside a 64% diameter
    # circle, leaving margin within Android's central 66% safe zone.
    crop = art.crop(art.getbbox())
    factor = SIZE * .64 / hypot(*crop.size)
    crop = crop.resize(tuple(round(n * factor) for n in crop.size), Image.Resampling.LANCZOS)
    foreground = Image.new("RGBA", art.size)
    foreground.alpha_composite(crop, ((SIZE - crop.width) // 2, (SIZE - crop.height) // 2))
    save(foreground, "resources/icon-foreground.png", (1024, 1024))
    res = Path("android/app/src/main/res")
    for density, size in zip(("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"), (48, 72, 96, 144, 192)):
        folder = res / f"mipmap-{density}"
        save(square, folder / "ic_launcher.png", (size, size))
        save(circle, folder / "ic_launcher_round.png", (size, size))
        adaptive_size = size * 9 // 4
        save(foreground, folder / "ic_launcher_foreground.png", (adaptive_size, adaptive_size))
    (ROOT / res / "values/ic_launcher_background.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        '    <color name="ic_launcher_background">#06221D</color>\n</resources>\n', encoding="utf-8"
    )
    # iOS supplies the corner mask; fill source corners with opaque brand green.
    ios = Image.new("RGBA", square.size, BG)
    ios.alpha_composite(square)
    save(ios, "ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png", (1024, 1024), "RGB")
    for name, size in (("favicon.png", 32), ("favicon-192.png", 192), ("apple-touch-icon.png", 180)):
        save(ios if size == 180 else square, Path("public") / name, (size, size), "RGB" if size == 180 else "RGBA")
    for path in sorted((ROOT / res).glob("drawable*/splash.png")):
        with Image.open(path) as old:
            dimensions = old.size
        splash = Image.new("RGBA", dimensions, BG)
        side = round(min(dimensions) * .34)
        small = art.resize((side, side), Image.Resampling.LANCZOS)
        splash.alpha_composite(small, ((dimensions[0] - side) // 2, (dimensions[1] - side) // 2))
        save(splash, path.relative_to(ROOT), mode="RGB")
    preview = Image.new("RGB", (1600, 1120), "#E4E5DE")
    pd = ImageDraw.Draw(preview)
    label_font = ImageFont.truetype(str(args.font), 25)
    preview.paste(square.resize((1024, 1024), Image.Resampling.LANCZOS), (24, 48), square.resize((1024, 1024), Image.Resampling.LANCZOS))
    pd.text((24, 12), "1024", font=label_font, fill=BG)
    for y, size in ((70, 192), (400, 96), (640, 48)):
        pd.text((1090, y - 35), str(size), font=label_font, fill=BG)
        for x, source in ((1090, square), (1340, circle)):
            icon = source.resize((size, size), Image.Resampling.LANCZOS)
            preview.paste(icon, (x, y), icon)
    save(preview, "resources/icon-preview.png")
    # Reopen every file to validate the actual encoded dimensions and mode.
    for path, size, mode in OUTPUTS:
        with Image.open(path) as result:
            assert result.size == size, f"Wrong size: {path}"
            assert result.mode == mode, f"Wrong mode: {path}"
            result.load()
            print(f"{path.relative_to(ROOT).as_posix()}: {size[0]}x{size[1]} {mode} OK")
    with Image.open(ROOT / "resources/icon-foreground.png") as check:
        alpha = check.getchannel("A")
        safe = Image.new("L", check.size)
        ImageDraw.Draw(safe).ellipse((174, 174, 850, 850), fill=255)
        assert ImageChops.subtract(alpha, safe).getbbox() is None, "Foreground outside 66% safe zone"
    print(f"Verified {len(OUTPUTS)} PNG files; adaptive safe zone OK; iOS RGB OK.")


if __name__ == "__main__":
    main()
