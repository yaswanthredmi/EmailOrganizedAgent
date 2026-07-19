"""可选兜底：当学校 M365 邮箱无法自动转发到 Gmail 时，用 Microsoft Graph 直接读取。

采用 MSAL 设备码(device code)登录，无需公网回调，适合本地脚本。
仅实现「读未读 + 标记已读」；给学校邮箱发回复可按需另行扩展 send。
需要在 Azure 注册一个应用，拿到 client_id，并授予委托权限 Mail.Read（或 Mail.ReadWrite）。
"""
import json

import config
from bs4 import BeautifulSoup

GRAPH_SCOPES = ["Mail.ReadWrite"]
GRAPH_API = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/{tenant}"


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n").strip()


def _get_token() -> str:
    import msal  # 延迟导入，未启用兜底时无需安装

    config.require("GRAPH_CLIENT_ID")
    cache = msal.SerializableTokenCache()
    if config.GRAPH_TOKEN_FILE.exists():
        cache.deserialize(config.GRAPH_TOKEN_FILE.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        config.GRAPH_CLIENT_ID,
        authority=AUTHORITY.format(tenant=config.GRAPH_TENANT_ID),
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"发起设备码登录失败：{json.dumps(flow, ensure_ascii=False)}")
        print(flow["message"])  # 提示用户到浏览器输入验证码
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Graph 获取 token 失败：{result.get('error_description', result)}")

    if cache.has_state_changed:
        config.GRAPH_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.GRAPH_TOKEN_FILE.write_text(cache.serialize(), encoding="utf-8")

    return result["access_token"]


def list_unread(max_results: int = None) -> list:
    """返回标准化后的邮件字典列表，字段与 email_parser.parse_message 对齐。"""
    import requests

    top = max_results or config.GRAPH_MAX_RESULTS
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "$filter": "isRead eq false",
        "$top": top,
        "$orderby": "receivedDateTime desc",
        "$select": "id,conversationId,subject,from,receivedDateTime,body,bodyPreview,internetMessageId",
    }
    resp = requests.get(f"{GRAPH_API}/me/messages", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("value", [])

    out = []
    for it in items:
        sender = (it.get("from") or {}).get("emailAddress", {})
        body = it.get("body", {})
        content = body.get("content", "")
        text = _html_to_text(content) if body.get("contentType") == "html" else content
        out.append({
            "msg_id": "graph:" + it.get("id", ""),
            "graph_id": it.get("id", ""),
            "thread_id": it.get("conversationId", ""),
            "from_name": sender.get("name", ""),
            "from_email": sender.get("address", ""),
            "to": "",
            "subject": it.get("subject", ""),
            "date_iso": it.get("receivedDateTime", ""),
            "date_raw": it.get("receivedDateTime", ""),
            "message_id_header": it.get("internetMessageId", ""),
            "references_header": "",
            "body_text": (text or it.get("bodyPreview", "")).strip(),
            "snippet": it.get("bodyPreview", ""),
        })
    return out


def mark_read(graph_id: str):
    import requests

    token = _get_token()
    resp = requests.patch(
        f"{GRAPH_API}/me/messages/{graph_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"isRead": True},
        timeout=30,
    )
    resp.raise_for_status()
