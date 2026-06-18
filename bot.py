import discord
from discord import app_commands
import aiohttp
import asyncio
import io
import os
from dotenv import load_dotenv
from renderer import render_inventory_image

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ROLI_SECURITY = os.getenv("ROLI_SECURITY")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

HEADERS_ROBLOX = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

HEADERS_ROLIMONS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cookie": f"rolimons_security={ROLI_SECURITY}",
    "Referer": "https://www.rolimons.com/",
}

# ─── Roblox helpers ────────────────────────────────────────────────────────────

async def resolve_user(session: aiohttp.ClientSession, identifier: str) -> dict | None:
    """Accepts numeric ID or username. Returns {"id": int, "name": str} or None."""
    if identifier.isdigit():
        async with session.get(
            f"https://users.roblox.com/v1/users/{identifier}",
            headers=HEADERS_ROBLOX,
        ) as r:
            if r.status == 200:
                data = await r.json()
                return {"id": data["id"], "name": data["name"]}
    else:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [identifier], "excludeBannedUsers": False},
            headers=HEADERS_ROBLOX,
        ) as r:
            if r.status == 200:
                data = await r.json()
                results = data.get("data", [])
                if results:
                    return {"id": results[0]["id"], "name": results[0]["name"]}
    return None


async def get_collectibles(session: aiohttp.ClientSession, user_id: int) -> list[dict]:
    """Retorna todos os limiteds do inventário (API pública do Roblox)."""
    items = []
    cursor = ""
    while True:
        url = (
            f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles"
            f"?limit=100&sortOrder=Desc"
        )
        if cursor:
            url += f"&cursor={cursor}"
        async with session.get(url, headers=HEADERS_ROBLOX) as r:
            if r.status != 200:
                break
            data = await r.json()
            items.extend(data.get("data", []))
            cursor = data.get("nextPageCursor") or ""
            if not cursor:
                break
    return items


async def get_thumbnail_url(session: aiohttp.ClientSession, asset_id: int) -> str | None:
    url = (
        f"https://thumbnails.roblox.com/v1/assets"
        f"?assetIds={asset_id}&size=150x150&format=Png&isCircular=false"
    )
    async with session.get(url, headers=HEADERS_ROBLOX) as r:
        if r.status == 200:
            data = await r.json()
            d = data.get("data", [])
            if d and d[0].get("state") == "Completed":
                return d[0]["imageUrl"]
    return None


async def get_thumbnails_batch(session: aiohttp.ClientSession, asset_ids: list[int]) -> dict[int, str]:
    """Busca thumbnails em lotes de 100."""
    result = {}
    for i in range(0, len(asset_ids), 100):
        batch = asset_ids[i : i + 100]
        ids_str = ",".join(str(a) for a in batch)
        url = (
            f"https://thumbnails.roblox.com/v1/assets"
            f"?assetIds={ids_str}&size=420x420&format=Png&isCircular=false"
        )
        async with session.get(url, headers=HEADERS_ROBLOX) as r:
            if r.status == 200:
                data = await r.json()
                for item in data.get("data", []):
                    if item.get("state") == "Completed":
                        result[item["targetId"]] = item["imageUrl"]
    return result


async def get_user_avatar_url(session: aiohttp.ClientSession, user_id: int) -> str | None:
    url = (
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
        f"?userIds={user_id}&size=420x420&format=Png"
    )
    async with session.get(url, headers=HEADERS_ROBLOX) as r:
        if r.status == 200:
            data = await r.json()
            d = data.get("data", [])
            if d and d[0].get("state") == "Completed":
                return d[0]["imageUrl"]
    return None


# ─── Rolimons helpers ──────────────────────────────────────────────────────────

async def get_rolimons_player(session: aiohttp.ClientSession, user_id: int) -> dict | None:
    async with session.get(
        f"https://www.rolimons.com/playerapi/player/{user_id}",
        headers=HEADERS_ROLIMONS,
    ) as r:
        if r.status == 200:
            return await r.json()
    return None


async def get_rolimons_items(session: aiohttp.ClientSession) -> dict:
    """Retorna mapa {assetId: [name, acronym, value, demand, trend, projected, hyped, rare, ...]}"""
    async with session.get(
        "https://www.rolimons.com/itemapi/itemdetails",
        headers=HEADERS_ROLIMONS,
    ) as r:
        if r.status == 200:
            data = await r.json()
            return data.get("items", {})
    return {}


