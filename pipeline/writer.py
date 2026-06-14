"""
核心观点生成 + Obsidian 笔记写入。

按用户固化偏好：只产出「核心观点 + 完整逐字稿」，不做金句摘要。
"""
import os
from pathlib import Path

import yaml

from . import config
from .normalize import safe_filename


CORE_PROMPT = (
    "你是中文内容分析助手。请阅读下面的视频逐字稿，提炼这条视频的『核心观点』：\n"
    "- 用 3-6 条要点概括作者的主要论点与结论\n"
    "- 每条一句话，准确、不堆砌、不加入逐字稿里没有的信息\n"
    "- 只输出要点本身，不要前言后语\n\n逐字稿：\n{transcript}"
)


def make_core_points(transcript, cfg):
    s = cfg["summarize"]
    if s.get("mode") != "openai":
        return "_（核心观点待生成：config.summarize.mode 设为 manual，请在 Codex 端用 LLM 基于下方逐字稿补全）_"
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("summarize.mode=openai，但未设置 OPENAI_API_KEY")
    client = OpenAI(base_url=s["openai_base_url"],
                    api_key=api_key)
    # 逐字稿过长时截断喂入
    text = transcript[:12000]
    resp = client.chat.completions.create(
        model=s["openai_model"],
        messages=[{"role": "user",
                   "content": CORE_PROMPT.format(transcript=text)}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def build_markdown(meta, core_points, transcript):
    from datetime import datetime
    title = " ".join(str(meta["title"]).splitlines()).strip() or "untitled"
    frontmatter = yaml.safe_dump(
        {
            "source": meta["source_url"],
            "video_id": str(meta["vid"]),
            "type": meta["kind"],
            "title": title,
            "clipped": datetime.now().strftime("%Y-%m-%d"),
            "tags": meta.get("tags", ["douyin", "AI学习"]),
        },
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    fm = [
        "---",
        frontmatter,
        "---",
        "",
        f"# {title}",
        "",
        f"> 来源：[{meta['source_url']}]({meta['source_url']})",
        "",
        "## 1. 核心观点",
        "",
        core_points,
        "",
        "## 2. 逐字稿",
        "",
        transcript,
        "",
    ]
    return "\n".join(fm)


def write_note(meta, core_points, transcript, cfg):
    vault = Path(cfg["obsidian"]["vault_path"]).expanduser().resolve()
    subdir = cfg["obsidian"]["notes_subdir"]
    if os.path.isabs(subdir):
        raise ValueError("obsidian.notes_subdir 必须是 vault 内的相对路径")
    out_dir = (vault / subdir).resolve()
    if out_dir != vault and vault not in out_dir.parents:
        raise ValueError("obsidian.notes_subdir 不能指向 vault 之外")
    os.makedirs(out_dir, exist_ok=True)
    meta = {**meta, "tags": cfg["obsidian"].get("tags", ["douyin", "AI学习"])}
    fname = f"{meta['vid']}_{safe_filename(meta['title'])}.md"
    path = out_dir / fname
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(meta, core_points, transcript))
    return str(path)
