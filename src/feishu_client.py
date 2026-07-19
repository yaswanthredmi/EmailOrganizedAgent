"""飞书多维表格：三分类工作流 + 邮件起草字段（写作对象/角度/语言/Context）。"""
import time

import requests

import config

# ---- 可见字段 ----
F_CATEGORY = "分类"
F_SUMMARY = "邮件概述"
F_DATE = "Date"
F_FROM_NAME = "对方名字"
F_WRITE_TARGET = "写作对象"
F_WRITE_ANGLE = "写作角度"
F_LANGUAGE = "语言"
F_CONTEXT = "Context"
F_TODO = "待办事项"
F_DEADLINE = "DDL"
F_THEME = "主题标签"
F_RELEVANCE = "相关性"
F_REPLY = "建议回复"
F_STATUS = "状态"
F_REMIND = "提醒"
F_UNREAD = "未读"

# 三分类（邮件爆炸工作流）
CAT_RESPOND = "要回复"
CAT_ARCHIVE = "要归档"
CAT_REVIEW = "要查阅"
CATEGORIES = [CAT_RESPOND, CAT_ARCHIVE, CAT_REVIEW]

WRITE_TARGETS = ["同级同事", "客户", "leader", "外部协同方", "学校/机构", "其他"]
WRITE_ANGLES = ["信息询问", "进度汇报", "Cold Reach Out", "通知确认", "感谢", "其他"]
LANGUAGES = ["English", "中文"]
THEMES = ["新功能", "设计", "技术分享", "行政通知", "求职", "课程", "其他"]

STATUS_TODO = "待办"
STATUS_TO_SEND = "待发送"
STATUS_SENT = "已发送"
STATUS_NEW_ARCHIVE = "新归档"
STATUS_ARCHIVED = "已归档"
STATUS_REVIEW = "待查阅"
STATUS_DONE = "完成"
STATUS_PENDING = STATUS_TODO

REMIND_NONE = "无"
REMIND_SOON = "即将到期"
REMIND_TODAY = "今日到期"
REMIND_OVERDUE = "已过期"

FIELD_DEFS = [
    (F_CATEGORY, 3, {"options": CATEGORIES}),
    (F_SUMMARY, 1, None),
    (F_DATE, 5, {"date_formatter": "yyyy/MM/dd"}),
    (F_FROM_NAME, 1, None),
    (F_WRITE_TARGET, 3, {"options": WRITE_TARGETS}),
    (F_WRITE_ANGLE, 3, {"options": WRITE_ANGLES}),
    (F_LANGUAGE, 3, {"options": LANGUAGES}),
    (F_CONTEXT, 1, None),
    (F_TODO, 1, None),
    (F_DEADLINE, 5, {"date_formatter": "yyyy/MM/dd"}),
    (F_THEME, 3, {"options": THEMES}),
    (F_RELEVANCE, 1, None),
    (F_REPLY, 1, None),
    (
        F_STATUS,
        3,
{
                "options": [
                    STATUS_TODO,
                    STATUS_TO_SEND,
                    STATUS_SENT,
                    STATUS_NEW_ARCHIVE,
                    STATUS_ARCHIVED,
                    STATUS_REVIEW,
                    STATUS_DONE,
                ]
            },
    ),
    (F_REMIND, 3, {"options": [REMIND_NONE, REMIND_SOON, REMIND_TODAY, REMIND_OVERDUE]}),
    (F_UNREAD, 7, None),  # 复选框：来自未读收件箱的自动入库
]

FIELDS_TO_DELETE = {"_邮件ID", "_会话ID", "文本", "单选", "日期", "附件", "GmailMsgId", "GmailThreadId"}


