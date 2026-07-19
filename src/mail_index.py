"""本地邮件索引：把 Gmail msg_id/thread_id 存在本地，飞书表格里不再显示。"""
import json
from pathlib import Path

import config

INDEX_FILE = config.PROJECT_ROOT / "state" / "mail_index.json"


def _load() -> dict:
    if not INDEX_FILE.exists():
        return {"by_msg_id": {}, "by_record_id": {}}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"by_msg_id": {}, "by_record_id": {}}


def _save(data: dict) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def has_msg(msg_id: str) -> bool:
    return bool(msg_id) and msg_id in _load().get("by_msg_id", {})


def bind(record_id: str, msg_id: str, thread_id: str = "") -> None:
    data = _load()
    data.setdefault("by_msg_id", {})[msg_id] = {
        "record_id": record_id,
        "thread_id": thread_id,
    }
    data.setdefault("by_record_id", {})[record_id] = {
        "msg_id": msg_id,
        "thread_id": thread_id,
    }
    _save(data)


def get_by_record(record_id: str) -> dict:
    return _load().get("by_record_id", {}).get(record_id, {})
