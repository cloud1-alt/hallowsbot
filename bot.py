"""
renderer.py — Gera a imagem do inventário estilo Rolimons
com tema visual inspirado no Hallows (laranja + preto).
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
import math
import os

# ─── Paleta Hallows ────────────────────────────────────────────────────────────
BG_DARK       = (15, 12, 8)
BG_CARD       = (28, 22, 14)
ORANGE_MAIN   = (255, 106, 0)
ORANGE_LIGHT  = (255, 165, 60)
ORANGE_GLOW   = (255, 90, 0, 55)
TEXT_WHITE    = (240, 235, 225)
TEXT_MUTED    = (160, 145, 120)
TEXT_GREEN    = (80, 220, 120)
DIVIDER       = (50, 38, 22)
SERIAL_COLOR  = (255, 186, 60)

# ─── Layout ────────────────────────────────────────────────────────────────────
IMG_WIDTH     = 980
COLS          = 6
CARD_W        = 148
CARD_H        = 210
CARD_PAD      = 10
HEADER_H      = 96
SIDE_PAD      = 20
THUMB_SIZE    = 120   # tamanho do thumbnail dentro do card
AVATAR_SIZE   = 64    # tamanho do avatar no header

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
        return "-"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))


def paste_rgba(base: Image.Image, overlay: Image.Image, x: int, y: int):
    """Cola imagem RGBA sobre base RGB respeitando transparência corretamente."""
    if base.mode != "RGBA":
        base_rgba = base.convert("RGBA")
    else:
        base_rgba = base
    if overlay.mode != "RGBA":
        overlay = overlay.convert("RGBA")
    base_rgba.paste(overlay, (x, y), overlay)
    # Converter de volta para RGB preservando o resultado
    result = base_rgba.convert("RGB")
    base.paste(result)


def make_circle_avatar(img_bytes: bytes, size: int) -> Image.Image:
    """Cria avatar circular a partir de bytes, com alta qualidade."""
    # Abre e redimensiona em tamanho 4x para depois reduzir (antialiasing manual)
    scale = 4
    big = size * scale
    av = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    av = av.resize((big, big), Image.LANCZOS)

    # Máscara circular suave
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)

    result = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    result.paste(av, mask=mask)

    # Reduzir para tamanho final com LANCZOS
    result = result.resize((size, size), Image.LANCZOS)
    return result


def draw_glow_rect(img: Image.Image, xy, color_rgba, radius=8):
    """Glow laranja sutil em volta dos cards."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x0, y0, x1, y1 = xy
    for expand in range(7, 0, -1):
        alpha = int(color_rgba[3] * (expand / 7) * 0.9)
        gd.rounded_rectangle(
            [x0 - expand, y0 - expand, x1 + expand, y1 + expand],
            radius=radius + expand,
            fill=(*color_rgba[:3], alpha),
        )
    base_rgba = img.convert("RGBA")
    base_rgba = Image.alpha_composite(base_rgba, glow)
    img.paste(base_rgba.convert("RGB"))


