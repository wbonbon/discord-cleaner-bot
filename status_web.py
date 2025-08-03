import os
import sqlite3
import subprocess
import logging
from flask import Flask, render_template
from log_utils import parse_log_line, to_jst

app = Flask(__name__)

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

def get_latest_cleanup_status():
    """
    データベースから最新のクリーンアップ履歴を取得する。
    クリーンアップのサマリー情報はこの関数で一元的に取得する。
    """
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT timestamp, deleted, skipped_too_old, skipped_pinned, non_target, dry_run
            FROM history
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            # DBから取得した最新の情報を辞書に格納
            return {
                "last_cleanup": to_jst(row[0]),
                "deleted": row[1],
                "skipped_too_old": row[2],
                "skipped_pinned": row[3],
                "non_target": row[4],
                "dry_run": "True" if row[5] else "False" # Boolean値を文字列に変換
            }
    except sqlite3.OperationalError as e:
        logging.error(f"データベースの読み込み失敗: {e}")
    finally:
        conn.close()
    return None

def load_recent_logs():
    """
    journalctlからBotの状態ログ（再接続など）を取得し、status辞書を更新する。
    クリーンアップのサマリー情報はデータベースから取得するため、ここでは解析しない。
    """
    try:
        # 修正: ログの行数を50に減らし、パフォーマンスをさらに向上させる
        out = subprocess.check_output(
            ["journalctl", "-u", "discord-cleaner.service", "-n", "50", "--no-pager"],
            text=True
        )
        for line in reversed(out.splitlines()):
            # 処理サマリのログ行はデータベースから取得するため、この行は削除しました。
            parse_log_line(line, status)
    except Exception as e:
        status["last_event"] = f"ログ取得失敗: {e}"
        logging.error(f"ログ取得失敗: {e}")

@app.route("/status")
def status_page():
    """ボットの状態を表示するページ"""
    global status
    # 状態をリセットし、初期値で上書きされないようにする
    status = {
        "last_cleanup": "―",
        "deleted": "―",
        "skipped_too_old": "―",
        "skipped_pinned": "―",
        "non_target": "―",
        "dry_run": "―",
        "last_event": "Bot未稼働",
    }
    
    # データベースから最新のクリーンアップ情報を取得
    cleanup_status = get_latest_cleanup_status()
    if cleanup_status:
        status.update(cleanup_status)
    
    # journalctlからBotの最新イベント情報を取得
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
