import os
import sqlite3
import subprocess
from flask import Flask, render_template_string
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

def load_recent_logs():
    try:
        out = subprocess.check_output(
            ["journalctl", "-u", "discord-cleaner.service", "-n", "100", "--no-pager"],
            text=True
        )
        for line in out.splitlines():
            parse_log_line(line, status)
    except Exception as e:
        status["last_event"] = f"ログ取得失敗: {e}"

@app.route("/status")
def status_page():
    load_recent_logs()

    html = f"""
    <html><head>
    <title>Status</title>
    <meta http-equiv="refresh" content="10">
    <style>body{{font-family:sans-serif;line-height:1.6;}}</style>
    </head><body>
    <h2>🧹 Discord Cleaner Bot 状態</h2>
    <ul>
      <li><strong>最新処理時刻（JST）：</strong> {status["last_cleanup"]}</li>
      <li><strong>削除件数：</strong> {status["deleted"]}</li>
      <li><strong>古すぎスキップ：</strong> {status["skipped_too_old"]}</li>
      <li><strong>ピン留めスキップ：</strong> {status["skipped_pinned"]}</li>
      <li><strong>対象外：</strong> {status["non_target"]}</li>
      <li><strong>DRY_RUN モード：</strong> {status["dry_run"]}</li>
      <li><strong>Bot 状態：</strong> {status["last_event"]}</li>
    </ul>
    <p><a href="/history">📈 履歴を見る</a></p>
    </body></html>
    """
    return render_template_string(html)

@app.route("/history")
def history_page():
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, deleted, skipped_too_old, skipped_pinned, non_target, dry_run
        FROM history
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()
    conn.close()

    html = """
    <html><head>
    <title>履歴</title>
    <style>
      body {font-family:sans-serif;margin:2em;}
      table {border-collapse:collapse;width:100%;}
      th, td {padding:0.6em;border:1px solid #ccc;text-align:center;}
      th {background:#f2f2f2;}
    </style></head><body>
    <h2>📊 Discord Cleaner Bot 履歴</h2>
    <table>
      <tr><th>実行時刻（JST）</th><th>削除</th><th>古すぎ</th><th>ピン留め</th><th>対象外</th><th>DRY_RUN</th></tr>
    """
    from log_utils import to_jst  # JST変換関数を使用

    for row in rows:
        ts_jst = to_jst(row[0])
        html += (
            f"<tr><td>{ts_jst}</td>"
            f"<td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td><td>{row[5]}</td></tr>"
        )

    html += """
    </table>
    <p><a href="/status">⬅️ 状態に戻る</a></p>
    </body></html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
