"""半自动发送：在飞书把状态改成「待发送」后，本脚本真正发邮件。

操作步骤见项目根目录《使用说明.md》。
"""
import sys

import feishu_client as fc
import gmail_client
import mail_index
from email_parser import parse_message


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


def run():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    service = gmail_client.get_service()
    feishu = fc.FeishuClient()

    records = feishu.search_by_status(fc.STATUS_TO_SEND)
    print(f"待发送记录：{len(records)} 条。")

    sent, skipped, failed = 0, 0, 0
    for rec in records:
        record_id = rec.get("record_id")
        fields = rec.get("fields", {})
        reply_body = _field_text(fields.get(fc.F_REPLY)).strip()
        mapped = mail_index.get_by_record(record_id)
        msg_id = mapped.get("msg_id", "")

        try:
            if not msg_id:
                print(f"  [跳过] {record_id}：本地没有对应邮件索引（旧数据需重新 ingest）。")
                skipped += 1
                continue
            if not reply_body:
                print(f"  [跳过] {record_id}：建议回复为空，请先在飞书填写后再改成待发送。")
                skipped += 1
                continue

            raw = gmail_client.get_message(service, msg_id)
            parsed = parse_message(raw)
            gmail_client.send_reply(service, parsed, reply_body)
            feishu.update_record(record_id, {fc.F_STATUS: fc.STATUS_SENT})
            print(f"  已回复：{(parsed.get('subject') or '')[:50]} -> {parsed.get('from_email')}")
            sent += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [失败] {record_id}: {e}")

    print(f"完成：已发送 {sent}，跳过 {skipped}，失败 {failed}。")


if __name__ == "__main__":
    run()
