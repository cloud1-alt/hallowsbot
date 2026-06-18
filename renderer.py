"""
renderer.py — Gera a imagem do inventário estilo Rolimons
com tema visual inspirado no Hallows (laranja + preto).
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io
import math
import os

# ─── Paleta Hallows ────────────────────────────────────────────────────────────
BG_DARK       = (15, 12, 8)          # fundo quase preto
BG_CARD       = (28, 22, 14)         # card de item
BG_CARD_HOVER = (40, 30, 15)         # borda accent laranja escuro
ORANGE_MAIN   = (255, 106, 0)        # laranja principal
ORANGE_LIGHT  = (255, 165, 60)       # laranja claro
ORANGE_GLOW   = (255, 90, 0, 60)     # glow sutil
TEXT_WHITE    = (240, 235, 225)      # texto principal
TEXT_MUTED    = (160, 145, 120)      # texto secundário
TEXT_GREEN    = (80, 220, 120)       # valor positivo
TEXT_GOLD     = (255, 210, 60)       # valor em gold
DIVIDER       = (50, 38, 22)         # separador
SERIAL_COLOR  = (255, 186, 60)       # cor do serial (#xxx)

# ─── Layout ────────────────────────────────────────────────────────────────────
IMG_WIDTH     = 980
COLS          = 6
CARD_W        = 140
CARD_H        = 195
CARD_PAD      = 10
HEADER_H      = 90
SIDE_PAD      = 20

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


def draw_rounded_rect(draw: ImageDraw.Draw, xy, radius: int, fill, outline=None, outline_width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill,
                           outline=outline, width=outline_width)


def paste_centered(base: Image.Image, overlay: Image.Image, cx: int, cy: int):
    x = cx - overlay.width // 2
    y = cy - overlay.height // 2
    if overlay.mode == "RGBA":
        base.paste(overlay, (x, y), overlay)
    else:
        base.paste(overlay, (x, y))


def draw_glow_rect(img: Image.Image, xy, color_rgba, radius=8):
    """Adiciona um glow sutil em volta de um retângulo."""
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    x0, y0, x1, y1 = xy
    for expand in range(6, 0, -1):
        alpha = int(color_rgba[3] * (expand / 6))
        gd.rounded_rectangle(
            [x0 - expand, y0 - expand, x1 + expand, y1 + expand],
            radius=radius + expand,
            fill=(*color_rgba[:3], alpha),
        )
    img.paste(glow_layer, mask=glow_layer)


def make_hallows_bg_pattern(width: int, height: int) -> Image.Image:
    """Fundo com tiles do Hallows repetidos em grade alinhada, semi-transparentes."""
    bg = Image.new("RGBA", (width, height), BG_DARK + (255,))

    # Tentar carregar a imagem do Hallows
    hallows_path = os.path.join(os.path.dirname(__file__), "hallows.png")
    if os.path.exists(hallows_path):
        tile_src = Image.open(hallows_path).convert("RGBA")

        # Tamanho do tile no grid
        tile_size = 90

        # Redimensionar mantendo qualidade
        tile = tile_src.resize((tile_size, tile_size), Image.LANCZOS)

        # Aplicar opacidade baixa para ficar sutil no fundo (20%)
        r, g, b, a = tile.split()
        a = a.point(lambda x: int(x * 0.18))
        tile.putalpha(a)

        # Tile em grade alinhada com pequeno gap
        gap = 14
        step = tile_size + gap

        for row_y in range(0, height + step, step):
            for col_x in range(0, width + step, step):
                bg.paste(tile, (col_x, row_y), tile)

    # Overlay escuro suave sobre os tiles para não competir com os cards
    overlay = Image.new("RGBA", (width, height), (*BG_DARK, 120))
    bg = Image.alpha_composite(bg, overlay)

    # Linha decorativa no topo
    draw = ImageDraw.Draw(bg)
    for i in range(3):
        alpha = 120 - i * 35
        draw.line([(0, i), (width, i)], fill=(*ORANGE_MAIN, alpha), width=1)

    return bg


# ─── Renderer principal ────────────────────────────────────────────────────────

def render_inventory_image(
    username: str,
    user_id: int,
    total_value: int,
    total_rap: int,
    item_count: int,
    items: list[dict],
    thumb_images: dict[int, bytes],  # assetId -> bytes PNG
    avatar_bytes: bytes | None,
) -> bytes:

    rows = math.ceil(len(items) / COLS)
    grid_h = rows * (CARD_H + CARD_PAD) + CARD_PAD
    img_height = HEADER_H + grid_h + 24

    # Base
    bg = make_hallows_bg_pattern(IMG_WIDTH, img_height)
    img = bg.convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── HEADER ────────────────────────────────────────────────────────────────

    # Barra laranja no topo
    draw.rectangle([0, 0, IMG_WIDTH, 3], fill=ORANGE_MAIN)

    # Avatar
    avatar_x, avatar_y = SIDE_PAD, 14
    avatar_size = 54
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = av_img.resize((avatar_size, avatar_size), Image.LANCZOS)
            # Máscara circular
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)
            # Borda laranja
            border_img = Image.new("RGBA", (avatar_size + 4, avatar_size + 4), (0, 0, 0, 0))
            ImageDraw.Draw(border_img).ellipse(
                [0, 0, avatar_size + 3, avatar_size + 3], fill=ORANGE_MAIN
            )
            img.paste(border_img.convert("RGB"), (avatar_x - 2, avatar_y - 2))
            img.paste(av_img, (avatar_x, avatar_y), mask)
        except Exception:
            pass

    # Nome do usuário
    font_name   = load_font(22, bold=True)
    font_stats  = load_font(13)
    font_label  = load_font(11)

    name_x = avatar_x + avatar_size + 14
    draw.text((name_x, avatar_y + 2), username, font=font_name, fill=TEXT_WHITE)

    # Linha de stats
    stats_y = avatar_y + 30
    stats = [
        ("Value", fmt_number(total_value)),
        ("RAP", fmt_number(total_rap)),
        ("Items", str(item_count)),
    ]
    sx = name_x
    for label, val in stats:
        draw.text((sx, stats_y), label, font=font_label, fill=TEXT_MUTED)
        tw = draw.textlength(label, font=font_label)
        draw.text((sx + tw + 4, stats_y), val, font=font_stats, fill=ORANGE_LIGHT)
        sw = draw.textlength(val, font=font_stats)
        sx += int(tw + sw + 24)

    # Separador
    sep_y = HEADER_H - 8
    draw.line([(SIDE_PAD, sep_y), (IMG_WIDTH - SIDE_PAD, sep_y)], fill=DIVIDER, width=1)
    # Dot accent no centro do separador
    mid = IMG_WIDTH // 2
    draw.ellipse([mid - 3, sep_y - 3, mid + 3, sep_y + 3], fill=ORANGE_MAIN)

    # ── GRID DE ITENS ─────────────────────────────────────────────────────────

    font_item_name = load_font(11, bold=True)
    font_item_val  = load_font(11)
    font_serial    = load_font(10)

    total_grid_w = COLS * CARD_W + (COLS - 1) * CARD_PAD
    grid_x_start = (IMG_WIDTH - total_grid_w) // 2

    for idx, item in enumerate(items):
        col = idx % COLS
        row = idx // COLS

        x0 = grid_x_start + col * (CARD_W + CARD_PAD)
        y0 = HEADER_H + CARD_PAD + row * (CARD_H + CARD_PAD)
        x1 = x0 + CARD_W
        y1 = y0 + CARD_H

        # Glow sutil na borda
        draw_glow_rect(img, (x0, y0, x1, y1), ORANGE_GLOW, radius=8)

        # Card background
        draw_rounded_rect(draw, (x0, y0, x1, y1), radius=8,
                         fill=BG_CARD, outline=(*ORANGE_MAIN[:3],), outline_width=1)

        # Thumbnail
        asset_id = item["assetId"]
        thumb_bytes = thumb_images.get(asset_id)
        thumb_y = y0 + 8
        if thumb_bytes:
            try:
                th = Image.open(io.BytesIO(thumb_bytes)).convert("RGBA")
                th = th.resize((110, 110), Image.LANCZOS)
                thumb_cx = x0 + CARD_W // 2
                paste_centered(img, th, thumb_cx, thumb_y + 55)
            except Exception:
                pass
        else:
            # Placeholder
            ph_x = x0 + 15
            ph_y = thumb_y + 5
            draw.rounded_rectangle([ph_x, ph_y, ph_x + 110, ph_y + 110],
                                   radius=6, fill=(35, 28, 18))
            draw.text((ph_x + 35, ph_y + 40), "?", font=load_font(30), fill=TEXT_MUTED)

        # Nome do item (2 linhas max)
        name = item.get("name", "Unknown")
        name_y = y0 + 126
        # Quebra nome longo
        words = name.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            if draw.textlength(test, font=font_item_name) <= CARD_W - 8:
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
            draw.text((x0 + (CARD_W - tw) // 2, name_y + i * 14),
                      line, font=font_item_name, fill=TEXT_WHITE)

        # RAP
        rap = item.get("rap")
        value = item.get("value")
        serial = item.get("serial")

        info_y = y0 + CARD_H - 44

        # Linha RAP
        rap_str = f"RAP  {fmt_number(rap)}" if rap else "RAP  -"
        tw = draw.textlength(rap_str, font=font_item_val)
        draw.text((x0 + (CARD_W - tw) // 2, info_y), rap_str, font=font_item_val, fill=TEXT_MUTED)

        # Linha Value
        val_str = fmt_number(value) if value else "-"
        tw = draw.textlength(val_str, font=font_item_val)
        val_color = TEXT_GREEN if value and value > (rap or 0) else ORANGE_LIGHT
        draw.text((x0 + (CARD_W - tw) // 2, info_y + 15),
                  val_str, font=font_item_val, fill=val_color)

        # Serial
        if serial:
            serial_str = f"#{serial}"
            tw = draw.textlength(serial_str, font=font_serial)
            draw.text((x0 + (CARD_W - tw) // 2, info_y + 30),
                      serial_str, font=font_serial, fill=SERIAL_COLOR)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    draw.rectangle([0, img_height - 4, IMG_WIDTH, img_height], fill=ORANGE_MAIN)

    # Salvar
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out.read()
