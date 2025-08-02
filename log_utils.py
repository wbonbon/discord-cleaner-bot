import logging
import re
from typing import Optional
from datetime import datetime, timezone, timedelta

def format_cleanup_summary(deleted: int, skipped_old: int, skipped_pinned: int, non_target: int) -> str:
    """メッセージ削除のサマリーをフォーマットする"""
    return f"処理サマリ → 削除済: {deleted}件 / 古すぎ: {skipped_old}件 / ピン留め: {skipped_pinned}件 / 対象外: {non_target}件"

def log_cleanup_summary(deleted: int, skipped_old: int, skipped_pinned: int, non_target: int):
    """サマリーをログに出力する"""
    logging.info(format_cleanup_summary(deleted, skipped_old, skipped_pinned, non_target))

def get_utc_timestamp() -> str:
    """UTCタイムスタンプを文字列で取得する (ベストプラクティスに準拠)"""
    # 修正: datetime.utcnow() から datetime.now(timezone.utc) に変更
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def get_cleanup_threshold(days: int) -> datetime:
    """クリーンアップの閾値となるUTC日時を取得する"""
    # 修正: datetime.utcnow() から datetime.now(timezone.utc) に変更
    return datetime.now(timezone.utc) - timedelta(days=days)

def to_jst(utc_str: str) -> str:
    """UTC文字列をJSTに変換する"""
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9)))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    # 修正: 広範な Exception から ValueError に変更
    except ValueError:
        return utc_str

def parse_line(line: str) -> Optional[dict]:
    """ログ行を解析して辞書を返す"""
    if "処理サマリ" in line:
        m = re.search(r"削除済: (\d+)件 / 古すぎ: (\d+)件 / ピン留め: (\d+)件 / 対象外: (\d+)件", line)
        if m:
            return {
                "deleted": int(m.group(1)),
                "skipped_too_old": int(m.group(2)),
                "skipped_pinned": int(m.group(3)),
                "non_target": int(m.group(4)),
                "last_event": "削除完了"
            }
    elif "削除処理" in line:
        ts = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", line)
        timestamp = ts.group() if ts else "―"
        return {
            "last_event": "削除処理開始",
            "dry_run": "True" if "dry-run: True" in line else "False",
            "last_cleanup": timestamp
        }
    elif "Websocket closed" in line:
        return {"last_event": "切断→再接続中"}
    elif "RESUMED" in line:
        return {"last_event": "再接続成功"}
    return None

def parse_log_line(line: str, status: dict):
    """ログ行を解析し、状態辞書を更新する"""
    parsed = parse_line(line)
    if parsed:
        status.update(parsed)
