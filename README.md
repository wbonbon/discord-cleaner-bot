# Discord Cleaner Bot

Discordの指定したチャンネルで、一定期間以上経過したピン留めされていない古いメッセージを自動で削除するBotです。`systemd`と連携して安定稼働し、Flask製のWebインターフェースで稼働状況を簡単に監視できます。

## ✨ 主な機能

* **定期的な自動削除**: Botの起動時と、毎日午前3時にメッセージを自動でクリーンアップします。

* **安全な設定管理**: `.env`ファイルでBotトークンやチャンネルIDを安全に管理します。

* **テストモード**: `DRY_RUN`モードを有効にすることで、実際にメッセージを削除せずに動作テストが可能です。

* **Webステータスページ**: Flask製のWeb UIで、Botの稼働状況やクリーンアップ履歴をリアルタイムに確認できます。

* **安定した運用**: `systemd`と連携し、Botをバックグラウンドで安定して稼働させることができます。

## 🛠️ セットアップ手順

### 1. リポジトリのクローン

```
git clone [https://github.com/wbonbon/discord-cleaner-bot.git](https://github.com/wbonbon/discord-cleaner-bot.git)
cd discord-cleaner-bot
```

### 2. Python仮想環境の構築

プロジェクトをクリーンな環境で管理するため、仮想環境を作成して有効化します。

```
python -m venv venv
source venv/bin/activate
```

### 3. 必要なライブラリのインストール

以下のコマンドで、`requirements.txt`に記載されているライブラリをインストールします。

```
pip install -r requirements.txt
```

### 4. `.env`ファイルの作成

`.env.example`ファイルをコピーして`.env`を作成し、設定情報を記述してください。

```

cp .env.example .env
```.env`ファイルの内容：

```

# Discord Developer Portalで取得したBotのトークン
DISCORD_TOKEN=YOUR_BOT_TOKEN

# メッセージを削除したいチャンネルのID (Discordで開発者モードを有効にしてIDをコピー)
CHANNEL_ID=YOUR_CHANNEL_ID

# テスト用のチャンネルID (テストモードで使用)
TEST_CHANNEL_ID=YOUR_TEST_CHANNEL_ID

# 削除するメッセージの経過日数
DELETE_DAYS=7

# テストモード (trueにすると実際には削除しない)
DRY_RUN=true

# 実行モード (live: 本番, dev: 開発)
MODE=live
```

## 🚀 実行方法

### 手動での実行

まず、以下のコマンドでBotを起動します。

```
python discord_cleaner.py
```

次に、別のターミナルでWebステータスサーバーを起動します。本番環境では`gunicorn`の使用を推奨します。

```
gunicorn --bind 0.0.0.0:5000 status_web:app
```

サーバーが起動したら、Webブラウザで `http://<サーバーのIPアドレス>:5000/status` にアクセスしてステータスを確認できます。

### systemdでのサービス化 (推奨)

BotとWebサーバーをバックグラウンドで安定稼働させるため、`systemd`にサービスとして登録することを強く推奨します。

#### 1. `discord-cleaner.service`の作成

```
sudo nano /etc/systemd/system/discord-cleaner.service
```

以下の内容を記述します。（`User`と`WorkingDirectory`、`ExecStart`のパスはご自身の環境に合わせて変更してください）

```
[Unit]
Description=Discord Cleaner Bot
After=network.target

[Service]
User=yosio
Group=yosio
WorkingDirectory=/home/yosio/discord-cleaner-bot
ExecStart=/home/yosio/discord-cleaner-bot/venv/bin/python discord_cleaner.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2. `status-web.service`の作成

```
sudo nano /etc/systemd/system/status-web.service
```

以下の内容を記述します。

```
[Unit]
Description=Status Web for Discord Cleaner Bot
After=network.target

[Service]
User=yosio
Group=yosio
WorkingDirectory=/home/yosio/discord-cleaner-bot
ExecStart=/home/yosio/discord-cleaner-bot/venv/bin/gunicorn --bind 0.0.0.0:5000 status_web:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 3. サービスの有効化と起動

```
# サービスを有効化 (OS起動時に自動起動)
sudo systemctl enable discord-cleaner.service
sudo systemctl enable status-web.service

# サービスを起動
sudo systemctl start discord-cleaner.service
sudo systemctl start status-web.service
```

ログは`journalctl -u discord-cleaner.service -f`で確認できます。

## 🔧 トラブルシューティング

* **Webページで`gunicorn`のタイムアウトエラーが出る場合**:
  `status-web.service`の`ExecStart`に`--timeout 120`オプションを追加して、タイムアウト時間を延長してみてください。

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。詳細は`LICENSE`ファイルをご覧ください。
