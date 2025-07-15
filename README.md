# Discord Cleaner Bot 🧹

古い未ピン留めメッセージを削除する Discord Bot。起動時と毎朝3:00に動作します。

## 特徴
- 起動時＋定刻（3:00）に自動削除
- `.env` による安全な設定管理
- `DRY_RUN` モードで安全に動作確認
- Discord API の削除制限（14日）にも対応
- ステータスメッセージで状況表示
- journalctl で詳細ログ追跡可能

## 使い方

1. `.env.example` を `.env` にコピーして必要な情報を設定
2. 必要ライブラリをインストール：
   ```bash
   pip install discord.py python-dotenv
