"""Generate unified modern flat 1024x1024 PNG and multi-layer ICO app icons."""

from __future__ import annotations

import math
import struct
from pathlib import Path
from PIL import Image, ImageDraw

CANVAS_SIZE = 1024
SUPERSAMPLE = 2
HI_SIZE = CANVAS_SIZE * SUPERSAMPLE  # 2048x2048

# ~8% outer margin on 1024x1024 -> 82px (164px at 2048x2048)
MARGIN_HI = 164
CORNER_RADIUS_HI = 440  # 220px at 1024x1024
BORDER_WIDTH_HI = 20    # 10px subtle inner highlight stroke at 1024x1024
STROKE_HI = 96          # 48px stroke width at 1024x1024 for crisp 16x16 scaling

ICO_SIZES = [16, 32, 48, 64, 128, 256]

APP_SPECS = {
    "drive_downloader": {
        "title": "DriveDownloader",
        "top_color": (59, 130, 246),    # #3B82F6
        "bottom_color": (29, 78, 216),  # #1D4ED8
    },
    "ocr_desktop": {
        "title": "OCRProcessor",
        "top_color": (20, 184, 166),    # #14B8A6
        "bottom_color": (15, 118, 110), # #0F766E
    },
    "batch_coder": {
        "title": "BatchCoder",
        "top_color": (99, 102, 241),    # #6366F1
        "bottom_color": (67, 56, 202),  # #4338CA
    },
    "single_coder_desktop": {
        "title": "SingleCoder",
        "top_color": (245, 158, 11),    # #F59E0B
        "bottom_color": (194, 65, 12),  # #C2410C
    },
    "highlighter_desktop": {
        "title": "Highlighter",
        "top_color": (244, 63, 94),     # #F43F5E
        "bottom_color": (190, 18, 60),  # #BE123C
    },
}


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))


