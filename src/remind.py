"""DDL 提醒：扫描表格里有截止日期的待办，更新「提醒」字段，并可选推送到飞书机器人。

用法： python src/remind.py
建议用 Windows 计划任务每天早上跑一次。
"""
from datetime import date, datetime, timezone

import config
import feishu_client as fc


def _field_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            seg.get("text", "") if isinstance(seg, dict) else str(seg) for seg in value
        )
    if isinstance(value, dict):
        return value.get("text", "")
    return str(value)


def _deadline_date(value) -> date | None:
    """飞书日期字段通常是毫秒时间戳。"""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
        if isinstance(value, str) and value.isdigit():
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date()
    except (ValueError, OSError, OverflowError):
        return None
    return None


def _remind_label(deadline: date, today: date, soon_days: int) -> str:
    delta = (deadline - today).days
    if delta < 0:
        return fc.REMIND_OVERDUE
    if delta == 0:
        return fc.REMIND_TODAY
    if delta <= soon_days:
        return fc.REMIND_SOON
    return fc.REMIND_NONE


def run():
    soon_days = int(getattr(config, "REMIND_SOON_DAYS", 3) or 3)
    feishu = fc.FeishuClient()
    today = date.today()
    records = feishu.list_records()

    updated, alerts = 0, []
    for rec in records:
        record_id = rec.get("record_id")
        fields = rec.get("fields", {})
        status = _field_text(fields.get(fc.F_STATUS))
        if status in (fc.STATUS_DONE, fc.STATUS_ARCHIVED, fc.STATUS_SENT):
            continue

        ddl = _deadline_date(fields.get(fc.F_DEADLINE))
        if not ddl:
            continue

        label = _remind_label(ddl, today, soon_days)
        current = _field_text(fields.get(fc.F_REMIND)) or fc.REMIND_NONE
        if label != current:
            feishu.update_record(record_id, {fc.F_REMIND: label})
            updated += 1

        if label in (fc.REMIND_TODAY, fc.REMIND_OVERDUE, fc.REMIND_SOON):
            summary = _field_text(fields.get(fc.F_SUMMARY))
            todo = _field_text(fields.get(fc.F_TODO))
            who = _field_text(fields.get(fc.F_FROM_NAME))
            alerts.append(
                f"[{label}] {ddl.isoformat()} | {summary} | 对方:{who} | 待办:{todo}"
            )

    print(f"扫描 {len(records)} 条，更新提醒字段 {updated} 条，需关注 {len(alerts)} 条。")
    for line in alerts:
        print(" ", line)

    if alerts:
        text = "📬 邮件 DDL 提醒\n" + "\n".join(alerts)
        if feishu.send_webhook(text):
            print("已推送到飞书机器人 webhook。")
        else:
            print("未配置 FEISHU_WEBHOOK_URL，仅更新了表格「提醒」字段（可在飞书里筛选查看）。")


if __name__ == "__main__":
    run()
