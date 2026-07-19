# EmailOrganizedAgent

开源的邮件整理 / 回复 Agent：自动读取 Gmail → AI 三分类与起草 → 写入飞书多维表格；你在表格里确认后，再半自动发送回复。

灵感来自「邮件爆炸」工作流：**每天只盯「要回复」**，归档直接忽略，查阅看摘要即可。

## 功能

- **自动拉取**：未读 / 星标邮件（Gmail API）
- **三分类**：要回复 / 要归档 / 要查阅（可自定义 `config/focus_rules.md`）
- **起草字段**：写作对象、写作角度、语言、Context、建议回复
- **DDL 提醒**：有截止日期自动标记即将到期 / 今日到期 / 已过期
- **半自动发送**：只有你在飞书把状态改成「待发送」后，才真正发信（默认不自动发）
- **可选**：Microsoft Graph 读取学校 M365 邮箱（转发被禁时）

## 架构

```
Gmail (未读/星标)
    → ingest.py 解析
    → AI（Gemini 原生 或 OpenAI 兼容网关）
    → 飞书多维表格（分类 / 起草 / DDL）
         ↓ 你把状态改为「待发送」
    → send.py 线程内回复
```

## 快速开始

### 1. 准备凭证（网页端）

1. **Gmail**：Google Cloud 启用 Gmail API，创建「桌面应用」OAuth 客户端，下载 JSON 为 `config/credentials.json`
2. **飞书**：开放平台创建企业自建应用，开通多维表格权限，把应用加为表格协作者；从 URL 取 app_token / table_id
3. **AI**：Gemini API Key，或任意 OpenAI 兼容 `base_url` + `key`

### 2. 安装

```powershell
git clone https://github.com/<YOUR_GITHUB_USERNAME>/EmailOrganizedAgent.git
cd EmailOrganizedAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，填入你的配置（切勿提交 .env）
```

### 3. 初始化并运行

```powershell
python src\setup_feishu_table.py   # 自动创建字段
python src\doctor.py               # 体检连通性
python src\ingest.py               # 拉邮件 → 分类起草 → 写飞书
# 在飞书把状态改为「待发送」后：
python src\send.py
python src\remind.py               # DDL 提醒
```

### 4. Windows 计划任务（可选）

可用 `run_ingest.bat` / `run_remind.bat`。建议拉取间隔不要太密（例如每 8 小时）。**发送建议手动触发**，避免误发。

## 配置说明

见 [`.env.example`](.env.example)。敏感文件已被 `.gitignore` 忽略：

- `.env`
- `config/credentials.json` / `config/token.json`
- `state/`（本地邮件索引）

分类规则模板：复制 `config/focus_rules.example.md` → `config/focus_rules.md` 后按自己的关注点修改。

## 安全

- **不要**把 API Key、App Secret、OAuth token、个人邮箱、飞书表格链接提交到 Git
- 开源前用 `git status` / `git secrets` 再扫一遍
- 本仓库示例与默认配置均为占位符

## License

MIT
