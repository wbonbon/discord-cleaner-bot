import discord
import os
import asyncio
import sqlite3
import logging
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# --- ログ設定（journalctl用フォーマット） ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DELETE_DAYS = int(os.getenv("DELETE_DAYS", 7))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

has_run = False  # 起動時処理フラグ

# --- ステータス表示（DiscordのBotの「プレイ中」欄） ---
async def update_status(text):
    await client.change_presence(activity=discord.Game(name=text))

# --- 履歴保存（SQLite） ---
def save_history_to_db(timestamp, deleted, skipped_old, skipped_pinned, dry_run):
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            deleted INTEGER,
            skipped_too_old INTEGER,
            skipped_pinned INTEGER,
            dry_run BOOLEAN
        )
    """)
    cursor.execute("""
        INSERT INTO history (timestamp, deleted, skipped_too_old, skipped_pinned, dry_run)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, deleted, skipped_old, skipped_pinned, dry_run))
    conn.commit()
    conn.close()

# --- 削除処理 ---
async def cleanup_messages():
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        if channel is None:
            logging.error("チャンネル取得失敗（CHANNEL_IDが不正）")
            return

        threshold = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=DELETE_DAYS)
        logging.info(f"削除対象条件: {DELETE_DAYS}日以上前 & 未ピン留め")

        deleted_count = 0
        skipped_old = 0
        skipped_pinned = 0

        async for msg in channel.history(limit=None, oldest_first=True):
            if msg.pinned:
                skipped_pinned += 1
                continue
            if msg.created_at < threshold:
                skipped_old += 1
                continue

            if DRY_RUN:
                logging.info(f"DRY-RUN: {msg.id} | {msg.created_at} | {msg.content}")
            else:
                try:
                    await msg.delete()
                    deleted_count += 1
                except Exception as e:
                    logging.error(f"削除失敗: {e}")

        logging.info(f"処理サマリ → 削除済: {deleted_count}件 / 古すぎ: {skipped_old}件 / ピン留め: {skipped_pinned}件")

        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        save_history_to_db(timestamp, deleted_count, skipped_old, skipped_pinned, DRY_RUN)

    except Exception as e:
        logging.critical(f"削除処理中に致命的エラー: {e}")

# --- Bot起動時 ---
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
    else:
        logging.info("再接続検出 → 起動時処理はスキップ")

    scheduled_cleanup.start()

# --- 定期処理（毎日3時） ---
@tasks.loop(minutes=1)
async def scheduled_cleanup():
    now = datetime.now()
    if now.hour == 3 and now.minute == 0:
        logging.info(f"定期削除処理 3:00 開始（dry-run: {DRY_RUN}）")
        await update_status("掃除中 🧹")
        await cleanup_messages()
        await update_status("待機中 ⏳")

# --- Bot起動 ---
if __name__ == "__main__":
    logging.debug("Bot起動開始 → client.run(TOKEN)")
    client.run(TOKEN)