class FeishuClient:
    def __init__(self):
        config.require("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_APP_TOKEN", "FEISHU_TABLE_ID")
        self.base = config.FEISHU_BASE_URL
        self.app_token = config.FEISHU_APP_TOKEN
        self.table_id = config.FEISHU_TABLE_ID
        self._token = None
        self._token_exp = 0

    def _tenant_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        url = f"{self.base}/open-apis/auth/v3/tenant_access_token/internal"
        resp = requests.post(
            url,
            json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
            timeout=20,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败：{data}")
        self._token = data["tenant_access_token"]
        self._token_exp = time.time() + data.get("expire", 7200)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._tenant_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _bitable_url(self, suffix: str) -> str:
        return f"{self.base}/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/{suffix}"

    def _check(self, data: dict, action: str) -> dict:
        if data.get("code") != 0:
            raise RuntimeError(f"飞书接口调用失败({action})：{data}")
        return data.get("data", {})

    def list_fields(self) -> list:
        url = self._bitable_url("fields")
        resp = requests.get(url, headers=self._headers(), params={"page_size": 100}, timeout=20)
        return self._check(resp.json(), "list_fields").get("items", [])

    def create_field(self, field_name: str, field_type: int, property_: dict | None):
        url = self._bitable_url("fields")
        body = {"field_name": field_name, "type": field_type}
        if property_:
            if "options" in property_:
                body["property"] = {"options": [{"name": o} for o in property_["options"]]}
            else:
                body["property"] = property_
        resp = requests.post(url, headers=self._headers(), json=body, timeout=20)
        return self._check(resp.json(), f"create_field:{field_name}")

    def delete_field(self, field_id: str):
        url = self._bitable_url(f"fields/{field_id}")
        resp = requests.delete(url, headers=self._headers(), timeout=20)
        return self._check(resp.json(), f"delete_field:{field_id}")

    def ensure_fields(self) -> list:
        existing = {f.get("field_name") for f in self.list_fields()}
        created = []
        for name, ftype, prop in FIELD_DEFS:
            if name not in existing:
                self.create_field(name, ftype, prop)
                created.append(name)
        return created

    def cleanup_extra_fields(self) -> list:
        deleted = []
        for f in self.list_fields():
            name = f.get("field_name", "")
            if name not in FIELDS_TO_DELETE or f.get("is_primary"):
                continue
            try:
                self.delete_field(f["field_id"])
                deleted.append(name)
            except RuntimeError as e:
                if "Primary Field" in str(e):
                    continue
                raise
        return deleted

    def set_row_height(self, height: str = "high") -> None:
        url = f"{self.base}/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/views"
        resp = requests.get(url, headers=self._headers(), timeout=20)
        views = self._check(resp.json(), "list_views").get("items", [])
        if not views:
            return
        view_id = views[0]["view_id"]
        patch_url = (
            f"{self.base}/open-apis/bitable/v1/apps/{self.app_token}"
            f"/tables/{self.table_id}/views/{view_id}"
        )
        resp = requests.patch(
            patch_url, headers=self._headers(), json={"property": {"row_height": height}}, timeout=20
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"设置行高失败：{data}")

    def add_record(self, fields: dict) -> dict:
        url = self._bitable_url("records")
        resp = requests.post(url, headers=self._headers(), json={"fields": fields}, timeout=20)
        return self._check(resp.json(), "add_record")

    def update_record(self, record_id: str, fields: dict) -> dict:
        url = self._bitable_url(f"records/{record_id}")
        resp = requests.put(url, headers=self._headers(), json={"fields": fields}, timeout=20)
        return self._check(resp.json(), "update_record")

    def search_by_status(self, status: str, page_size: int = 50) -> list:
        url = self._bitable_url("records/search")
        body = {
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {"field_name": F_STATUS, "operator": "is", "value": [status]}
                ],
            }
        }
        resp = requests.post(
            url, headers=self._headers(), json=body, params={"page_size": page_size}, timeout=20
        )
        return self._check(resp.json(), "search_by_status").get("items", [])

    def list_records(self, page_size: int = 100) -> list:
        url = self._bitable_url("records/search")
        items, page_token = [], None
        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            resp = requests.post(url, headers=self._headers(), json={}, params=params, timeout=30)
            data = self._check(resp.json(), "list_records")
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        return items

    def send_webhook(self, text: str) -> bool:
        webhook = getattr(config, "FEISHU_WEBHOOK_URL", "") or ""
        if not webhook:
            return False
        resp = requests.post(
            webhook,
            json={"msg_type": "text", "content": {"text": text}},
            timeout=20,
        )
        return resp.status_code == 200 and resp.json().get("code", 0) == 0
