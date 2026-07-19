"""配置体检：填完 .env 后运行，逐项校验密钥与连通性。

用法： python src/doctor.py
不会触发 Gmail 首次授权（那一步请直接跑 ingest.py），只做非交互式检查。
"""
import json

import config


def _ok(msg):
    print(f"  [OK]   {msg}")


def _warn(msg):
    print(f"  [WARN] {msg}")


def _fail(msg):
    print(f"  [FAIL] {msg}")


def check_gmail() -> bool:
    print("Gmail:")
    ok = True
    if not config.GMAIL_CREDENTIALS_FILE.exists():
        _fail(f"找不到 {config.GMAIL_CREDENTIALS_FILE}（从 GCP 拿 OAuth 客户端后放这里）")
        return False
    try:
        data = json.loads(config.GMAIL_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        node = data.get("installed") or data.get("web") or {}
        if node.get("client_id"):
            _ok(f"credentials.json 有效（client_id: ...{node['client_id'][-12:]}）")
        else:
            _fail("credentials.json 缺少 client_id，格式可能不对（应为『桌面应用』类型）")
            ok = False
    except (json.JSONDecodeError, OSError) as e:
        _fail(f"credentials.json 读取失败：{e}")
        return False

    if config.GMAIL_TOKEN_FILE.exists():
        try:
            from google.oauth2.credentials import Credentials
            from gmail_client import SCOPES
            creds = Credentials.from_authorized_user_file(str(config.GMAIL_TOKEN_FILE), SCOPES)
            _ok("已有 token.json" + ("（有效）" if creds and creds.valid else "（将自动刷新）"))
        except Exception as e:  # noqa: BLE001
            _warn(f"token.json 存在但无法读取：{e}（首次跑 ingest.py 会重新授权）")
    else:
        _warn("尚无 token.json —— 首次运行 ingest.py 会弹浏览器授权（正常）")
    return ok


def check_newapi() -> bool:
    print("Gemini / AI:")
    if not config.OPENAI_API_KEY:
        _fail("OPENAI_API_KEY 未填")
        return False
    try:
        import requests

        base = (config.OPENAI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        url = f"{base}/models/{config.OPENAI_MODEL}:generateContent"
        resp = requests.post(
            url,
            params={"key": config.OPENAI_API_KEY},
            json={
                "contents": [{"parts": [{"text": "ping，只回复 pong"}]}],
                "generationConfig": {"maxOutputTokens": 8, "temperature": 0},
            },
            timeout=30,
        )
        data = resp.json()
        if resp.status_code != 200:
            _fail(f"调用失败 ({resp.status_code}): {data}")
            return False
        text = "".join(
            p.get("text", "")
            for p in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        )
        _ok(f"连通成功，模型 {config.OPENAI_MODEL} 返回：{text!r}")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"调用失败：{e}")
        return False


def check_feishu() -> bool:
    print("飞书:")
    for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_APP_TOKEN", "FEISHU_TABLE_ID"):
        if not getattr(config, name):
            _fail(f"{name} 未填")
            return False
    try:
        from feishu_client import FeishuClient
        client = FeishuClient()
        client._tenant_token()  # noqa: SLF001 主动触发一次鉴权
        _ok("拿到 tenant_access_token")
        fields = client.list_fields()
        names = [f.get("field_name") for f in fields]
        _ok(f"读到表格字段 {len(names)} 个：{names}")
        return True
    except Exception as e:  # noqa: BLE001
        _fail(f"访问多维表格失败：{e}（检查 App Token/Table ID，并确认应用已被加为表格协作者、已开通 bitable 权限）")
        return False


def main():
    print("=" * 56)
    print("配置体检")
    print("=" * 56)
    results = {
        "Gmail": check_gmail(),
        "New API": check_newapi(),
        "飞书": check_feishu(),
    }
    print("-" * 56)
    for name, ok in results.items():
        print(f"  {name}: {'通过' if ok else '未通过'}")
    if all(results.values()):
        print("\n全部通过！接下来：python src\\setup_feishu_table.py  然后  python src\\ingest.py")
    else:
        print("\n还有项未通过，按上面提示补齐后再跑一次 doctor。")


if __name__ == "__main__":
    main()