def _create_rounded_gradient_base(top_color: tuple[int, int, int], bottom_color: tuple[int, int, int]) -> Image.Image:
    """Create the 2048x2048 rounded-rectangle base with vertical gradient and subtle highlight border."""
    x0, y0 = MARGIN_HI, MARGIN_HI
    x1, y1 = HI_SIZE - MARGIN_HI, HI_SIZE - MARGIN_HI

    # Vertical gradient image (1px wide, stretched horizontally for fast clean gradient)
    grad_strip = Image.new("RGBA", (1, HI_SIZE), (0, 0, 0, 0))
    span = max(1, y1 - y0)
    for y in range(HI_SIZE):
        t = min(1.0, max(0.0, (y - y0) / span))
        r, g, b = _lerp_color(top_color, bottom_color, t)
        grad_strip.putpixel((0, y), (r, g, b, 255))
    gradient_bg = grad_strip.resize((HI_SIZE, HI_SIZE), Image.Resampling.BILINEAR)

    # Rounded rectangle alpha mask
    mask = Image.new("L", (HI_SIZE, HI_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([x0, y0, x1, y1], radius=CORNER_RADIUS_HI, fill=255)

    canvas = Image.new("RGBA", (HI_SIZE, HI_SIZE), (0, 0, 0, 0))
    canvas.paste(gradient_bg, (0, 0), mask)

    # Subtle inner highlight stroke just inside the rounded rectangle edge
    border_layer = Image.new("RGBA", (HI_SIZE, HI_SIZE), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    inset = BORDER_WIDTH_HI // 2
    border_draw.rounded_rectangle(
        [x0 + inset, y0 + inset, x1 - inset, y1 - inset],
        radius=max(10, CORNER_RADIUS_HI - inset),
        outline=(255, 255, 255, 85),
        width=BORDER_WIDTH_HI,
    )
    canvas = Image.alpha_composite(canvas, border_layer)
    return canvas


def _draw_dot(draw: ImageDraw.ImageDraw, cx: float, cy: float, width: int, fill=(255, 255, 255, 255)) -> None:
    r = width / 2.0
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def _draw_segment(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    width: int,
    fill=(255, 255, 255, 255),
) -> None:
    draw.line([p1, p2], fill=fill, width=width)
    _draw_dot(draw, p1[0], p1[1], width, fill)
    _draw_dot(draw, p2[0], p2[1], width, fill)


def _draw_polyline(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    width: int,
    fill=(255, 255, 255, 255),
) -> None:
    for a, b in zip(points, points[1:]):
        _draw_segment(draw, a, b, width, fill)


def _draw_polygon_outline(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    width: int,
    fill=(255, 255, 255, 255),
) -> None:
    closed = list(points) + [points[0]]
    _draw_polyline(draw, closed, width, fill)


def _draw_glyph_drive_downloader(draw: ImageDraw.ImageDraw) -> None:
    """Cloud / open tray base + bold downward download arrow."""
    # Bold downward arrow centered slightly above tray
    _draw_segment(draw, (1024, 520), (1024, 1140), STROKE_HI)
    _draw_polyline(draw, [(760, 880), (1024, 1150), (1288, 880)], STROKE_HI)

    # Bold receiving tray (U-shaped dock tray)
    _draw_polyline(
        draw,
        [(560, 1120), (560, 1440), (1488, 1440), (1488, 1120)],
        STROKE_HI,
    )


def _draw_glyph_ocr_desktop(draw: ImageDraw.ImageDraw) -> None:
    """Document page outline with bold horizontal scan beam and text bars."""
    # Document outline with top-right folded corner
    doc_pts = [
        (640, 500),
        (1220, 500),
        (1408, 688),
        (1408, 1548),
        (640, 1548),
    ]
    _draw_polygon_outline(draw, doc_pts, STROKE_HI)
    _draw_polyline(draw, [(1220, 500), (1220, 688), (1408, 688)], STROKE_HI - 12)

    # Horizontal text bars inside document
    _draw_segment(draw, (800, 840), (1160, 840), STROKE_HI - 16)
    _draw_segment(draw, (800, 1320), (1248, 1320), STROKE_HI - 16)

    # Bold full-width OCR scan beam crossing the document
    _draw_segment(draw, (480, 1080), (1568, 1080), STROKE_HI + 12)


def _draw_glyph_batch_coder(draw: ImageDraw.ImageDraw) -> None:
    """Stacked documents with bold code brackets < >."""
    # Back stacked sheet offset (top-left peek)
    _draw_polyline(
        draw,
        [(540, 1280), (540, 520), (1260, 520)],
        STROKE_HI - 12,
    )
    # Front document card
    front_pts = [
        (700, 680),
        (1500, 680),
        (1500, 1520),
        (700, 1520),
    ]
    _draw_polygon_outline(draw, front_pts, STROKE_HI)

    # Bold code brackets < > inside front card
    _draw_polyline(draw, [(1020, 940), (860, 1100), (1020, 1260)], STROKE_HI - 8)
    _draw_polyline(draw, [(1180, 940), (1340, 1100), (1180, 1260)], STROKE_HI - 8)


def _draw_glyph_single_coder_desktop(draw: ImageDraw.ImageDraw) -> None:
    """Single document page with bold code braces { } and verification checkmark."""
    # Single document outline
    doc_pts = [
        (620, 480),
        (1428, 480),
        (1428, 1568),
        (620, 1568),
    ]
    _draw_polygon_outline(draw, doc_pts, STROKE_HI)

    # Top code braces { } hint via symmetric bracket chevrons
    _draw_polyline(draw, [(920, 740), (800, 860), (920, 980)], STROKE_HI - 12)
    _draw_polyline(draw, [(1128, 740), (1248, 860), (1128, 980)], STROKE_HI - 12)

    # Bold verification checkmark at lower center
    _draw_polyline(draw, [(830, 1240), (975, 1385), (1240, 1120)], STROKE_HI)


def _draw_glyph_highlighter_desktop(draw: ImageDraw.ImageDraw) -> None:
    """Angled bold highlighter marker nib and bright highlight underline bar."""
    # Angled marker body (rotated rectangle drawn with bold strokes)
    # Direction along 45 deg from bottom-left (700, 1220) toward top-right (1380, 540)
    marker_pts = [
        (720, 1120),
        (1200, 640),
        (1420, 860),
        (940, 1340),
    ]
    _draw_polygon_outline(draw, marker_pts, STROKE_HI - 8)

    # Chisel nib at bottom-left
    _draw_polyline(draw, [(720, 1120), (600, 1360), (940, 1340)], STROKE_HI - 10)

    # Bold horizontal highlight bar underneath
    _draw_segment(draw, (580, 1500), (1468, 1500), STROKE_HI + 10)


GLYPH_DRAWERS = {
    "drive_downloader": _draw_glyph_drive_downloader,
    "ocr_desktop": _draw_glyph_ocr_desktop,
    "batch_coder": _draw_glyph_batch_coder,
    "single_coder_desktop": _draw_glyph_single_coder_desktop,
    "highlighter_desktop": _draw_glyph_highlighter_desktop,
}


def render_app_icon(app_name: str) -> Image.Image:
    """Render a 1024x1024 RGBA icon with 2x supersampling."""
    spec = APP_SPECS[app_name]
    canvas_hi = _create_rounded_gradient_base(spec["top_color"], spec["bottom_color"])

    glyph_layer = Image.new("RGBA", (HI_SIZE, HI_SIZE), (0, 0, 0, 0))
    glyph_draw = ImageDraw.Draw(glyph_layer)
    GLYPH_DRAWERS[app_name](glyph_draw)

    combined_hi = Image.alpha_composite(canvas_hi, glyph_layer)
    return combined_hi.resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.LANCZOS)


def save_multilayer_ico(source_1024: Image.Image, ico_path: Path) -> None:
    """Save a standard multi-layer ICO containing 16, 32, 48, 64, 128, and 256 layers."""
    sizes = [(s, s) for s in ICO_SIZES]
    source_1024.save(ico_path, format="ICO", sizes=sizes)


def generate_preview_sheet(icons: dict[str, Image.Image], preview_path: Path) -> None:
    """Create a dark+light checkerboard-friendly preview grid of all 5 icons."""
    cols = len(icons)
    cell_w = 260
    cell_h = 300
    sheet = Image.new("RGBA", (cols * cell_w + 40, cell_h + 40), (240, 244, 248, 255))
    draw = ImageDraw.Draw(sheet)

    for idx, (app_name, icon_img) in enumerate(icons.items()):
        x = 20 + idx * cell_w
        y = 20
        thumb_large = icon_img.resize((200, 200), Image.Resampling.LANCZOS)
        thumb_16 = icon_img.resize((16, 16), Image.Resampling.LANCZOS)
        thumb_32 = icon_img.resize((32, 32), Image.Resampling.LANCZOS)
        sheet.paste(thumb_large, (x + 30, y + 10), thumb_large)
        sheet.paste(thumb_32, (x + 80, y + 225), thumb_32)
        sheet.paste(thumb_16, (x + 135, y + 233), thumb_16)
        draw.text((x + 30, y + 270), APP_SPECS[app_name]["title"], fill=(30, 41, 59, 255))

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(preview_path, format="PNG")


def verify_ico_layers(ico_path: Path) -> list[int]:
    """Read ICO header and return list of embedded pixel widths."""
    raw = ico_path.read_bytes()
    reserved, img_type, count = struct.unpack("<HHH", raw[:6])
    if reserved != 0 or img_type != 1:
        raise ValueError(f"Invalid ICO header in {ico_path}")
    widths = []
    for i in range(count):
        base = 6 + i * 16
        w_byte = raw[base]
        widths.append(256 if w_byte == 0 else w_byte)
    return widths


def main() -> None:
    icons_dir = Path(__file__).resolve().parent
    rendered: dict[str, Image.Image] = {}

    for app_name in APP_SPECS:
        icon_1024 = render_app_icon(app_name)
        rendered[app_name] = icon_1024

        png_path = icons_dir / f"{app_name}.png"
        ico_path = icons_dir / f"{app_name}.ico"

        icon_1024.save(png_path, format="PNG")
        save_multilayer_ico(icon_1024, ico_path)

        layers = verify_ico_layers(ico_path)
        print(f"Generated {png_path.name} ({icon_1024.size}) & {ico_path.name} layers={layers}")
        if layers != ICO_SIZES:
            raise RuntimeError(f"ICO layers mismatch for {ico_path}: got {layers}, expected {ICO_SIZES}")

    preview_out = Path("/mnt/c/LocalD/antigravity/MMIWG/icons_preview.png")
    if preview_out.parent.exists():
        generate_preview_sheet(rendered, preview_out)
        print(f"Saved visual preview sheet: {preview_out}")


if __name__ == "__main__":
    main()
