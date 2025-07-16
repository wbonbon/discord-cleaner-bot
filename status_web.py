import sqlite3
import subprocess
import re
from flask import Flask, render_template_string

app = Flask(__name__)
status = {
    "last_cleanup": "―",
    "deleted": "―",
    "skipped_too_old": "―",
    "skipped_pinned": "―",
    "non_target": "―",
    "dry_run": "―",
    "last_event": "Bot未稼働",
}

def parse_log_line(line: str):
    if "削除処理" in line:
        status["last_event"] = "削除処理開始"
        status["dry_run"] = "True" if "dry-run: True" in line else "False"
        ts = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line)
        if ts:
            status["last_cleanup"] = ts.group()
    elif "処理サマリ" in line:
        m = re.search(r"削除済: (\d+)件 / 古すぎ: (\d+)件 / ピン留め: (\d+)件 / 対象外: (\d+)件", line)
        if m:
            status["deleted"] = m.group(1)
            status["skipped_too_old"] = m.group(2)
            status["skipped_pinned"] = m.group(3)
            status["non_target"] = m.group(4)
            status["last_event"] = "削除完了"
    elif "Websocket closed" in line:
        status["last_event"] = "切断→再接続中"
    elif "RESUMED" in line:
        status["last_event"] = "再接続成功"

def load_recent_logs():
    try:
        out = subprocess.check_output(
            ["journalctl", "-u", "discord-cleaner.service", "-n", "30", "--no-pager"],
            text=True
        )
        for line in out.splitlines():
            parse_log_line(line)
    except Exception as e:
        status["last_event"] = f"ログ取得失敗: {e}"

@app.route("/status")
def status_page():
    load_recent_logs()
    html = f"""
    <html><head><title>Status</title>
    <meta http-equiv="refresh" content="5">
    <style>body{{font-family:sans-serif;line-height:1.6;}}</style></head><body>
    <h2>🧹 Discord Cleaner Bot 状態</h2>
    <ul>
        <li><strong>最新処理時刻：</strong> {status["last_cleanup"]}</li>
        <li><strong>削除件数：</strong> {status["deleted"]}</li>
        <li><strong>古すぎスキップ：</strong> {status["skipped_too_old"]}</li>
        <li><strong>ピン留めスキップ：</strong> {status["skipped_pinned"]}</li>
        <li><strong>対象外メッセージ：</strong> {status["non_target"]}</li>
        <li><strong>DRY_RUN モード：</strong> {status["dry_run"]}</li>
        <li><strong>Bot状態：</strong> {status["last_event"]}</li>
    </ul>
    <p><a href="/history">📜 履歴を表示する</a></p>
    </body></html>
    """
    return render_template_string(html)

@app.route("/history")
def history_page():
    conn = sqlite3.connect("discord-cleaner-history.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, deleted, skipped_too_old, skipped_pinned, non_target, dry_run
        FROM history ORDER BY id DESC LIMIT 20
    """)
    rows = cursor.fetchall()
    conn.close()

    html = """
    <html><head><title>履歴</title>
    <style>
        body{font-family:sans-serif;margin:2em;}
        table{border-collapse:collapse;width:100%;}
        th, td{padding:0.6em;border:1px solid #ccc;text-align:center;}
        th{background:#f2f2f2;}
    </style></head><body>
    <h2>📊 Discord Cleaner Bot 履歴</h2>
    <table>
    <tr><th>実行時刻</th><th>削除</th><th>古すぎ</th><th>ピン留め</th><th>対象外</th><th>DRY_RUN</th></tr>
    """
    for row in rows:
        html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
    html += """
    </table>
    <p><a href="/status">⬅️ 状態に戻る</a></p>
    </body></html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app
