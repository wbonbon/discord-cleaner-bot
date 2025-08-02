import os
import sqlite3
import subprocess
import logging
from flask import Flask, render_template
from log_utils import parse_log_line, to_jst

app = Flask(__name__)

# ログ初期化（status_web用の設定）
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 状態を保持する辞書
status = {
    "last_cleanup": "―",
    "deleted": "―",
    "skipped_too_old": "―",
    "skipped_pinned": "―",
    "non_target": "―",
    "dry_run": "―",
    "last_event": "Bot未稼働",
}

def load_recent_logs():
    """journalctlから最新のログを取得し、status辞書を更新する"""
    try:
        out = subprocess.check_output(
            ["journalctl", "-u", "discord-cleaner.service", "-n", "300", "--no-pager"],
            text=True
        )
        for line in out.splitlines():
            parse_log_line(line, status)
    except Exception as e:
        status["last_event"] = f"ログ取得失敗: {e}"
        logging.error(f"ログ取得失敗: {e}")

@app.route("/status")
def status_page():
    """ボットの状態を表示するページ"""
    load_recent_logs()
    # templates/status.htmlをレンダリング
    return render_template("status.html", status=status)

@app.route("/history")
def history_page():
    """ボットの実行履歴を表示するページ"""
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT timestamp, deleted, skipped_too_old, skipped_pinned, non_target, dry_run
            FROM history
            ORDER BY id DESC
            LIMIT 20
        """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        logging.error(f"データベースの読み込み失敗: {e}")
        rows = []
    finally:
        conn.close()

    # templates/history.htmlをレンダリング
    # to_jst関数もテンプレートに渡す
    return render_template("history.html", rows=rows, to_jst=to_jst)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