def make_hallows_bg_pattern(width: int, height: int) -> Image.Image:
    """Fundo com tiles do Hallows em grade alinhada."""
    bg = Image.new("RGBA", (width, height), BG_DARK + (255,))

    hallows_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hallows.png")
    if os.path.exists(hallows_path):
        tile_src = Image.open(hallows_path).convert("RGBA")
        tile_size = 92
        tile = tile_src.resize((tile_size, tile_size), Image.LANCZOS)

        # Opacidade 16%
        r, g, b, a = tile.split()
        a = a.point(lambda x: int(x * 0.16))
        tile.putalpha(a)

        gap = 16
        step = tile_size + gap
        for row_y in range(0, height + step, step):
            for col_x in range(0, width + step, step):
                bg.paste(tile, (col_x, row_y), tile)

    # Overlay escuro para não competir com os cards
    overlay = Image.new("RGBA", (width, height), (*BG_DARK, 110))
    bg = Image.alpha_composite(bg, overlay)
    return bg


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
    img_height = HEADER_H + grid_h + 28

    # ── Base ──────────────────────────────────────────────────────────────────
    bg = make_hallows_bg_pattern(IMG_WIDTH, img_height)
    img = bg.convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── HEADER ────────────────────────────────────────────────────────────────

    # Barra laranja no topo
    draw.rectangle([0, 0, IMG_WIDTH, 4], fill=ORANGE_MAIN)

    # Avatar circular de alta qualidade
    av_x, av_y = SIDE_PAD, 16
    if avatar_bytes:
        try:
            av_circle = make_circle_avatar(avatar_bytes, AVATAR_SIZE)
            # Borda laranja: desenha círculo laranja ligeiramente maior antes
            border_size = AVATAR_SIZE + 6
            border_circle = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
            ImageDraw.Draw(border_circle).ellipse(
                [0, 0, border_size - 1, border_size - 1], fill=ORANGE_MAIN
            )
            paste_rgba(img, border_circle, av_x - 3, av_y - 3)
            paste_rgba(img, av_circle, av_x, av_y)
        except Exception:
            pass

    # Fontes do header
    font_name  = load_font(24, bold=True)
    font_stats = load_font(14)
    font_label = load_font(12)

    name_x = av_x + AVATAR_SIZE + 16
    name_y = av_y + 4
    draw.text((name_x, name_y), username, font=font_name, fill=TEXT_WHITE)

    # Stats em linha
    stats_y = name_y + 32
    stats = [
        ("Value", fmt_number(total_value)),
        ("RAP",   fmt_number(total_rap)),
        ("Items", str(item_count)),
    ]
    sx = name_x
    for label, val in stats:
        lw = draw.textlength(label, font=font_label)
        draw.text((sx, stats_y), label, font=font_label, fill=TEXT_MUTED)
        draw.text((sx + lw + 5, stats_y), val, font=font_stats, fill=ORANGE_LIGHT)
        vw = draw.textlength(val, font=font_stats)
        sx += int(lw + vw + 26)

    # Separador com ponto laranja central
    sep_y = HEADER_H - 10
    draw.line([(SIDE_PAD, sep_y), (IMG_WIDTH - SIDE_PAD, sep_y)], fill=DIVIDER, width=1)
    mid = IMG_WIDTH // 2
    draw.ellipse([mid - 4, sep_y - 4, mid + 4, sep_y + 4], fill=ORANGE_MAIN)

    # ── GRID DE ITENS ─────────────────────────────────────────────────────────

    font_item_name = load_font(12, bold=True)
    font_item_val  = load_font(12)
    font_serial    = load_font(11)

    total_grid_w = COLS * CARD_W + (COLS - 1) * CARD_PAD
    grid_x_start = (IMG_WIDTH - total_grid_w) // 2

    for idx, item in enumerate(items):
        col = idx % COLS
        row = idx // COLS

        x0 = grid_x_start + col * (CARD_W + CARD_PAD)
        y0 = HEADER_H + CARD_PAD + row * (CARD_H + CARD_PAD)
        x1 = x0 + CARD_W
        y1 = y0 + CARD_H

        # Glow laranja
        draw_glow_rect(img, (x0, y0, x1, y1), ORANGE_GLOW, radius=9)

        # Redesenhar o draw depois do glow (ele reconverte o img)
        draw = ImageDraw.Draw(img)

        # Card background + borda
        draw.rounded_rectangle(
            [x0, y0, x1, y1], radius=9,
            fill=BG_CARD, outline=ORANGE_MAIN, width=1
        )

        # ── Thumbnail ─────────────────────────────────────────────────────────
        asset_id   = item["assetId"]
        thumb_data = thumb_images.get(asset_id)
        thumb_cx   = x0 + CARD_W // 2
        thumb_cy   = y0 + 8 + THUMB_SIZE // 2

        if thumb_data:
            try:
                th = Image.open(io.BytesIO(thumb_data)).convert("RGBA")
                th = th.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
                paste_rgba(img, th, thumb_cx - THUMB_SIZE // 2, thumb_cy - THUMB_SIZE // 2)
                draw = ImageDraw.Draw(img)
            except Exception:
                pass
        else:
            # Placeholder quando não há thumb
            ph_x = x0 + (CARD_W - THUMB_SIZE) // 2
            ph_y = y0 + 8
            draw.rounded_rectangle(
                [ph_x, ph_y, ph_x + THUMB_SIZE, ph_y + THUMB_SIZE],
                radius=6, fill=(35, 28, 18)
            )
            qm = load_font(34)
            draw.text((ph_x + THUMB_SIZE // 2 - 9, ph_y + THUMB_SIZE // 2 - 18),
                      "?", font=qm, fill=TEXT_MUTED)

        # ── Nome do item ──────────────────────────────────────────────────────
        name   = item.get("name", "Unknown")
        name_y = y0 + 8 + THUMB_SIZE + 6

        words   = name.split()
        lines   = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            if draw.textlength(test, font=font_item_name) <= CARD_W - 10:
                current = test
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        lines = lines[:2]

        for i, line in enumerate(lines):
            tw = draw.textlength(line, font=font_item_name)
            draw.text(
                (x0 + (CARD_W - tw) // 2, name_y + i * 15),
                line, font=font_item_name, fill=TEXT_WHITE
            )

        # ── RAP / Value / Serial ──────────────────────────────────────────────
        rap    = item.get("rap")
        value  = item.get("value")
        serial = item.get("serial")

        info_y = y1 - 46

        # RAP
        rap_str = f"RAP  {fmt_number(rap)}"
        tw = draw.textlength(rap_str, font=font_item_val)
        draw.text((x0 + (CARD_W - tw) // 2, info_y), rap_str,
                  font=font_item_val, fill=TEXT_MUTED)

        # Value
        val_str   = fmt_number(value)
        val_color = TEXT_GREEN if value and value > (rap or 0) else ORANGE_LIGHT
        tw = draw.textlength(val_str, font=font_item_val)
        draw.text((x0 + (CARD_W - tw) // 2, info_y + 16), val_str,
                  font=font_item_val, fill=val_color)

        # Serial
        if serial:
            s_str = f"#{serial}"
            tw = draw.textlength(s_str, font=font_serial)
            draw.text((x0 + (CARD_W - tw) // 2, info_y + 31), s_str,
                      font=font_serial, fill=SERIAL_COLOR)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    draw.rectangle([0, img_height - 4, IMG_WIDTH, img_height], fill=ORANGE_MAIN)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out.read()
