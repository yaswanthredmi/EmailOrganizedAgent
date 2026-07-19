"""可选兜底管道：从学校 M365(Graph) 读未读 -> AI 总结 -> 写飞书。

用法： python src/ingest_graph.py
仅当 .env 中 GRAPH_ENABLED=true 时才会运行。
"""
import ai_summarizer
import config
import feishu_client as fc
import graph_client
from ingest import _build_fields


def run():
    if not config.GRAPH_ENABLED:
        print("GRAPH_ENABLED=false，跳过学校 M365 兜底管道。")
        return

    config.require("OPENAI_API_KEY", "GRAPH_CLIENT_ID")
    feishu = fc.FeishuClient()

    emails = graph_client.list_unread()
    print(f"学校 M365 未读邮件：{len(emails)} 封。")

    processed, skipped, failed = 0, 0, 0
    for parsed in emails:
        msg_id = parsed["msg_id"]
        try:
            if feishu.record_exists(msg_id):
                graph_client.mark_read(parsed["graph_id"])
                skipped += 1
                continue

            print(f"  处理：{parsed.get('subject', '(无主题)')[:50]}  <- {parsed.get('from_email')}")
            ai = ai_summarizer.summarize(parsed)
            feishu.add_record(_build_fields(parsed, ai))
            graph_client.mark_read(parsed["graph_id"])
            processed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [失败] {msg_id}: {e}")

    print(f"完成：新增 {processed}，跳过 {skipped}，失败 {failed}。")


if __name__ == "__main__":
    run()
