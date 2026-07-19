"""集中读取配置。所有路径都相对项目根目录解析。"""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env", override=True)


def _path(value: str) -> Path:
    """把可能是相对路径的配置值解析成绝对路径。"""
    p = Path(value)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


# ---- Gmail ----
GMAIL_CREDENTIALS_FILE = _path(os.getenv("GMAIL_CREDENTIALS_FILE", "config/credentials.json"))
GMAIL_TOKEN_FILE = _path(os.getenv("GMAIL_TOKEN_FILE", "config/token.json"))
GMAIL_QUERY = os.getenv("GMAIL_QUERY", "is:unread OR is:starred")
GMAIL_MAX_RESULTS = int(os.getenv("GMAIL_MAX_RESULTS", "50"))
GMAIL_PROCESSED_LABEL = os.getenv("GMAIL_PROCESSED_LABEL", "已处理")
GMAIL_MARK_READ = _bool(os.getenv("GMAIL_MARK_READ", "false"))

# ---- New API / Gemini ----
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# ---- 飞书 ----
FEISHU_BASE_URL = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_APP_TOKEN = os.getenv("FEISHU_APP_TOKEN", "")
FEISHU_TABLE_ID = os.getenv("FEISHU_TABLE_ID", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
REMIND_SOON_DAYS = int(os.getenv("REMIND_SOON_DAYS", "3"))

# ---- 回复 ----
REPLY_SIGNATURE = os.getenv("REPLY_SIGNATURE", "")

# ---- 可选：学校 M365 兜底 ----
GRAPH_ENABLED = _bool(os.getenv("GRAPH_ENABLED", "false"))
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "")
GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "common")
GRAPH_TOKEN_FILE = _path(os.getenv("GRAPH_TOKEN_FILE", "config/graph_token.json"))
GRAPH_MAX_RESULTS = int(os.getenv("GRAPH_MAX_RESULTS", "10"))


def require(*names: str) -> None:
    """启动前校验必填项，缺失时抛出清晰错误。"""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(
            "缺少必要配置：" + ", ".join(missing) + "。请检查 .env 文件（参考 .env.example）。"
        )
