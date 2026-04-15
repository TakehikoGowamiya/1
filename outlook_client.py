"""
Outlook クライアント (Microsoft Graph API)

認証方式: MSAL デバイスコードフロー
  - ブラウザで microsoft.com/devicelogin にアクセスしてログインするだけで使えます。
  - 取得したトークンはローカルにキャッシュされ、次回以降は再ログイン不要です。
"""

import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import msal
import requests


# Microsoft Graph API のエンドポイント
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# 必要なスコープ
SCOPES = ["Calendars.Read", "Mail.Read", "Tasks.Read"]

# トークンキャッシュファイルのパス
TOKEN_CACHE_PATH = Path(".token_cache.json")


class OutlookClient:
    def __init__(
        self,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Args:
            client_id: Azure AD アプリの クライアント ID。
                       省略した場合は環境変数 AZURE_CLIENT_ID を使用。
            tenant_id: テナント ID。省略した場合は環境変数 AZURE_TENANT_ID を使用。
                       個人アカウントの場合は "consumers" を指定。
        """
        self.client_id = client_id or os.environ.get("AZURE_CLIENT_ID")
        self.tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "common")

        if not self.client_id:
            raise ValueError(
                "クライアント ID が設定されていません。"
                "引数 client_id を指定するか、環境変数 AZURE_CLIENT_ID を設定してください。"
            )

        self._cache = self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=self._cache,
        )
        self._token: Optional[str] = None

    # ------------------------------------------------------------------
    # 認証
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """アクセストークンを取得します。
        キャッシュにトークンがある場合は再利用します。
        ない場合はデバイスコードフローでログインを促します。
        """
        accounts = self._app.get_accounts()
        result = None

        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            flow = self._app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"デバイスフローの開始に失敗しました: {flow}")

            print("\n" + "=" * 60)
            print(flow["message"])
            print("=" * 60 + "\n")

            result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise RuntimeError(f"認証に失敗しました: {result.get('error_description')}")

        self._token = result["access_token"]
        self._save_cache()

    # ------------------------------------------------------------------
    # カレンダー
    # ------------------------------------------------------------------

    def get_today_events(self, timezone_offset_hours: int = 9) -> list[dict]:
        """今日のカレンダーイベントを取得します。

        Args:
            timezone_offset_hours: UTC からのオフセット (デフォルト: 9 = JST)。

        Returns:
            イベント辞書のリスト。各辞書のキー:
              - subject: 件名
              - start: 開始時刻 (datetime)
              - end: 終了時刻 (datetime)
              - location: 場所
              - is_online: オンライン会議かどうか
              - online_url: オンライン会議 URL
        """
        tz = timezone(timedelta(hours=timezone_offset_hours))
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        params = {
            "$orderby": "start/dateTime",
            "$select": "subject,start,end,location,isOnlineMeeting,onlineMeetingUrl,onlineMeeting",
            "startDateTime": start_of_day.isoformat(),
            "endDateTime": end_of_day.isoformat(),
        }

        data = self._get("/me/calendarView", params=params)
        return [self._parse_event(e, tz) for e in data.get("value", [])]

    def get_upcoming_events(self, minutes: int = 15, timezone_offset_hours: int = 9) -> list[dict]:
        """指定した分以内に始まるイベントを取得します (リマインダー用)。

        Args:
            minutes: 何分以内に開始するイベントを取得するか。
            timezone_offset_hours: UTC からのオフセット。
        """
        tz = timezone(timedelta(hours=timezone_offset_hours))
        now = datetime.now(tz)
        soon = now + timedelta(minutes=minutes)

        params = {
            "$orderby": "start/dateTime",
            "$select": "subject,start,end,location,isOnlineMeeting,onlineMeetingUrl,onlineMeeting",
            "startDateTime": now.isoformat(),
            "endDateTime": soon.isoformat(),
        }

        data = self._get("/me/calendarView", params=params)
        return [self._parse_event(e, tz) for e in data.get("value", [])]

    # ------------------------------------------------------------------
    # メール
    # ------------------------------------------------------------------

    def get_unread_mails(self, top: int = 5) -> list[dict]:
        """未読メールを取得します。

        Args:
            top: 取得件数 (デフォルト: 5)。

        Returns:
            メール辞書のリスト。各辞書のキー:
              - subject: 件名
              - from_name: 送信者名
              - from_email: 送信者メールアドレス
              - received_at: 受信日時 (datetime)
              - preview: 本文のプレビュー (最大 200 文字)
        """
        params = {
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime desc",
            "$top": top,
            "$select": "subject,from,receivedDateTime,bodyPreview",
        }
        data = self._get("/me/messages", params=params)
        return [self._parse_mail(m) for m in data.get("value", [])]

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        if not self._token:
            raise RuntimeError("先に authenticate() を呼び出してください。")

        response = requests.get(
            f"{GRAPH_BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _parse_event(raw: dict, tz: timezone) -> dict:
        def parse_dt(dt_str: str) -> datetime:
            dt = datetime.fromisoformat(dt_str.rstrip("Z"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(tz)

        online_url = (
            raw.get("onlineMeetingUrl")
            or (raw.get("onlineMeeting") or {}).get("joinUrl")
        )

        return {
            "subject": raw.get("subject", "(件名なし)"),
            "start": parse_dt(raw["start"]["dateTime"]),
            "end": parse_dt(raw["end"]["dateTime"]),
            "location": (raw.get("location") or {}).get("displayName", ""),
            "is_online": raw.get("isOnlineMeeting", False),
            "online_url": online_url or "",
        }

    @staticmethod
    def _parse_mail(raw: dict) -> dict:
        sender = raw.get("from", {}).get("emailAddress", {})
        received = raw.get("receivedDateTime", "")
        dt = datetime.fromisoformat(received.rstrip("Z")).replace(tzinfo=timezone.utc)

        return {
            "subject": raw.get("subject", "(件名なし)"),
            "from_name": sender.get("name", ""),
            "from_email": sender.get("address", ""),
            "received_at": dt,
            "preview": raw.get("bodyPreview", "")[:200],
        }

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if TOKEN_CACHE_PATH.exists():
            cache.deserialize(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        return cache

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            TOKEN_CACHE_PATH.write_text(
                self._cache.serialize(), encoding="utf-8"
            )
