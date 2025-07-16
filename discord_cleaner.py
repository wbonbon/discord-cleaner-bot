import discord
import os
import asyncio
import sqlite3
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DELETE_DAYS = int(os.getenv("DELETE_DAYS", 7))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

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

async def cleanup_messages():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[ERROR] 指定チャンネル {CHANNEL_ID} が見つかりません")
        return

    print(f"[INFO] 削除対象条件: {DELETE_DAYS}日以上前 & 未ピン留め")
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=DELETE_DAYS)

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
            print(f"[DRY_RUN] 削除対象: {msg.id} | {msg.created_at} | {msg.content}")
        else:
            try:
                await msg.delete()
                deleted_count += 1
            except Exception as e:
                print(f"[ERROR] 削除失敗: {e}")

    summary = f"処理サマリ → 削除済: {deleted_count}件 / 古すぎ: {skipped_old}件 / ピン留め: {skipped_pinned}件"
    print(f"[INFO] {summary}")
    timestamp = now.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    save_history_to_db(timestamp, deleted_count, skipped_old, skipped_pinned, DRY_RUN)

@client.event
async def on_ready():
    print(f"[INFO] Botログイン成功: {client.user}")
    print(f"[INFO] 起動時削除処理を実行（dry-run: {DRY_RUN}）")
    await cleanup_messages()
    scheduled_cleanup.start()

@tasks.loop(hours=24)
async def scheduled_cleanup():
    now = datetime.now().astimezone()
    if now.hour == 3:
        print(f"[INFO] 定期削除処理 3:00 開始（dry-run: {DRY_RUN}）")
        await cleanup_messages()

client.run(TOKEN)
