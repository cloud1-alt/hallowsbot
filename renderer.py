"""
renderer.py — Inventário clean com tema Hallows. Render direto em 1x, fontes grandes.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import math
import os

# ─── Paleta ────────────────────────────────────────────────────────────────────
BG_DARK      = (13, 11, 9)
BG_PANEL     = (20, 17, 13)
BG_CARD      = (26, 22, 16)
BG_CARD_TOP  = (32, 26, 18)
ORANGE_MAIN  = (255, 110, 0)
ORANGE_LIGHT = (255, 175, 70)
ORANGE_DIM   = (160, 70, 0)
TEXT_WHITE   = (242, 238, 230)
TEXT_MUTED   = (140, 130, 112)
TEXT_GREEN   = (72, 210, 110)
SERIAL_COLOR = (255, 200, 70)
DIVIDER      = (40, 34, 24)

# ─── Layout ────────────────────────────────────────────────────────────────────
IMG_WIDTH = 1000
COLS      = 5
CARD_W    = 175
CARD_H    = 270
CARD_PAD  = 12
HEADER_H  = 110
SIDE_PAD  = 22
FOOTER_H  = 8

# ─── Fontes ────────────────────────────────────────────────────────────────────
def load_font(size: int, bold: bool = False):
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ─── Helpers ───────────────────────────────────────────────────────────────────
def fmt_number(n) -> str:
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))

def paste_centered(base, overlay, cx, cy):
    x = cx - overlay.width // 2
    y = cy - overlay.height // 2
    if overlay.mode == "RGBA":
        base.paste(overlay, (x, y), overlay)
    else:
        base.paste(overlay, (x, y))

def draw_soft_shadow(img, xy, radius=10, strength=60):
    x0, y0, x1, y1 = xy
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([x0+3, y0+5, x1+3, y1+5], radius=radius, fill=(0,0,0,strength))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    img.paste(shadow, mask=shadow)

def draw_hold_clock(img, cx, cy, r=13):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(18, 14, 9, 230))
    ld.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(*ORANGE_MAIN, 255), width=2)
    # minuto (12h)
    ld.line([(cx, cy), (cx, cy - int(r*0.65))], fill=(*TEXT_WHITE, 220), width=2)
    # hora (3h)
    ld.line([(cx, cy), (cx + int(r*0.45), cy)], fill=(*ORANGE_LIGHT, 220), width=2)
    ld.ellipse([cx-2, cy-2, cx+2, cy+2], fill=(*ORANGE_LIGHT, 255))
    img.paste(layer, mask=layer)

def draw_quantity_badge(draw, x1, y1, quantity, font):
    text = f"x{quantity}"
    tw = int(draw.textlength(text, font=font))
    px, py = 7, 4
    bx1 = x1 - 7
    by1 = y1 - 7
    bx0 = bx1 - tw - px*2
    by0 = by1 - 20 - py*2
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6,
                           fill=(*BG_DARK, 220), outline=(*ORANGE_MAIN,), width=1)
    draw.text((bx0+px, by0+py), text, font=font, fill=ORANGE_LIGHT)

def make_bg(width, height):
    bg = Image.new("RGBA", (width, height), (*BG_DARK, 255))
    hallows_path = os.path.join(os.path.dirname(__file__), "hallows.png")
    if os.path.exists(hallows_path):
        tile_src = Image.open(hallows_path).convert("RGBA")
        tile = tile_src.resize((90, 90), Image.LANCZOS)
        r2, g2, b2, a2 = tile.split()
        a2 = a2.point(lambda x: int(x * 0.07))
        tile.putalpha(a2)
        step = 108
        for ry in range(0, height + step, step):
            for rx in range(0, width + step, step):
                bg.paste(tile, (rx, ry), tile)
    ov = Image.new("RGBA", (width, height), (*BG_DARK, 155))
    bg = Image.alpha_composite(bg, ov)
    return bg.convert("RGB")

# ─── Renderer principal ────────────────────────────────────────────────────────
def render_inventory_image(
    username: str,
    user_id: int,
    total_value: int,
    total_rap: int,
    item_count: int,
    items: list,
    thumb_images: dict,
    avatar_bytes,
) -> bytes:

    rows = math.ceil(len(items) / COLS)
    grid_h = rows * (CARD_H + CARD_PAD) + CARD_PAD
    img_height = HEADER_H + grid_h + FOOTER_H + 10

    img = make_bg(IMG_WIDTH, img_height)
    draw = ImageDraw.Draw(img)

    # ── Fontes ────────────────────────────────────────────────────────────────
    font_username  = load_font(26, bold=True)
    font_stat_val  = load_font(18, bold=True)
    font_stat_lbl  = load_font(13)
    font_item_name = load_font(17, bold=True)
    font_item_val  = load_font(18, bold=True)
    font_item_lbl  = load_font(14)
    font_serial    = load_font(13)
    font_badge     = load_font(14, bold=True)

    # ── HEADER ────────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, IMG_WIDTH, 3], fill=ORANGE_MAIN)
    draw.rectangle([0, 0, IMG_WIDTH, HEADER_H], fill=BG_PANEL)
    draw.line([(0, HEADER_H), (IMG_WIDTH, HEADER_H)], fill=DIVIDER, width=1)

    # Avatar
    av_x, av_y = SIDE_PAD, 16
    av_size = 70
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av = av.resize((av_size, av_size), Image.LANCZOS)
            ring = Image.new("RGBA", (av_size+6, av_size+6), (0,0,0,0))
            ImageDraw.Draw(ring).ellipse([0, 0, av_size+5, av_size+5], fill=ORANGE_MAIN)
            img.paste(ring.convert("RGB"), (av_x-3, av_y-3))
            mask = Image.new("L", (av_size, av_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, av_size, av_size], fill=255)
            img.paste(av, (av_x, av_y), mask)
        except Exception:
            pass

    # Nome
    nx = av_x + av_size + 16
    draw.text((nx, av_y + 4), username, font=font_username, fill=TEXT_WHITE)

    # Stats em pills
    stats = [("VALUE", fmt_number(total_value)), ("RAP", fmt_number(total_rap)), ("ITEMS", str(item_count))]
    sx = nx
    sy = av_y + 42
    for label, val in stats:
        lw = int(draw.textlength(label, font=font_stat_lbl))
        vw = int(draw.textlength(val, font=font_stat_val))
        pw = lw + vw + 22
        ph = 28
        draw.rounded_rectangle([sx, sy, sx+pw, sy+ph], radius=6, fill=BG_CARD)
        draw.text((sx+8, sy+7), label, font=font_stat_lbl, fill=TEXT_MUTED)
        draw.text((sx+10+lw, sy+5), val, font=font_stat_val, fill=ORANGE_LIGHT)
        sx += pw + 10

    # ── GRID ──────────────────────────────────────────────────────────────────
    total_grid_w = COLS * CARD_W + (COLS-1) * CARD_PAD
    gx = (IMG_WIDTH - total_grid_w) // 2

    for idx, item in enumerate(items):
        col = idx % COLS
        row = idx // COLS

        x0 = gx + col * (CARD_W + CARD_PAD)
        y0 = HEADER_H + CARD_PAD + row * (CARD_H + CARD_PAD)
        x1 = x0 + CARD_W
        y1 = y0 + CARD_H

        draw_soft_shadow(img, (x0, y0, x1, y1), radius=10)

        # Card fundo
        draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=BG_CARD)
        # Faixa superior mais clara
        split_y = y0 + int(CARD_H * 0.60)
        draw.rounded_rectangle([x0, y0, x1, split_y], radius=10, fill=BG_CARD_TOP)
        draw.rectangle([x0, split_y-10, x1, split_y], fill=BG_CARD_TOP)
        # Borda
        draw.rounded_rectangle([x0, y0, x1, y1], radius=10, outline=ORANGE_DIM, width=1)
        # Separador
        draw.line([(x0+10, split_y), (x1-10, split_y)], fill=DIVIDER, width=1)

        # Hold clock
        if item.get("on_hold"):
            draw_hold_clock(img, x0+16, y0+16, r=13)

        # Thumbnail
        th_size = int(CARD_W * 0.80)
        thumb_cx = x0 + CARD_W // 2
        thumb_cy = y0 + int(CARD_H * 0.30)
        tb = thumb_images.get(item["assetId"])
        if tb:
            try:
                th = Image.open(io.BytesIO(tb)).convert("RGBA")
                th = th.resize((th_size, th_size), Image.LANCZOS)
                paste_centered(img, th, thumb_cx, thumb_cy)
            except Exception:
                pass
        else:
            ph = th_size
            px0 = thumb_cx - ph//2
            py0 = thumb_cy - ph//2
            draw.rounded_rectangle([px0, py0, px0+ph, py0+ph], radius=6, fill=(32,26,18))
            draw.text((px0+ph//2-10, py0+ph//2-14), "?", font=load_font(22), fill=TEXT_MUTED)

        # Nome (2 linhas)
        name   = item.get("name", "Unknown")
        name_y = split_y + 8
        words  = name.split()
        lines, cur = [], ""
        for w in words:
            test = (cur+" "+w).strip()
            if draw.textlength(test, font=font_item_name) <= CARD_W - 16:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        lines = lines[:2]

        for i, line in enumerate(lines):
            tw = int(draw.textlength(line, font=font_item_name))
            draw.text((x0 + (CARD_W-tw)//2, name_y + i*20), line, font=font_item_name, fill=TEXT_WHITE)

        # RAP + Value
        rap   = item.get("rap")
        value = item.get("value")
        serial = item.get("serial")
        info_y = y1 - 62

        # RAP linha
        rap_lbl = "RAP"
        rap_val = fmt_number(rap) if rap else "—"
        lw = int(draw.textlength(rap_lbl, font=font_item_lbl))
        vw = int(draw.textlength(rap_val, font=font_item_val))
        rx = x0 + (CARD_W - lw - 8 - vw) // 2
        draw.text((rx, info_y), rap_lbl, font=font_item_lbl, fill=TEXT_MUTED)
        draw.text((rx+lw+8, info_y-2), rap_val, font=font_item_val, fill=TEXT_MUTED)

        # Value
        val_str = fmt_number(value) if value else "—"
        val_color = TEXT_GREEN if value and value > (rap or 0) else ORANGE_LIGHT
        vw2 = int(draw.textlength(val_str, font=font_item_val))
        draw.text((x0+(CARD_W-vw2)//2, info_y+22), val_str, font=font_item_val, fill=val_color)

        # Serial
        if serial:
            sstr = f"#{serial}"
            sw = int(draw.textlength(sstr, font=font_serial))
            draw.text((x0+(CARD_W-sw)//2, info_y+44), sstr, font=font_serial, fill=SERIAL_COLOR)

        # Badge quantidade
        if item.get("quantity", 1) > 1:
            draw_quantity_badge(draw, x1, y1, item["quantity"], font_badge)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    draw.rectangle([0, img_height-FOOTER_H, IMG_WIDTH, img_height], fill=ORANGE_MAIN)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out.read()
