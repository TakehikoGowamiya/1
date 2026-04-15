"""
Slack Webhook 使用例

実行前に .env.example を参考に .env ファイルを作成してください:
  cp .env.example .env
  # .env の SLACK_WEBHOOK_URL を実際の値に書き換える

実行:
  pip install -r requirements.txt
  python main.py
"""

from dotenv import load_dotenv
from slack_webhook import SlackWebhook, SlackWebhookError

load_dotenv()


def main():
    slack = SlackWebhook()

    # --- 1. シンプルなテキスト送信 ---
    slack.send("こんにちは！Slack Webhook 連携のテストです。")

    # --- 2. ユーザー名・絵文字を変えて送信 ---
    slack.send(
        text="デプロイが完了しました :tada:",
        username="Deploy Bot",
        icon_emoji=":rocket:",
    )

    # --- 3. アラート通知 (info / warning / error) ---
    slack.send_alert(
        title="バッチ処理完了",
        message="100 件のレコードを正常に処理しました。",
        level="info",
        fields={"処理件数": "100", "所要時間": "3.2s"},
    )

    slack.send_alert(
        title="ディスク使用率が高くなっています",
        message="サーバー web-01 のディスク使用率が 85% を超えました。",
        level="warning",
        fields={"サーバー": "web-01", "使用率": "85%"},
    )

    slack.send_alert(
        title="エラーが発生しました",
        message="データベース接続に失敗しました。",
        level="error",
        fields={"エラーコード": "DB_CONN_TIMEOUT", "発生時刻": "2026-04-15 12:34:56"},
    )

    # --- 4. Block Kit によるリッチメッセージ ---
    slack.send_blocks(
        text="週次レポート",
        blocks=[
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "週次レポート :bar_chart:"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*新規ユーザー*\n120 人"},
                    {"type": "mrkdwn", "text": "*売上*\n¥1,250,000"},
                    {"type": "mrkdwn", "text": "*エラー件数*\n3 件"},
                    {"type": "mrkdwn", "text": "*稼働率*\n99.9%"},
                ],
            },
        ],
    )

    print("すべてのメッセージを送信しました。")


if __name__ == "__main__":
    try:
        main()
    except SlackWebhookError as e:
        print(f"送信エラー: {e}")
    except ValueError as e:
        print(f"設定エラー: {e}")
