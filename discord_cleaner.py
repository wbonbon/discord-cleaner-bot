import discord
from discord.ext import tasks
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import logging

# --- ログ設定（journalctl向け） ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# --- 環境変数のロード ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DELETE_DAYS = int(os.getenv("DELETE_DAYS", 30))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

has_run = False  # 起動後一度だけ処理させる制御用

@client.event
async def on_ready():
    global has_run
    logging.info(f"Botログイン成功: {client.user}")

    # 起動時は「待機中」に設定
    await update_status("待機中 ⏳")

    if not has_run:
        logging.info(f"起動時削除処理を実行（dry-run: {DRY_RUN}）")
        await update_status("掃除中 🧹")
        await clean_messages()
        await update_status("待機中 ⏳")
        has_run = True
    else:
        logging.info("再接続検出 → 起動時処理はスキップ")

    check_time_and_clean.start()

@tasks.loop(minutes=1)
async def check_time_and_clean():
    now = datetime.now()
    if now.hour == 3 and now.minute == 0:
        logging.info(f"定期削除処理 3:00 開始（dry-run: {DRY_RUN}）")
        await update_status("掃除中 🧹")
        await clean_messages()
        await update_status("待機中 ⏳")

async def clean_messages():
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

        async for msg in channel.history(limit=1000):
            if msg.pinned:
                skipped_pinned += 1
                continue

            age = (datetime.now(timezone.utc) - msg.created_at).days
            if msg.created_at < threshold:
                if age > 14:
                    logging.warning(f"スキップ（API制限）: {msg.author} {age}日前 → 削除不可")
                    skipped_old += 1
                    continue

                if DRY_RUN:
                    logging.info(f"DRY-RUN: {msg.author} {age}日前 → 内容: {msg.content}")
                else:
                    try:
                        await msg.delete()
                        logging.info(f"削除完了: {msg.author} {age}日前のメッセージ")
                        deleted_count += 1
                    except Exception as e:
                        logging.error(f"削除失敗: {e}")

        logging.info(f"処理サマリ → 削除済: {deleted_count}件 / 古すぎ: {skipped_old}件 / ピン留め: {skipped_pinned}件")

    except Exception as e:
        logging.critical(f"削除処理中に致命的エラー: {e}")

async def update_status(text):
    await client.change_presence(activity=discord.Game(name=text))

if __name__ == "__main__":
    logging.debug("Bot起動開始 → client.run(TOKEN)")
    client.run(TOKEN)
