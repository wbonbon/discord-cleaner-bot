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
logging.info(f"削除処理開始（dry-run: {DRY_RUN})")

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

@client.event
async def on_ready():
    global has_run
    logging.info(f"Botログイン成功: {client.user}")
    await update_status("待機中 ⏳")
    if not has_run:
        await update_status("掃除中 🧹")
        await cleanup_messages()
        await update_status("待機中 ⏳")
        has_run = True
        scheduled_cleanup.start()

@tasks.loop(minutes=1)
async def scheduled_cleanup():
    now = datetime.now()
    if now.hour == 3 and now.minute == 0:
        await update_status("掃除中 🧹")
        await cleanup_messages()
        await update_status("待機中 ⏳")

if __name__ == "__main__":
    client.run(TOKEN)
