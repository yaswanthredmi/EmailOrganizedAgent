"""主管道：未读 + 星标邮件 → 三分类 + 起草 → 飞书（未读会勾选「未读」）。

用法：
  python src/ingest.py
  set FORCE_REPROCESS=1 再跑：对已有邮件用新模型重分类/重起草
"""
import os
from datetime import datetime, timezone

import ai_summarizer
import config
import feishu_client as fc
import gmail_client
import mail_index
from email_parser import parse_message


def _to_ms(value: str) -> int | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def _status_for(category: str) -> str:
    if category == fc.CAT_ARCHIVE:
        return fc.STATUS_NEW_ARCHIVE  # 新归档：你一眼能看出是新来的，看完改成「完成」
    if category == fc.CAT_REVIEW:
        return fc.STATUS_REVIEW
    return fc.STATUS_TODO


def _with_signature(reply: str) -> str:
    """建议回复末尾按 .env 的 REPLY_SIGNATURE 自动附加签名。"""
    reply = (reply or "").rstrip()
    if not reply:
        return ""
    sig = (config.REPLY_SIGNATURE or "").strip()
    if not sig:
        return reply
    # 已包含签名则不重复
    if reply.endswith(sig) or reply.lower().endswith(sig.lower()):
        return reply
    return reply + "\n\n" + sig


def _build_fields(parsed: dict, ai: dict, is_unread: bool = False) -> dict:
    fields = {
        fc.F_CATEGORY: ai["category"],
        fc.F_SUMMARY: ai["summary"],
        fc.F_FROM_NAME: ai.get("from_name")
        or parsed.get("from_name", "")
        or parsed.get("from_email", ""),
        fc.F_WRITE_TARGET: ai["write_target"],
        fc.F_WRITE_ANGLE: ai["write_angle"],
        fc.F_LANGUAGE: ai["language"],
        fc.F_CONTEXT: ai["context"],
        fc.F_TODO: ai["todo"],
        fc.F_THEME: ai["theme"],
        fc.F_RELEVANCE: ai["relevance"],
        fc.F_REPLY: _with_signature(ai["suggested_reply"]),
        fc.F_STATUS: _status_for(ai["category"]),
        fc.F_REMIND: fc.REMIND_NONE,
        fc.F_UNREAD: bool(is_unread),
    }
    date_ms = _to_ms(parsed.get("date_iso", ""))
    if date_ms is not None:
        fields[fc.F_DATE] = date_ms
    deadline_ms = _to_ms(ai.get("deadline", ""))
    if deadline_ms is not None:
        fields[fc.F_DEADLINE] = deadline_ms
        # 有 DDL：入库时就给出提醒档位（remind.py 会再刷新）
        try:
            from datetime import date as _date
            from remind import _remind_label

            ddl = datetime.utcfromtimestamp(deadline_ms / 1000).date()
            fields[fc.F_REMIND] = _remind_label(ddl, _date.today(), int(getattr(config, "REMIND_SOON_DAYS", 3) or 3))
        except Exception:
            fields[fc.F_REMIND] = fc.REMIND_SOON
    return fields


def run():
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    force = os.getenv("FORCE_REPROCESS", "").lower() in ("1", "true", "yes")
    config.require("OPENAI_API_KEY")
    service = gmail_client.get_service()
    feishu = fc.FeishuClient()
    label_id = gmail_client.get_or_create_label(service, config.GMAIL_PROCESSED_LABEL)

    messages = gmail_client.list_messages(service, config.GMAIL_QUERY, config.GMAIL_MAX_RESULTS)
    print(f"查询 '{config.GMAIL_QUERY}' 命中 {len(messages)} 封" + ("（强制重处理）" if force else ""))

    processed, skipped, failed, updated = 0, 0, 0, 0
    for m in messages:
        msg_id = m["id"]
        try:
            existing = mail_index._load().get("by_msg_id", {}).get(msg_id)  # noqa: SLF001
            if existing and not force:
                skipped += 1
                continue

            raw = gmail_client.get_message(service, msg_id)
            parsed = parse_message(raw)
            is_unread = "UNREAD" in (raw.get("labelIds") or [])
            subject = (parsed.get("subject") or "(无主题)").encode("utf-8", "replace").decode("utf-8")
            flag = "未读" if is_unread else "星标"
            print(f"  处理[{flag}]：{subject[:50]}  <- {parsed.get('from_name')}")

            ai = ai_summarizer.summarize(parsed)
            fields = _build_fields(parsed, ai, is_unread=is_unread)
            print(f"    → {ai['category']} | {ai['write_target']} | {ai['write_angle']} | {ai['language']}")

            if existing and force:
                record_id = existing.get("record_id", "")
                if record_id:
                    # 读取当前状态：发送流程中的不改状态，其余按分类同步
                    safe_fields = dict(fields)
                    try:
                        cur_items = feishu.search_by_status(fc.STATUS_TO_SEND)
                        to_send_ids = {x.get("record_id") for x in cur_items}
                    except Exception:
                        to_send_ids = set()
                    # 更稳妥：若建议回复非空且用户可能已改状态，仍先去掉 STATUS，再单独按分类写回（非待发送/已发送时）
                    new_status = safe_fields.pop(fc.F_STATUS, None)
                    feishu.update_record(record_id, safe_fields)
                    if new_status and record_id not in to_send_ids:
                        feishu.update_record(record_id, {fc.F_STATUS: new_status})
                    updated += 1
                else:
                    result = feishu.add_record(fields)
                    record_id = (result.get("record") or {}).get("record_id", "")
                    if record_id:
                        mail_index.bind(record_id, parsed["msg_id"], parsed.get("thread_id", ""))
                    processed += 1
            else:
                result = feishu.add_record(fields)
                record_id = (result.get("record") or {}).get("record_id", "")
                if record_id:
                    mail_index.bind(record_id, parsed.get("msg_id", ""), parsed.get("thread_id", ""))
                processed += 1

            gmail_client.mark_processed(service, msg_id, label_id, config.GMAIL_MARK_READ)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [失败] {msg_id}: {e}")

    print(
        f"完成：新增 {processed}，更新 {updated}，跳过 {skipped}，失败 {failed}。"
    )


if __name__ == "__main__":
    run()
