#!/bin/bash
# ============================================================
# セットアップスクリプト（Mac用）
# 実行: bash setup.sh
# ============================================================

echo "🏙 横浜中古マンション相場 定点観測システム セットアップ"
echo "============================================================"

# 1. 依存ライブラリのインストール
echo "📦 Pythonライブラリをインストール中..."
pip3 install requests beautifulsoup4 lxml --quiet
echo "✅ インストール完了"

# 2. ディレクトリ作成
mkdir -p data reports
echo "✅ data/ reports/ ディレクトリ作成"

# 3. macOS launchd の週次自動実行を設定
# 毎週月曜 8:00 に自動実行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/com.yuto.yokohama-estate.plist"
LOG_PATH="$SCRIPT_DIR/data/run.log"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yuto.yokohama-estate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$SCRIPT_DIR/run.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
</dict>
</plist>
EOF

# launchd に登録
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "✅ 週次自動実行を設定しました（毎週月曜 8:00）"
echo ""
echo "============================================================"
echo "🚀 今すぐ手動実行するには:"
echo "   python3 run.py"
echo ""
echo "📊 レポートを開くには（実行後）:"
echo "   open reports/\$(date +%Y-%m-%d).html"
echo ""
echo "🗂 価格履歴CSV:"
echo "   data/history.csv"
echo ""
echo "⚙️  自動実行を止めるには:"
echo "   launchctl unload ~/Library/LaunchAgents/com.yuto.yokohama-estate.plist"
echo "============================================================"
