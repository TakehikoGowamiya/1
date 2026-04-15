"""
Outlook MCP サーバー

Claude Code からこのサーバーを登録することで、
Claude が直接 Outlook の予定・メールを参照できるようになります。

起動方法:
  python mcp_server.py

Claude Code への登録方法 (.claude/settings.json):
  {
    "mcpServers": {
      "outlook": {
        "command": "python",
        "args": ["/path/to/mcp_server.py"],
        "env": {
          "AZURE_CLIENT_ID": "your_client_id",
          "AZURE_TENANT_ID": "common"
        }
      }
    }
  }
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from outlook_client import OutlookClient

# グローバルクライアント (初回ツール呼び出し時に初期化)
_client: OutlookClient | None = None


def get_client() -> OutlookClient:
    global _client
    if _client is None:
        _client = OutlookClient()
        _client.authenticate()
    return _client


def format_events(events: list[dict]) -> str:
    if not events:
        return "予定はありません。"

    lines = []
    for e in events:
        start: datetime = e["start"]
        end: datetime = e["end"]
        time_str = f"{start.strftime('%H:%M')} 〜 {end.strftime('%H:%M')}"
        line = f"・{time_str}  {e['subject']}"
        if e["location"]:
            line += f"  [{e['location']}]"
        if e["is_online"] and e["online_url"]:
            line += f"\n  参加URL: {e['online_url']}"
        lines.append(line)

    return "\n".join(lines)


def format_mails(mails: list[dict]) -> str:
    if not mails:
        return "未読メールはありません。"

    lines = []
    jst = timezone(timedelta(hours=9))
    for m in mails:
        received: datetime = m["received_at"].astimezone(jst)
        lines.append(
            f"・{received.strftime('%m/%d %H:%M')}  {m['subject']}\n"
            f"  From: {m['from_name']} <{m['from_email']}>\n"
            f"  {m['preview']}"
        )

    return "\n\n".join(lines)


# ------------------------------------------------------------------
# MCP サーバー定義
# ------------------------------------------------------------------

app = Server("outlook")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_today_events",
            description=(
                "今日の Outlook カレンダーの予定一覧を取得します。"
                "「今日の予定は？」「スケジュールを教えて」などの質問に答えるために使います。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "timezone_offset": {
                        "type": "integer",
                        "description": "UTC からのタイムゾーンオフセット (時間)。デフォルト 9 (JST)。",
                        "default": 9,
                    }
                },
            },
        ),
        Tool(
            name="get_upcoming_events",
            description=(
                "指定した分以内に開始する Outlook の予定を取得します。"
                "「次の会議は？」「もうすぐ始まる予定は？」などに答えるために使います。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "何分以内に始まる予定を取得するか。デフォルト 60。",
                        "default": 60,
                    },
                    "timezone_offset": {
                        "type": "integer",
                        "description": "UTC からのタイムゾーンオフセット (時間)。デフォルト 9 (JST)。",
                        "default": 9,
                    },
                },
            },
        ),
        Tool(
            name="get_unread_mails",
            description=(
                "Outlook の未読メールを取得します。"
                "「未読メールは？」「新着メールを教えて」などに答えるために使います。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "top": {
                        "type": "integer",
                        "description": "取得する件数 (最大 20)。デフォルト 5。",
                        "default": 5,
                    }
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    client = get_client()

    if name == "get_today_events":
        tz_offset = arguments.get("timezone_offset", 9)
        events = client.get_today_events(timezone_offset_hours=tz_offset)
        today = datetime.now(timezone(timedelta(hours=tz_offset))).strftime("%Y年%m月%d日")
        result = f"【{today} の予定】\n\n{format_events(events)}"

    elif name == "get_upcoming_events":
        minutes = min(arguments.get("minutes", 60), 1440)
        tz_offset = arguments.get("timezone_offset", 9)
        events = client.get_upcoming_events(minutes=minutes, timezone_offset_hours=tz_offset)
        result = f"【今後 {minutes} 分以内の予定】\n\n{format_events(events)}"

    elif name == "get_unread_mails":
        top = min(arguments.get("top", 5), 20)
        mails = client.get_unread_mails(top=top)
        result = f"【未読メール (最新 {top} 件)】\n\n{format_mails(mails)}"

    else:
        result = f"未知のツール: {name}"

    return [TextContent(type="text", text=result)]


# ------------------------------------------------------------------
# エントリーポイント
# ------------------------------------------------------------------

async def main():
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
