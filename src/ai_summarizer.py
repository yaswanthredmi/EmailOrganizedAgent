"""邮件三分类 + 起草字段提取（写作对象/角度/语言/Context/建议回复）。"""
import json
import re
from pathlib import Path

import requests

import config
import feishu_client as fc

SYSTEM_PROMPT = (
    "你是资深邮件秘书 Agent。只输出 JSON。"
    "严格按用户的 focus_rules 做三分类，并为「要回复」写好可发送草稿。"
)

USER_PROMPT_TEMPLATE = """你要处理一封邮件。先读「我的分类标准」，再输出 JSON。

======= 我的分类标准 =======
{focus_rules}
======= 标准结束 =======

返回 JSON（枚举必须用给定值）：
{{
  "category": "{cats} 三选一",
  "summary": "一句话概述（中文）",
  "from_name": "对方称呼/名字",
  "write_target": "{targets} 之一（自动判断收件人关系）",
  "write_angle": "{angles} 之一（这封回信/处理的写作角度）",
  "language": "{langs} 之一（回复应用的语言，通常跟原邮件一致）",
  "context": "小 context：背景要点 2-4 句，供起草回复用；可含项目/DDL/对方诉求",
  "todo": "我要做的事；可换行；没有则空字符串",
  "deadline": "YYYY-MM-DD 或空字符串（有 DDL 必填）",
  "theme": "{themes} 之一（仅要查阅时有意义，否则填其他）",
  "relevance": "若要查阅：为什么与我相关；其他分类可空",
  "needs_reply": true/false（要回复且需要写邮件时为 true；只需点链接/填表可为 false）",
  "suggested_reply": "needs_reply=true 时：按 write_target/write_angle/language/context 写完整可发送正文，署名用 .env 里的 REPLY_SIGNATURE（未配置则不署名）；否则空字符串"
}}

规则：
- 要归档：一般不写 suggested_reply，todo 可空
- 要查阅：填 theme + relevance + summary，通常不回信
- 要回复：必须填 write_target/write_angle/language/context；若需回信则 suggested_reply 必须是完整邮件正文，结尾按 REPLY_SIGNATURE 署名（未配置则不署名）

只返回 JSON。

发件人：{from_name} <{from_email}>
主题：{subject}
日期：{date}
正文：
{body}
"""


def _load_focus_rules() -> str:
    path = Path(config.PROJECT_ROOT) / "config" / "focus_rules.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "（未找到 focus_rules.md，请按常识：强相关要回复，无关归档，有长期价值查阅）"


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def _normalize_deadline(value: str) -> str:
    value = (value or "").strip()
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if not m:
        return ""
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _pick(value, allowed, fallback):
    return value if value in allowed else fallback


def _coerce(result: dict) -> dict:
    category = _pick(result.get("category"), fc.CATEGORIES, fc.CAT_REVIEW)
    needs_reply = bool(result.get("needs_reply", False)) and category == fc.CAT_RESPOND
    reply = str(result.get("suggested_reply", "")).strip()
    if not needs_reply:
        reply = ""
    else:
        sig = (getattr(config, "REPLY_SIGNATURE", None) or "").strip()
        if reply and sig and not reply.rstrip().endswith(sig):
            reply = reply.rstrip() + "\n\n" + sig
    return {
        "category": category,
        "summary": str(result.get("summary", "")).strip(),
        "from_name": str(result.get("from_name", "")).strip(),
        "write_target": _pick(result.get("write_target"), fc.WRITE_TARGETS, "其他"),
        "write_angle": _pick(result.get("write_angle"), fc.WRITE_ANGLES, "其他"),
        "language": _pick(result.get("language"), fc.LANGUAGES, "English"),
        "context": str(result.get("context", "")).strip(),
        "todo": str(result.get("todo", "")).strip(),
        "deadline": _normalize_deadline(str(result.get("deadline", ""))),
        "theme": _pick(result.get("theme"), fc.THEMES, "其他"),
        "relevance": str(result.get("relevance", "")).strip(),
        "needs_reply": needs_reply,
        "suggested_reply": reply,
    }


def _is_gemini() -> bool:
    base = (config.OPENAI_BASE_URL or "").lower()
    return "generativelanguage.googleapis.com" in base or base.rstrip("/").endswith("/v1beta")


def _call_gemini(prompt: str) -> str:
    config.require("OPENAI_API_KEY")
    base = config.OPENAI_BASE_URL.rstrip("/")
    if base.endswith("/openai"):
        base = base[: -len("/openai")]
    url = f"{base}/models/{config.OPENAI_MODEL}:generateContent"
    resp = requests.post(
        url,
        params={"key": config.OPENAI_API_KEY},
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=90,
    )
    data = resp.json()
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API 失败 ({resp.status_code}): {data}")
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def _call_openai_compatible(prompt: str) -> str:
    config.require("OPENAI_API_KEY", "OPENAI_BASE_URL")
    url = config.OPENAI_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENAI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(
        url, headers=headers, json={**payload, "response_format": {"type": "json_object"}}, timeout=90
    )
    if resp.status_code != 200:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
    data = resp.json()
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI 兼容 API 失败 ({resp.status_code}): {data}")
    return data["choices"][0]["message"]["content"] or "{}"


def summarize(parsed: dict, max_body_chars: int = 6000) -> dict:
    body = (parsed.get("body_text") or "")[:max_body_chars]
    prompt = USER_PROMPT_TEMPLATE.format(
        focus_rules=_load_focus_rules(),
        cats=" / ".join(fc.CATEGORIES),
        targets=" / ".join(fc.WRITE_TARGETS),
        angles=" / ".join(fc.WRITE_ANGLES),
        langs=" / ".join(fc.LANGUAGES),
        themes=" / ".join(fc.THEMES),
        from_name=parsed.get("from_name", ""),
        from_email=parsed.get("from_email", ""),
        subject=parsed.get("subject", ""),
        date=parsed.get("date_raw", ""),
        body=body,
    )
    content = _call_gemini(prompt) if _is_gemini() else _call_openai_compatible(prompt)
    try:
        data = _extract_json(content or "{}")
    except (json.JSONDecodeError, ValueError):
        data = {"summary": (content or "")[:200], "category": fc.CAT_REVIEW}
    return _coerce(data)