async def download_image(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status == 200:
                return await r.read()
    except Exception:
        pass
    return None


# ─── Slash command ─────────────────────────────────────────────────────────────

@tree.command(
    name="inventory",
    description="Mostra o inventário de limiteds de um player do Roblox",
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(player="ID numérico ou username do Roblox")
async def inventory(interaction: discord.Interaction, player: str):
    await interaction.response.defer(thinking=True)

    async with aiohttp.ClientSession() as session:
        # 1. Resolver usuário
        user = await resolve_user(session, player)
        if not user:
            await interaction.followup.send(
                f"❌ Não encontrei o usuário **{player}**. Verifique o ID ou username.",
                ephemeral=True,
            )
            return

        user_id = user["id"]
        username = user["name"]

        # 2. Buscar dados Rolimons (valor, RAP, etc.)
        roli_data = await get_rolimons_player(session, user_id)
        roli_items_db = await get_rolimons_items(session)

        # 3. Montar collectibles
        # itemdetails: [Name, Acronym, RAP, Value, DefaultValue, Demand, Trend, ...]
        # player_assets: [serial, rap, value, ...] — índices próprios
        # Sempre buscar name/value da roli_items_db (mais confiável)
        collectibles = []
        if roli_data and roli_data.get("player_assets"):
            for asset_id_str, vals in roli_data["player_assets"].items():
                item_info = roli_items_db.get(asset_id_str, [])
                # item_info: [Name, Acronym, RAP, Value, DefaultValue, ...]
                name  = item_info[0] if len(item_info) > 0 else f"Item #{asset_id_str}"
                # RAP e Value vêm da itemdetails (índices 2 e 3)
                rap   = item_info[2] if len(item_info) > 2 else -1
                value = item_info[3] if len(item_info) > 3 else -1
                # Serial vem do player_assets índice 0
                serial = vals[0] if len(vals) > 0 and vals[0] and vals[0] > 0 else None
                collectibles.append({
                    "assetId": int(asset_id_str),
                    "name":    name,
                    "rap":     rap   if rap   > 0 else None,
                    "value":   value if value > 0 else None,
                    "serial":  serial,
                })
        else:
            raw = await get_collectibles(session, user_id)
            for item in raw:
                asset_id_str = str(item.get("assetId", ""))
                item_info    = roli_items_db.get(asset_id_str, [])
                rap_raw   = item_info[2] if len(item_info) > 2 else -1
                value_raw = item_info[3] if len(item_info) > 3 else -1
                collectibles.append({
                    "assetId": item["assetId"],
                    "name":    item_info[0] if len(item_info) > 0 else item.get("name", "Unknown"),
                    "rap":     rap_raw   if rap_raw   > 0 else None,
                    "value":   value_raw if value_raw > 0 else None,
                    "serial":  item.get("serialNumber"),
                })

        if not collectibles:
            await interaction.followup.send(
                f"📦 **{username}** não tem limiteds visíveis no inventário.",
            )
            return

        # 4. Calcular totais
        # Value usa RAP como fallback quando o item não tem value definido no Rolimons
        total_rap   = sum(c["rap"]   or 0 for c in collectibles)
        total_value = sum(c["value"] or c["rap"] or 0 for c in collectibles)
        item_count = len(collectibles)

        # Mostrar apenas os primeiros 18 itens na imagem (layout fixo)
        display_items = collectibles[:18]

        # 5. Thumbnails em batch
        asset_ids = [c["assetId"] for c in display_items]
        thumbs = await get_thumbnails_batch(session, asset_ids)

        # 6. Download das imagens
        thumb_images: dict[int, bytes] = {}
        tasks = {
            aid: download_image(session, url)
            for aid, url in thumbs.items()
        }
        results = await asyncio.gather(*tasks.values())
        for aid, img_bytes in zip(tasks.keys(), results):
            if img_bytes:
                thumb_images[aid] = img_bytes

        # 7. Avatar do usuário
        avatar_url = await get_user_avatar_url(session, user_id)
        avatar_bytes = None
        if avatar_url:
            avatar_bytes = await download_image(session, avatar_url)

        # 8. Renderizar imagem
        img_bytes = await asyncio.get_event_loop().run_in_executor(
            None,
            render_inventory_image,
            username,
            user_id,
            total_value,
            total_rap,
            item_count,
            display_items,
            thumb_images,
            avatar_bytes,
        )

        file = discord.File(io.BytesIO(img_bytes), filename="inventory.png")
        embed = discord.Embed(
            title=f"",
            color=0xFF6A00,
        )
        embed.set_image(url="attachment://inventory.png")

        more_text = f" *(+{item_count - 18} itens não exibidos)*" if item_count > 18 else ""
        embed.set_footer(text=f"Mostrando {min(18, item_count)} de {item_count} itens{more_text} • Powered by Rolimons")

        await interaction.followup.send(embed=embed, file=file)


# ─── Eventos ───────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot conectado como {client.user}")
    print(f"📡 Slash commands sincronizados: {[c.name for c in tree.get_commands()]}")


client.run(TOKEN)
