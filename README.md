# Douyin Favorites to Obsidian

把指定抖音收藏夹里的新增视频和图文，定时整理为「核心观点 + 完整逐字稿」，写入本机 Obsidian Vault。

> 这是一个本地优先项目。登录 Cookie、API Key、视频缓存和 Obsidian 内容都留在用户自己的电脑上。

## 能做什么

- 按名称监听一个指定的抖音收藏夹，首次验证时自动识别稳定收藏夹 ID。
- 只处理新增内容，以抖音内容 ID 增量去重。
- 视频通过 `yt-dlp + faster-whisper` 生成带时间戳逐字稿。
- 图文通过抖音详情接口提取正文，并保留浏览器渲染兜底。
- 可选 OpenAI 兼容接口，自动生成 3-6 条中文核心观点。
- 将笔记写入任意 Obsidian Vault 子目录。
- 支持每天、工作日、每周、每 N 小时或自定义 cron 周期。
- 失败项不会写入已处理状态，下次会继续重试。

## 输出格式

文件名：`内容ID_标题.md`

```markdown
---
source: https://www.douyin.com/video/...
video_id: "..."
type: video
title: 标题
clipped: 2026-06-14
tags: [douyin, AI学习]
---

# 标题

> 来源：...

## 1. 核心观点

- ...

## 2. 逐字稿

[00:00] ...
```

项目不会生成“金句摘要”。

## 系统要求

- macOS 或 Linux
- Python 3.10+
- Node.js 18+
- Google Chrome，或由 Playwright 安装的 Chromium
- 本机 Obsidian Vault

Windows 用户可以手动运行流水线，但当前自动安装器使用 `cron`，需要自行改用任务计划程序。

## 快速开始

```bash
git clone https://github.com/CelesteZheng09/douyin-obsidian-sync.git
cd douyin-obsidian-sync
bash scripts/bootstrap.sh
source .venv/bin/activate
python -m pipeline.setup
```

配置向导会依次询问：

1. 抖音收藏夹名称；
2. Obsidian Vault 绝对路径；
3. Vault 内目标子目录；
4. 推送周期与时间；
5. 核心观点生成模式；
6. 是否立即扫码登录、验证收藏夹和安装定时任务。

向导不会把 Cookie 或 API Key 写入 Git 可跟踪文件。

## 手动安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run install-browser
cp config.example.yaml config.yaml
```

如需自动生成核心观点：

```bash
pip install -r requirements-openai.txt
```

然后运行配置、登录与验证：

```bash
python -m pipeline.setup
# 或分别执行
python -m pipeline.collector --login
python -m pipeline.collector --headful
```

## 配置

真实配置位于 `config.yaml`，已被 `.gitignore` 排除。主要字段：

```yaml
douyin:
  favorite_folder_name: "AI学习"
  favorite_folder_id: ""  # 可留空，配置向导自动识别

obsidian:
  vault_path: "/absolute/path/to/Obsidian Vault"
  notes_subdir: "_LLM/sources/web_clips/AI学习"
  tags: ["douyin", "AI学习"]

runtime:
  schedule: "0 10 * * *"  # 每天 10:00
```

周期示例：

| 需求 | cron |
|---|---|
| 每天 10:00 | `0 10 * * *` |
| 工作日 18:30 | `30 18 * * 1-5` |
| 每周一 09:00 | `0 9 * * 1` |
| 每 6 小时 | `0 */6 * * *` |

## 核心观点模式

### OpenAI 兼容接口

```yaml
summarize:
  mode: "openai"
  openai_base_url: "https://api.openai.com/v1"
  openai_model: "gpt-4o-mini"
```

配置向导可以把 `OPENAI_API_KEY` 保存到本机 `secrets/runtime.env`。该文件权限为 `0600`，且整个 `secrets/` 目录不会提交 Git。也可以自行设置环境变量。

### Manual

```yaml
summarize:
  mode: "manual"
```

这种模式会生成完整逐字稿，但在核心观点处保留占位符。适合由 Codex Skill 或其他本地 LLM 后处理。

## 运行与定时

手动运行：

```bash
python -m pipeline.run
```

管理定时任务：

```bash
python -m pipeline.scheduler install
python -m pipeline.scheduler status
python -m pipeline.scheduler uninstall
```

运行日志写入项目根目录的 `run.log`。

## Codex Skill

仓库包含 [`skills/douyin-obsidian-sync`](skills/douyin-obsidian-sync)，可复制或链接到个人 Skills 目录：

```bash
cp -R skills/douyin-obsidian-sync "${CODEX_HOME:-$HOME/.codex}/skills/"
```

之后可以对 Codex 说：

```text
使用 $douyin-obsidian-sync，帮我把“AI学习”收藏夹每天 10:00 同步到 Obsidian 的 _LLM/sources/AI。
```

## 数据与隐私

以下内容默认不会进入 Git：

- `config.yaml`
- `secrets/`：抖音登录态、yt-dlp Cookie、API Key
- `state/`：已处理 ID
- `.work/`：视频和音频临时文件
- `.models/`：Whisper 模型
- `run.log`

不要把 `secrets/`、真实 `config.yaml` 或 Obsidian 私人内容提交到公开仓库。

## 已知限制

- 抖音登录态会失效，届时重新运行 `python -m pipeline.collector --login`。
- 抖音前端或接口改版可能导致收藏夹定位失效。
- 无语音视频无法仅凭 ASR 产生逐字稿；当前不会对画面自动做 OCR 或视觉理解。
- 首次运行需要下载 Whisper 模型，`small` 模型约数百 MB。
- 请自行确认自动化访问、下载和保存内容符合所在地法律、平台条款及内容版权要求。

## 开发

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall -q pipeline
```

架构与故障排查见 [docs/architecture.md](docs/architecture.md) 和 [docs/troubleshooting.md](docs/troubleshooting.md)。

## License

[MIT](LICENSE)
