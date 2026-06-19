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

async def resolve_user(session, identifier):
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


async def get_collectibles(session, user_id):
    """
    Retorna todos os limiteds do inventário via API pública do Roblox.
    Cada item inclui: assetId, serialNumber, recentAveragePrice, isOnHold, name, etc.
    """
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


async def get_thumbnails_batch(session, asset_ids):
    """Busca thumbnails via API do Roblox. Para os que falharem, usa Rolimons como fallback."""
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

    # Fallback: itens sem thumb puxam direto do Rolimons
    missing = [aid for aid in asset_ids if aid not in result]
    for aid in missing:
        result[aid] = f"https://www.rolimons.com/images/items/{aid}_full.png"

    return result


async def get_user_avatar_url(session, user_id):
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

async def get_rolimons_player(session, user_id):
    async with session.get(
        f"https://www.rolimons.com/playerapi/player/{user_id}",
        headers=HEADERS_ROLIMONS,
    ) as r:
        if r.status == 200:
            return await r.json()
    return None


async def get_rolimons_items(session):
    """
    itemdetails: { assetId: [Name(0), Acronym(1), RAP(2), Value(3), DefaultValue(4), ...] }
    Value == -1 significa sem value definido no Rolimons.
    """
    urls = [
        ("https://api.rolimons.com/items/v2/itemdetails", HEADERS_ROBLOX),
        ("https://www.rolimons.com/itemapi/itemdetails",  HEADERS_ROLIMONS),
    ]
    for url, headers in urls:
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                print(f"[itemdetails] {url} → {r.status}")
                if r.status == 200:
                    data = await r.json(content_type=None)
                    items = data.get("items", {})
                    if items:
                        print(f"[itemdetails] OK — {len(items)} itens carregados")
                        return items
        except Exception as e:
            print(f"[itemdetails] erro em {url}: {e}")
    print("[itemdetails] FALHOU em todos os endpoints")
    return {}


async def download_image(session, url):
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

        user_id  = user["id"]
        username = user["name"]

        # 2. Buscar tudo em paralelo
        roli_data, roli_items_db, raw_collectibles = await asyncio.gather(
            get_rolimons_player(session, user_id),
            get_rolimons_items(session),
            get_collectibles(session, user_id),
        )

        # 3. Montar mapa assetId -> isOnHold direto da API do Roblox
        # O campo "isOnHold" é nativo e confiável — true = item em hold
        hold_map = {
            item["assetId"]: item.get("isOnHold", False)
            for item in raw_collectibles
        }

        # 4. Montar collectibles
        # itemdetails: [Name(0), Acronym(1), RAP(2), Value(3), DefaultValue(4), ...]
        ITEMDB_VALUE_IDX = 3

        collectibles = []
        if roli_data and roli_data.get("player_assets"):
            # player_assets: { assetId: [serial(0), rap(1)] }
            for asset_id_str, vals in roli_data["player_assets"].items():
                item_info = roli_items_db.get(asset_id_str, [])
                asset_id  = int(asset_id_str)

                name  = item_info[0] if len(item_info) > 0 else f"Item #{asset_id_str}"
                rap   = vals[1]      if len(vals) > 1       else -1
                value = item_info[ITEMDB_VALUE_IDX] if len(item_info) > ITEMDB_VALUE_IDX else -1
                serial = vals[0] if len(vals) > 0 and vals[0] and vals[0] > 0 else None

                collectibles.append({
                    "assetId": asset_id,
                    "name":    name,
                    "rap":     rap   if rap   > 0 else None,
                    "value":   value if value > 0 else None,
                    "serial":  serial,
                    "on_hold": hold_map.get(asset_id, False),
                })
        else:
            # Fallback: monta direto dos collectibles do Roblox
            for item in raw_collectibles:
                asset_id_str = str(item.get("assetId", ""))
                item_info    = roli_items_db.get(asset_id_str, [])
                rap_raw   = item_info[2] if len(item_info) > 2 else -1
                value_raw = item_info[ITEMDB_VALUE_IDX] if len(item_info) > ITEMDB_VALUE_IDX else -1
                collectibles.append({
                    "assetId": item["assetId"],
                    "name":    item_info[0] if len(item_info) > 0 else item.get("name", "Unknown"),
                    "rap":     rap_raw   if rap_raw   > 0 else None,
                    "value":   value_raw if value_raw > 0 else None,
                    "serial":  item.get("serialNumber"),
                    "on_hold": item.get("isOnHold", False),
                })

        if not collectibles:
            await interaction.followup.send(
                f"📦 **{username}** não tem limiteds visíveis no inventário.",
            )
            return

        # 5. Ordenar do maior pro menor value (fallback: rap)
        collectibles.sort(
            key=lambda c: (c["value"] or c["rap"] or 0),
            reverse=True,
        )

        # 6. Calcular totais
        total_rap   = sum(c["rap"]   or 0 for c in collectibles)
        total_value = sum(c["value"] or c["rap"] or 0 for c in collectibles)
        item_count  = len(collectibles)

        # Mostrar apenas os primeiros 18 itens na imagem
        display_items = collectibles[:18]

        # 7. Thumbnails em batch
        asset_ids = [c["assetId"] for c in display_items]
        thumbs    = await get_thumbnails_batch(session, asset_ids)

        # 8. Download das imagens em paralelo
        thumb_images = {}
        tasks   = {aid: download_image(session, url) for aid, url in thumbs.items()}
        results = await asyncio.gather(*tasks.values())
        for aid, img_bytes in zip(tasks.keys(), results):
            if img_bytes:
                thumb_images[aid] = img_bytes

        # 9. Avatar
        avatar_url   = await get_user_avatar_url(session, user_id)
        avatar_bytes = None
        if avatar_url:
            avatar_bytes = await download_image(session, avatar_url)

        # 10. Renderizar imagem
        loop = asyncio.get_running_loop()
        img_bytes = await loop.run_in_executor(
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

        # 11. Mandar só a imagem pura (sem embed, sem footer)
        file = discord.File(io.BytesIO(img_bytes), filename="inventory.png")
        await interaction.followup.send(file=file)


# ─── Eventos ───────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot conectado como {client.user}")
    print(f"📡 Slash commands sincronizados: {[c.name for c in tree.get_commands()]}")


client.run(TOKEN)
