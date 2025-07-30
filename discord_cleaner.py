import discord
import os
import asyncio
import sqlite3
import logging
from discord.ext import tasks
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from log_utils import get_utc_timestamp, get_cleanup_threshold, log_cleanup_summary

# 環境変数読み込み
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
MODE = os.getenv("MODE", "live").lower()
LIVE_CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
TEST_CHANNEL_ID = int(os.getenv("TEST_CHANNEL_ID"))
CHANNEL_ID = TEST_CHANNEL_ID if MODE == "test" else LIVE_CHANNEL_ID
DELETE_DAYS = int(os.getenv("DELETE_DAYS", 7))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# ログ初期化
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.info(f"Bot起動モード: {MODE.upper()} | 対象チャンネルID: {CHANNEL_ID} | DRY_RUN: {DRY_RUN}")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
has_run = False

async def update_status(text):
    await client.change_presence(activity=discord.Game(name=f"{text} [{MODE.upper()}]"))

def save_history_to_db(timestamp, deleted, skipped_old, skipped_pinned, non_target, dry_run):
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        deleted INTEGER,
        skipped_too_old INTEGER,
        skipped_pinned INTEGER,
        non_target INTEGER,
        dry_run BOOLEAN
    )""")
    cursor.execute("INSERT INTO history VALUES (NULL,?,?,?,?,?,?)",
        (timestamp, deleted, skipped_old, skipped_pinned, dry_run, non_target))
    conn.commit()
    conn.close()

def is_too_old_for_discord(msg_created_at: datetime) -> bool:
    limit = datetime.now(timezone.utc) - timedelta(days=14)
    return msg_created_at < limit

async def cleanup_messages():
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        threshold = get_cleanup_threshold(DELETE_DAYS)

        deleted = skipped_old = skipped_pinned = total = 0
        async for msg in channel.history(limit=None, oldest_first=True):
            total += 1
            if msg.pinned:
                skipped_pinned += 1
                continue
            if is_too_old_for_discord(msg.created_at):
                skipped_old += 1
                continue

            if DRY_RUN:
                logging.info(f"削除候補: {msg.id} | {msg.created_at}")
            else:
                try:
                    await msg.delete()
                    deleted += 1
                    logging.info(f"削除済: {msg.id} | {msg.created_at}")
                except Exception as e:
                    logging.error(f"削除失敗: {e}")

        non_target = total - (deleted + skipped_old + skipped_pinned)
        timestamp = get_utc_timestamp()
        save_history_to_db(timestamp, deleted, skipped_old, skipped_pinned, non_target, DRY_RUN)
        log_cleanup_summary(deleted, skipped_old, skipped_pinned, non_target)

    except Exception as e:
        logging.critical(f"削除中にエラー: {e}")

async def update_research_reset_pin_manual(next_time, message) -> str:
    channel = await client.fetch_channel(CHANNEL_ID)
    unix_ts = int(next_time.timestamp())
    new_embed_desc = f"<t:{unix_ts}:F>（<t:{unix_ts}:R>）にリセットされます！\n<@&1384067593425522769> の皆さん、準備してね。"

    existing_time = None
    pinned_msg = None
    pins = await channel.pins()
    for pinned in pins:
        embed = pinned.embeds[0] if pinned.embeds else None
        if embed and embed.title == "🧪 次回の研究度リセット予定":
            desc = embed.description or ""
            m = re.search(r"<t:(\d+):F>", desc)
            if m:
                try:
                    existing_time = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
                    pinned_msg = pinned
                    if desc == new_embed_desc:
                        return "✅ 同じ予定がすでにピン留めされています。更新は不要です。"
                except Exception:
                    logging.warning("Embedから既存日時抽出失敗")
            break

    now = datetime.now(timezone.utc)
    if next_time < now:
        return "⏰ 過去の日時は登録できません。未来の予定を送ってください。"

    if existing_time and next_time <= existing_time:
        return f"📌 すでにそれより新しい予定（{existing_time.strftime('%Y-%m-%d %H:%M:%S')}）がピン留めされています。今回の更新は不要です。"

    if pinned_msg:
        try:
            async for msg in channel.history(limit=20):
                if msg.type == discord.MessageType.pins_add:
                    try:
                        await msg.delete()
                        logging.info(f"🔻 ピン通知削除成功: {msg.id}")
                    except Exception as e:
                        logging.warning(f"⚠️ ピン通知削除失敗: {msg.id} | {e}")
            await pinned_msg.unpin()
            await pinned_msg.delete()
            logging.info(f"✅ 古いピン削除成功: {existing_time}")
        except Exception as e:
            logging.warning(f"古いピン削除失敗: {e}")

    embed = Embed(
        title="🧪 次回の研究度リセット予定",
        description=new_embed_desc,
        color=0x6A5ACD
    )
    sent = await channel.send(embed=embed)
    await sent.pin()
    logging.info(f"📌 新しいピン留め完了: {next_time}")
    return "✅ 研究度リセット予定を更新しました！"

@client.event
async def on_message(message):
    if message.guild is None and message.author != client.user:
        content = message.content.strip()
        match = re.search(
            r"(研究度リセットだよ).*?(occurs next at|次回は)\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})",
            content
        )
        if match:
            date_str = match.group(3)
            try:
                next_time = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                response = await update_research_reset_pin_manual(next_time, message)
                await message.channel.send(response)
            except ValueError:
                await message.channel.send("⚠️ 日付の形式が不正です。\n例：`2025-07-29 03:00:00` のように送ってください。")
        else:
            await message.channel.send(
                "🤔 メッセージ形式が認識できません。\n`研究度リセットだよ ... occurs next at YYYY-MM-DD HH:MM:SS` のように送ってください。"
            )
@client.event
async def on_ready():
    global has_run
    logging.info(f"Botログイン成功: {client.user}")
    await update_status("待機中 ⏳")
    if not has_run:
        logging.info(f"起動時削除処理を実行（dry-run: {DRY_RUN}）")
        await update_status("掃除中 🧹")
        await cleanup_messages()
        await update_status("待機中 ⏳")
        has_run = True
        scheduled_cleanup.start()

@tasks.loop(minutes=1)
async def scheduled_cleanup():
    now = datetime.now()
    if now.hour == 3 and now.minute == 0:
        logging.info(f"定期削除処理 3:00 実行（dry-run: {DRY_RUN}）")
        await update_status("掃除中 🧹")
        await cleanup_messages()
        await update_status("待機中 ⏳")

if __name__ == "__main__":
    client.run(TOKEN)
