"""初始化：建字段、删多余列、调高行高（自动换行更易读）。"""
from feishu_client import FeishuClient


def main():
    client = FeishuClient()
    print("检查并创建字段...")
    created = client.ensure_fields()
    print("新建字段：" + (", ".join(created) if created else "无"))

    print("删除多余列（邮件ID/默认空列）...")
    deleted = client.cleanup_extra_fields()
    print("已删除：" + (", ".join(deleted) if deleted else "无"))

    print("调高表格行高，方便概述/待办换行显示...")
    try:
        client.set_row_height("high")
        print("行高已设为 high。")
    except Exception as e:  # noqa: BLE001
        print(f"行高 API 设置失败（可在飞书视图里手动：视图设置→行高→高）：{e}")

    print("完成。")


if __name__ == "__main__":
    main()
