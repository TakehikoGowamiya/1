"""
Slack Webhook Notification Module

Incoming Webhook URL を使って Slack にメッセージを送信します。
"""

import os
import json
import requests
from typing import Optional


class SlackWebhookError(Exception):
    """Slack Webhook 送信時のエラー"""
    pass


class SlackWebhook:
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Args:
            webhook_url: Slack Incoming Webhook URL。
                         省略した場合は環境変数 SLACK_WEBHOOK_URL を使用します。
        """
        self.webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError(
                "Webhook URL が設定されていません。"
                "引数 webhook_url を指定するか、環境変数 SLACK_WEBHOOK_URL を設定してください。"
            )

    def send(
        self,
        text: str,
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> None:
        """シンプルなテキストメッセージを送信します。

        Args:
            text: 送信するメッセージ本文。
            username: 表示名を上書きする場合に指定。
            icon_emoji: アイコン絵文字 (例: ":robot_face:")。
            channel: 送信先チャンネルを上書きする場合に指定 (例: "#general")。
        """
        payload: dict = {"text": text}
        if username:
            payload["username"] = username
        if icon_emoji:
            payload["icon_emoji"] = icon_emoji
        if channel:
            payload["channel"] = channel

        self._post(payload)

    def send_blocks(
        self,
        blocks: list,
        text: str = "",
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        channel: Optional[str] = None,
    ) -> None:
        """Block Kit を使ったリッチメッセージを送信します。

        Args:
            blocks: Slack Block Kit の blocks 配列。
            text: 通知用フォールバックテキスト (プッシュ通知などに表示)。
            username: 表示名を上書きする場合に指定。
            icon_emoji: アイコン絵文字。
            channel: 送信先チャンネルを上書きする場合に指定。
        """
        payload: dict = {"blocks": blocks, "text": text}
        if username:
            payload["username"] = username
        if icon_emoji:
            payload["icon_emoji"] = icon_emoji
        if channel:
            payload["channel"] = channel

        self._post(payload)

    def send_alert(
        self,
        title: str,
        message: str,
        level: str = "info",
        fields: Optional[dict] = None,
    ) -> None:
        """アラート形式のメッセージを送信します。

        Args:
            title: アラートのタイトル。
            message: アラートの本文。
            level: "info" / "warning" / "error" のいずれか。色分けに使用。
            fields: 追加フィールド {ラベル: 値} の辞書。
        """
        color_map = {
            "info": "#36a64f",
            "warning": "#ffcc00",
            "error": "#ff0000",
        }
        color = color_map.get(level, "#36a64f")

        attachment: dict = {
            "color": color,
            "title": title,
            "text": message,
            "footer": "Slack Webhook",
        }

        if fields:
            attachment["fields"] = [
                {"title": k, "value": v, "short": True}
                for k, v in fields.items()
            ]

        self._post({"attachments": [attachment]})

    def _post(self, payload: dict) -> None:
        """Webhook URL に JSON ペイロードを POST します。"""
        try:
            response = requests.post(
                self.webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except requests.exceptions.RequestException as e:
            raise SlackWebhookError(f"HTTP リクエストに失敗しました: {e}") from e

        if response.status_code != 200 or response.text != "ok":
            raise SlackWebhookError(
                f"Slack から異常なレスポンスが返されました。"
                f"ステータス: {response.status_code}, ボディ: {response.text!r}"
            )
