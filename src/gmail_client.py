"""Gmail API 封装：OAuth 授权、读未读、取详情、打标签、线程内回复。

注意：本机 httplib2 连 Google 会超时，因此全部走 google.auth + requests。
"""
import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
GMAIL_API = "https://gmail.googleapis.com/gmail/v1"


def _get_credentials() -> Credentials:
    creds = None
    token_file = config.GMAIL_TOKEN_FILE
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not config.GMAIL_CREDENTIALS_FILE.exists():
                raise SystemExit(
                    f"找不到 Gmail 凭证文件：{config.GMAIL_CREDENTIALS_FILE}\n"
                    "请到 GCP 下载 OAuth 客户端 JSON，放到该路径（见 README）。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GMAIL_CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_service():
    """返回已授权的 requests Session（兼容旧调用名）。"""
    return AuthorizedSession(_get_credentials())


def _api(session: AuthorizedSession, method: str, path: str, **kwargs):
    url = f"{GMAIL_API}{path}"
    resp = session.request(method, url, timeout=60, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"Gmail API {method} {path} -> {resp.status_code}: {resp.text[:500]}")
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


def list_messages(session, query: str, max_results: int):
    data = _api(
        session,
        "GET",
        "/users/me/messages",
        params={"q": query, "maxResults": max_results},
    )
    return data.get("messages", [])


def get_message(session, msg_id: str) -> dict:
    return _api(session, "GET", f"/users/me/messages/{msg_id}", params={"format": "full"})


def get_profile_email(session) -> str:
    return _api(session, "GET", "/users/me/profile").get("emailAddress", "")


def get_or_create_label(session, name: str) -> str:
    labels = _api(session, "GET", "/users/me/labels").get("labels", [])
    for lb in labels:
        if lb.get("name") == name:
            return lb["id"]
    created = _api(
        session,
        "POST",
        "/users/me/labels",
        json={
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    )
    return created["id"]


def mark_processed(session, msg_id: str, label_id: str, mark_read: bool = False):
    remove = ["UNREAD"] if mark_read else []
    _api(
        session,
        "POST",
        f"/users/me/messages/{msg_id}/modify",
        json={"addLabelIds": [label_id], "removeLabelIds": remove},
    )


def send_reply(session, parsed: dict, body_text: str, from_addr: str = "me"):
    """在原邮件线程内回复原发件人。"""
    subject = parsed.get("subject", "")
    if subject and not subject.lower().startswith("re:"):
        subject = "Re: " + subject

    signature = (config.REPLY_SIGNATURE or "").strip()
    if signature:
        body = body_text.rstrip()
        if not body.endswith(signature):
            body_text = body + "\n\n" + signature
        else:
            body_text = body

    mime = MIMEText(body_text, "plain", "utf-8")
    mime["To"] = parsed.get("from_email", "")
    mime["Subject"] = subject
    if from_addr and from_addr != "me":
        mime["From"] = from_addr

    orig_msg_id = parsed.get("message_id_header", "")
    if orig_msg_id:
        mime["In-Reply-To"] = orig_msg_id
        refs = parsed.get("references_header", "")
        mime["References"] = (refs + " " + orig_msg_id).strip() if refs else orig_msg_id

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
    payload = {"raw": raw}
    if parsed.get("thread_id"):
        payload["threadId"] = parsed["thread_id"]

    return _api(session, "POST", "/users/me/messages/send", json=payload)
