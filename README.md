# 重要イベントNEWS通知アプリ

毎朝08:30（日本時間）に、本日・明日・明後日の重要イベントを1通のLINEメッセージで通知するGitHub Actionsアプリです。

## 通知対象

- 米国・日本・欧州・英国・中国の高重要度の経済指標や予定イベント（Forex Factoryの公開カレンダー）
- 日本企業の決算発表：時価総額5,000億円以上、または半導体・金融・大型テック・自動車などの重点企業（Traders Web）
- 米国企業の決算発表：超大型株と半導体・金融などの重点企業（Nasdaqの公開カレンダー）

## 時刻の扱い

すべて `Asia/Tokyo`（日本時間）に統一します。米国企業決算は、Nasdaqの「米国寄り前／米国引け後」区分を使って東部時間の代表時刻に変換します。時刻が提供されない場合は「時刻未確認」と表示します。

## セットアップ

1. GitHubで新しいリポジトリを作成（例：`important-events-news`）。
2. このZIPの内容をリポジトリのルートにアップロード。`.github/workflows/important-events-news.yml` の階層を保ってください。
3. `Settings` → `Secrets and variables` → `Actions` → `New repository secret` で、既存のLINE通知と同じ値を登録します。
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_TO`
4. `Actions` タブを開き、`Important Events NEWS` を選択して `Run workflow`。
5. 最初は `calculate` を選択して実行ログの出力を確認。LINE送信は行いません。
6. 問題なければ `notify` を選択してLINE到達を確認。

## 自動実行

GitHub Actionsのスケジュールは毎日08:30 JST（UTC 23:30）です。GitHub Actionsのスケジュール実行は混雑時に遅延する場合があります。

## データソースと注意点

- Forex Factory公開カレンダー: https://www.forexfactory.com/calendar
- Traders Web決算発表スケジュール: https://www.traders.co.jp/market_jp/earnings_calendar/all/all/1
- Nasdaq決算カレンダー: https://www.nasdaq.com/market-activity/earnings

このアプリは無料で利用できる公開カレンダーを読み取りますが、各サイトの仕様変更、アクセス制限、掲載遅延で取得に失敗することがあります。決算予定や発表時刻は変更される場合があり、すべての重要イベントを完全に網羅する保証はありません。重要な売買判断の前には公式発表元で確認してください。

## トラブルシューティング

- `calculate` でエラーになったら、GitHub Actionsログのエラー全文を確認してください。
- `calculate` はLINE送信しません。`notify` はLINE送信します。
- LINEに届かない場合は `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_TO`、Botの友だち追加状態を確認してください。
- GitHub Actionsは予定時刻ちょうどに必ず起動する保証はありません。
