"""
链接采集（路线 A：登录态浏览器抓收藏夹）。

依赖 Codex 内置的 Node Playwright，并调用本机 Google Chrome。

工作流：
1. 首次运行：python -m pipeline.collector --login
   打开浏览器，你手动扫码登录抖音，登录成功后回车，脚本保存 storage_state。
2. 日常运行：复用保存的登录态，进入"收藏"标签，定位目标收藏夹，
   滚动加载全部卡片，正则提取所有 modal_id/video 链接。

注意：抖音前端会改版，下面的选择器以"收藏夹名称文本 + 链接正则"为主，
尽量减少对脆弱 CSS class 的依赖；若某天定位失败，优先更新 folder 定位逻辑。
"""
import argparse
import json
import os
import re
import sys

from . import config
from .browser_bridge import run_action


ITEM_RE = re.compile(
    r"/(?P<kind>video|note|article)/(?P<item_id>\d+)|modal_id(?:=|%3D)(?P<modal_id>\d+)"
)


def extract_items(html):
    """Extract canonical Douyin URLs while preserving video/note type."""
    ordered_ids = []
    kinds = {}
    for match in ITEM_RE.finditer(html):
        vid = match.group("item_id") or match.group("modal_id")
        kind = match.group("kind") or "video"
        if vid not in kinds:
            ordered_ids.append(vid)
            kinds[vid] = kind
        elif kind in ("note", "article"):
            # Explicit note links are more reliable than generic modal_id links.
            kinds[vid] = "note"
    return [
        (
            f"https://www.douyin.com/{kinds[vid]}/{vid}",
            vid,
        )
        for vid in ordered_ids
    ]


def items_from_api(items):
    """Convert Douyin collection API items into canonical URLs."""
    output = []
    for item in items:
        vid = str(item.get("aweme_id") or "")
        if not vid.isdigit():
            continue
        aweme_type = item.get("aweme_type")
        if aweme_type == 163:
            kind = "article"
        elif item.get("has_images"):
            kind = "note"
        else:
            kind = "video"
        output.append((f"https://www.douyin.com/{kind}/{vid}", vid))
    return output


def do_login(cfg):
    """交互式登录，保存 storage_state 到 cookies_file。"""
    cookies_file = config.resolve(cfg, cfg["douyin"]["cookies_file"])
    os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
    run_action(
        cfg,
        "login",
        {"cookiesFile": cookies_file},
        interactive=True,
    )
    if os.path.exists(cookies_file):
        os.chmod(cookies_file, 0o600)


def collect_details(cfg, headless=True):
    """Return target-folder items plus the stable folder ID discovered by the API."""
    d = cfg["douyin"]
    cookies_file = config.resolve(cfg, d["cookies_file"])
    if not os.path.exists(cookies_file):
        raise RuntimeError("未找到登录态，请先运行：python -m pipeline.collector --login")

    result = run_action(
        cfg,
        "collect",
        {
            "cookiesFile": cookies_file,
            "headless": headless,
            "profileUrl": d["profile_url"],
            "folderName": d["favorite_folder_name"],
            "folderId": str(d.get("favorite_folder_id") or ""),
            "maxScroll": d.get("max_scroll", 40),
        },
    )
    if not result.get("folderClicked"):
        raise RuntimeError(
            f"未能进入收藏夹 '{d['favorite_folder_name']}'，已停止以避免抓错内容"
        )
    folder_items = result.get("folderItems")
    if folder_items is None:
        expected = d.get("favorite_folder_id") or "自动识别"
        raise RuntimeError(
            f"未取得收藏夹 ID {expected} 的接口响应，已停止以避免抓错内容"
        )
    return {
        "items": items_from_api(folder_items),
        "folder_id": result.get("resolvedFolderId") or d.get("favorite_folder_id") or "",
    }


def collect(cfg, headless=True):
    """返回 [(url, vid), ...]，为目标收藏夹内全部视频链接。"""
    return collect_details(cfg, headless=headless)["items"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="交互式登录并保存登录态")
    ap.add_argument("--headful", action="store_true", help="可见模式运行采集（调试用）")
    args = ap.parse_args()
    cfg = config.load()
    if args.login:
        do_login(cfg)
        return
    links = collect(cfg, headless=not args.headful)
    print(json.dumps([{"url": u, "vid": v} for u, v in links],
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
