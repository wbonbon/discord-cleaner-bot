import discord
import os
import asyncio
import sqlite3
import logging
import re
from discord.ext import tasks
from discord import Embed
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DELETE_DAYS = int(os.getenv("DELETE_DAYS", 7))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
has_run = False

async def update_status(text):
    await client.change_presence(activity=discord.Game(name=text))

def save_history_to_db(timestamp, deleted, skipped_old, skipped_pinned, non_target, dry_run):
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            deleted INTEGER,
            skipped_too_old INTEGER,
            skipped_pinned INTEGER,
            non_target INTEGER,
            dry_run BOOLEAN
        )
    """)
    cursor.execute("""
        INSERT INTO history (timestamp, deleted, skipped_too_old, skipped_pinned, non_target, dry_run)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (timestamp, deleted, skipped_old, skipped_pinned, non_target, dry_run))
    conn.commit()
    conn.close()

async def cleanup_messages():
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        threshold = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=DELETE_DAYS)

        deleted = skipped_old = skipped_pinned = total = 0

        async for msg in channel.history(limit=None, oldest_first=True):
            total += 1

            if msg.pinned:
                skipped_pinned += 1
                continue

            if msg.created_at > threshold:
                # 新しすぎる投稿 → 処理対象外だが、履歴保存には含めない
                continue

            if DRY_RUN:
                logging.info(f"削除候補: {msg.id} | {msg.created_at} | {msg.content[:50]}")
            else:
                try:
                    await msg.delete()
                    deleted += 1
                    logging.info(f"削除済: {msg.id} | {msg.created_at} | {msg.content[:50]}")
                except Exception as e:
                    logging.error(f"削除失敗: {e}")

        non_target = total - (deleted + skipped_old + skipped_pinned)
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        save_history_to_db(timestamp, deleted, skipped_old, skipped_pinned, non_target, DRY_RUN)

        logging.info(
            f"処理サマリ → 削除済: {deleted}件 / 古すぎ: {skipped_old}件 / ピン留め: {skipped_pinned}件 / 対象外: {non_target}件"
        )

    except Exception as e:
        logging.critical(f"削除処理中に致命的エラー: {e}")

async def update_research_reset_pin_manual(next_time):
    channel = await client.fetch_channel(CHANNEL_ID)

    # 既存ピンのEmbedから日時抽出
    existing_time = None
    pinned_msg = None
    pins = await channel.pins()
    for pinned in pins:
        if pinned.embeds and pinned.embeds[0].title == "🧪 次回の研究度リセット予定":
            desc = pinned.embeds[0].description or ""
            m = re.search(r"<t:(\d+):F>", desc)
            if m:
                try:
                    existing_time = datetime.fromtimestamp(int(m.group(1)))
                    pinned_msg = pinned
                except Exception:
                    logging.warning("既存Embedピンの日時抽出に失敗")
            break

    now = datetime.now()
    if next_time < now:
        await channel.send("⏰ その予定はすでに過ぎています。")
        return

    if existing_time and next_time <= existing_time:
        await channel.send("📌 その予定はすでにピン留めされています。")
        return

    if pinned_msg:
        await pinned_msg.unpin()
        await pinned_msg.delete()
        logging.info(f"古いピンを削除: {existing_time}")

    unix_ts = int(next_time.timestamp())
    embed = Embed(
        title="🧪 次回の研究度リセット予定",
        description=f"<t:{unix_ts}:F>（<t:{unix_ts}:R>）にリセットされます！\n<@&1384067593425522769> の皆さん、準備してね。",
        color=0x6A5ACD
    )
    sent = await channel.send(embed=embed)
    await sent.pin()
    logging.info(f"新しい研究度リセット予定をピン留め: {next_time}")

@client.event
async def on_message(message):
    if message.guild is None and message.author != client.user:
        content = message.content.strip()

        if "研究度リセットだよ" in content and "occurs next at" in content:
            m = re.search(r"occurs next at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", content)
            if m:
                try:
                    next_time = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    await update_research_reset_pin_manual(next_time)
                    await message.channel.send("✅ 研究度リセット予定を更新しました！")
                except ValueError:
                    await message.channel.send("⚠️ 日付の形式が不正です。`YYYY-MM-DD HH:MM:SS` で送ってください。")
            else:
                await message.channel.send("⚠️ 日付の抽出に失敗しました。")
        else:
            await message.channel.send("🤔 そのメッセージは認識できません。\n`研究度リセットだよ ... occurs next at YYYY-MM-DD HH:MM:SS` の形式で送ってください。")

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
