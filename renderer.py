"""
renderer.py — Inventário estilo moderno/clean com tema Hallows.
Renderiza em 2x internamente e reduz para 1x no output (supersampling anti-aliasing).
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import math
import os

# ─── Escala de supersampling ───────────────────────────────────────────────────
S = 2  # fator de escala interno (2x → downscale para 1x no output)

# ─── Paleta ────────────────────────────────────────────────────────────────────
BG_DARK      = (13, 11, 9)
BG_PANEL     = (20, 17, 13)
BG_CARD      = (26, 22, 16)
BG_CARD_TOP  = (32, 26, 18)
ORANGE_MAIN  = (255, 110, 0)
ORANGE_LIGHT = (255, 175, 70)
ORANGE_DIM   = (180, 80, 0)
TEXT_WHITE   = (242, 238, 230)
TEXT_MUTED   = (140, 130, 112)
TEXT_GREEN   = (72, 210, 110)
SERIAL_COLOR = (255, 200, 70)
DIVIDER      = (38, 32, 22)

# ─── Layout base (1x) — internamente multiplicado por S ────────────────────────
IMG_WIDTH  = 1080
COLS       = 5
CARD_W     = 196
CARD_H     = 260
CARD_PAD   = 12
HEADER_H   = 115
SIDE_PAD   = 24
FOOTER_H   = 8


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
                return ImageFont.truetype(path, size * S)
            except Exception:
                pass
    return ImageFont.load_default()


# ─── Helpers ───────────────────────────────────────────────────────────────────
def s(n): return int(n * S)  # escala um valor para o espaço 2x


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


def draw_soft_shadow(img, xy, radius=12, alpha=80):
    """Sombra suave sob o card via blur."""
    x0, y0, x1, y1 = xy
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([x0 + s(2), y0 + s(4), x1 + s(2), y1 + s(4)],
                         radius=radius, fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=s(6)))
    img.paste(shadow, mask=shadow)


def draw_hold_clock(img, cx, cy, r=12):
    """Ícone de relógio vetorial limpo no canto do card."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    # Fundo com borda
    ld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 14, 9, 230))
    ld.ellipse([cx - r, cy - r, cx + r, cy + r],
               outline=(*ORANGE_MAIN, 255), width=max(1, r // 6))

    # Ponteiro dos minutos (12h)
    ml = int(r * 0.65)
    ld.line([(cx, cy), (cx, cy - ml)], fill=(*TEXT_WHITE, 230), width=max(1, r // 7))
    # Ponteiro das horas (3h)
    hl = int(r * 0.45)
    ld.line([(cx, cy), (cx + hl, cy)], fill=(*ORANGE_LIGHT, 230), width=max(1, r // 6))
    # Centro
    ld.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(*ORANGE_LIGHT, 255))

    img.paste(layer, mask=layer)


def draw_quantity_badge(draw, x1, y1, quantity, font):
    """Badge x2 no canto inferior direito."""
    text = f"x{quantity}"
    tw = int(draw.textlength(text, font=font))
    px, py = s(6), s(3)
    bx1 = x1 - s(6)
    by1 = y1 - s(6)
    bx0 = bx1 - tw - px * 2
    by0 = by1 - s(16) - py * 2
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=s(5),
                           fill=(*BG_DARK, 220), outline=(*ORANGE_MAIN,), width=s(1))
    draw.text((bx0 + px, by0 + py), text, font=font, fill=ORANGE_LIGHT)


def make_bg(width, height):
    """Fundo escuro com tile do Hallows muito sutil + vinheta nas bordas."""
    bg = Image.new("RGBA", (width, height), (*BG_DARK, 255))

    hallows_path = os.path.join(os.path.dirname(__file__), "hallows.png")
    if os.path.exists(hallows_path):
        tile_src = Image.open(hallows_path).convert("RGBA")
        tile_size = s(80)
        tile = tile_src.resize((tile_size, tile_size), Image.LANCZOS)
        r2, g2, b2, a2 = tile.split()
        a2 = a2.point(lambda x: int(x * 0.07))  # muito sutil: 7%
        tile.putalpha(a2)
        step = tile_size + s(18)
        for ry in range(0, height + step, step):
            for rx in range(0, width + step, step):
                bg.paste(tile, (rx, ry), tile)

    # Overlay escuro para não competir com os cards
    ov = Image.new("RGBA", (width, height), (*BG_DARK, 160))
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
    img_height = HEADER_H + grid_h + FOOTER_H + 16

    # ── Canvas 2x ─────────────────────────────────────────────────────────────
    W = s(IMG_WIDTH)
    H = s(img_height)

    bg = make_bg(W, H)
    img = bg.copy()
    draw = ImageDraw.Draw(img)

    # ── Fontes (já em 2x via load_font) ───────────────────────────────────────
    font_username  = load_font(28, bold=True)
    font_stat_val  = load_font(20, bold=True)
    font_stat_lbl  = load_font(15)
    font_item_name = load_font(17, bold=True)
    font_item_val  = load_font(18, bold=True)
    font_item_lbl  = load_font(14)
    font_serial    = load_font(13)
    font_badge     = load_font(14, bold=True)

    # ── HEADER ────────────────────────────────────────────────────────────────
    # Barra de acento no topo
    draw.rectangle([0, 0, W, s(3)], fill=ORANGE_MAIN)

    # Painel do header (fundo levemente diferente)
    draw.rectangle([0, 0, W, s(HEADER_H)], fill=BG_PANEL)
    draw.line([(0, s(HEADER_H)), (W, s(HEADER_H))], fill=DIVIDER, width=s(1))

    # Avatar circular
    av_x, av_y = s(SIDE_PAD), s(18)
    av_size = s(62)
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av = av.resize((av_size, av_size), Image.LANCZOS)

            # Anel externo laranja
            ring_size = av_size + s(4)
            ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse([0, 0, ring_size - 1, ring_size - 1],
                                         fill=ORANGE_MAIN)
            img.paste(ring.convert("RGB"), (av_x - s(2), av_y - s(2)))

            mask = Image.new("L", (av_size, av_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, av_size, av_size], fill=255)
            img.paste(av, (av_x, av_y), mask)
        except Exception:
            pass

    # Nome
    name_x = av_x + av_size + s(16)
    name_y = s(20)
    draw.text((name_x, name_y), username, font=font_username, fill=TEXT_WHITE)

    # Stats em pills
    stats = [
        ("VALUE", fmt_number(total_value)),
        ("RAP",   fmt_number(total_rap)),
        ("ITEMS", str(item_count)),
    ]
    stat_y = name_y + s(32)
    sx = name_x
    for label, val in stats:
        lw = int(draw.textlength(label, font=font_stat_lbl))
        vw = int(draw.textlength(val,   font=font_stat_val))
        pill_w = lw + vw + s(20)
        pill_h = s(22)
        # Pill fundo
        draw.rounded_rectangle([sx, stat_y, sx + pill_w, stat_y + pill_h],
                               radius=s(5), fill=BG_CARD)
        # Label
        draw.text((sx + s(8), stat_y + s(4)), label, font=font_stat_lbl, fill=TEXT_MUTED)
        # Value
        draw.text((sx + s(10) + lw, stat_y + s(3)), val, font=font_stat_val, fill=ORANGE_LIGHT)
        sx += pill_w + s(8)

    # ── GRID DE ITENS ─────────────────────────────────────────────────────────
    total_grid_w = COLS * CARD_W + (COLS - 1) * CARD_PAD
    gx_start = (IMG_WIDTH - total_grid_w) // 2

    for idx, item in enumerate(items):
        col = idx % COLS
        row = idx // COLS

        # Coordenadas base (1x) → escalar
        bx0 = gx_start + col * (CARD_W + CARD_PAD)
        by0 = HEADER_H + CARD_PAD + row * (CARD_H + CARD_PAD)
        bx1 = bx0 + CARD_W
        by1 = by0 + CARD_H

        x0, y0 = s(bx0), s(by0)
        x1, y1 = s(bx1), s(by1)
        r_card = s(10)

        # Sombra suave
        draw_soft_shadow(img, (x0, y0, x1, y1), radius=r_card, alpha=70)

        # Card fundo
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r_card, fill=BG_CARD)

        # Faixa superior levemente mais clara
        draw.rounded_rectangle([x0, y0, x1, y0 + s(CARD_H // 2)],
                               radius=r_card, fill=BG_CARD_TOP)
        draw.rounded_rectangle([x0, y0 + s(CARD_H // 2) - r_card,
                                 x1, y0 + s(CARD_H // 2)],
                               radius=0, fill=BG_CARD_TOP)

        # Borda fina laranja muito sutil
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r_card,
                               outline=(*ORANGE_DIM,), width=s(1))

        # Linha separadora entre thumb e info
        sep_y = y0 + s(int(CARD_H * 0.62))
        draw.line([(x0 + s(10), sep_y), (x1 - s(10), sep_y)],
                  fill=DIVIDER, width=s(1))

        # Hold clock
        if item.get("on_hold"):
            draw_hold_clock(img, x0 + s(14), y0 + s(14), r=s(11))

        # Thumbnail
        asset_id    = item["assetId"]
        thumb_bytes = thumb_images.get(asset_id)
        th_size     = s(int(CARD_W * 0.78))
        thumb_cx    = x0 + (x1 - x0) // 2
        thumb_cy    = y0 + s(int(CARD_H * 0.31))

        if thumb_bytes:
            try:
                th = Image.open(io.BytesIO(thumb_bytes)).convert("RGBA")
                th = th.resize((th_size, th_size), Image.LANCZOS)
                paste_centered(img, th, thumb_cx, thumb_cy)
            except Exception:
                pass
        else:
            ph = th_size
            px0 = thumb_cx - ph // 2
            py0 = thumb_cy - ph // 2
            draw.rounded_rectangle([px0, py0, px0 + ph, py0 + ph],
                                   radius=s(6), fill=(32, 26, 18))
            draw.text((px0 + ph // 2 - s(8), py0 + ph // 2 - s(10)),
                      "?", font=load_font(20), fill=TEXT_MUTED)

        # Nome do item
        name   = item.get("name", "Unknown")
        name_y2 = sep_y + s(8)
        words  = name.split()
        lines  = []
        cur    = ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw.textlength(test, font=font_item_name) <= s(CARD_W - 14):
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        lines = lines[:2]

        line_h = s(15)
        for i, line in enumerate(lines):
            tw = int(draw.textlength(line, font=font_item_name))
            draw.text((x0 + ((x1 - x0) - tw) // 2, name_y2 + i * line_h),
                      line, font=font_item_name, fill=TEXT_WHITE)

        # RAP + Value
        rap   = item.get("rap")
        value = item.get("value")
        serial = item.get("serial")

        info_y = y1 - s(46)

        # RAP: label + valor na mesma linha
        rap_lbl = "RAP"
        rap_val = fmt_number(rap) if rap else "—"
        lw = int(draw.textlength(rap_lbl, font=font_item_lbl))
        vw = int(draw.textlength(rap_val, font=font_item_val))
        total_w = lw + s(8) + vw
        rx = x0 + ((x1 - x0) - total_w) // 2
        draw.text((rx, info_y), rap_lbl, font=font_item_lbl, fill=TEXT_MUTED)
        draw.text((rx + lw + s(8), info_y - s(2)), rap_val, font=font_item_val, fill=TEXT_MUTED)

        # Value
        val_str   = fmt_number(value) if value else "—"
        val_color = TEXT_GREEN if value and value > (rap or 0) else ORANGE_LIGHT
        vw2 = int(draw.textlength(val_str, font=font_item_val))
        draw.text((x0 + ((x1 - x0) - vw2) // 2, info_y + s(20)),
                  val_str, font=font_item_val, fill=val_color)

        # Serial
        if serial:
            sstr = f"#{serial}"
            sw = int(draw.textlength(sstr, font=font_serial))
            draw.text((x0 + ((x1 - x0) - sw) // 2, info_y + s(38)),
                      sstr, font=font_serial, fill=SERIAL_COLOR)

        # Badge quantidade
        quantity = item.get("quantity", 1)
        if quantity > 1:
            draw_quantity_badge(draw, x1, y1, quantity, font_badge)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    draw.rectangle([0, H - s(FOOTER_H), W, H], fill=ORANGE_MAIN)

    # ── DOWNSCALE 2x → 1x (antialiasing) ─────────────────────────────────────
    out_img = img.resize((IMG_WIDTH, img_height), Image.LANCZOS)

    out = io.BytesIO()
    out_img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out.read()
