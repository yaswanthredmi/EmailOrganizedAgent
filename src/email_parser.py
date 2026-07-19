"""把 Gmail API 返回的原始 message 解析成干净的结构化字典。"""
import base64
import re
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup


def _decode_b64url(data: str) -> bytes:
    if not data:
        return b""
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _walk_parts(payload: dict):
    """深度遍历 MIME 各部分，收集 text/plain 与 text/html 内容。"""
    plain, html = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if mime == "text/plain" and data:
            plain.append(_decode_b64url(data).decode("utf-8", "replace"))
        elif mime == "text/html" and data:
            html.append(_decode_b64url(data).decode("utf-8", "replace"))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return "\n".join(plain).strip(), "\n".join(html).strip()


def _get_header(headers: list, name: str) -> str:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def parse_message(message: dict) -> dict:
    """输入 users.messages.get(format='full') 的返回，输出结构化字段。"""
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    from_raw = _get_header(headers, "From")
    from_name, from_email = parseaddr(from_raw)

    date_raw = _get_header(headers, "Date")
    date_iso = ""
    if date_raw:
        try:
            date_iso = parsedate_to_datetime(date_raw).isoformat()
        except (TypeError, ValueError):
            date_iso = ""

    plain, html = _walk_parts(payload)
    body_text = plain or (_html_to_text(html) if html else "")
    if not body_text:
        body_text = message.get("snippet", "")

    return {
        "msg_id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "from_name": from_name or from_email,
        "from_email": from_email,
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date_iso": date_iso,
        "date_raw": date_raw,
        "message_id_header": _get_header(headers, "Message-ID"),
        "references_header": _get_header(headers, "References"),
        "body_text": body_text.strip(),
        "snippet": message.get("snippet", ""),
    }
