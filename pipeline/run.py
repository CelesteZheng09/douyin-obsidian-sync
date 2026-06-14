"""
主流程编排：采集 → 增量去重 → 逐条提取 → 生成核心观点 → 写入 Obsidian → 更新状态。

每天 10:00 由调度器（cron / Codex 定时器，见 config.runtime.schedule）触发：
    python -m pipeline.run
"""
import sys
import traceback

from . import config
from .collector import collect
from .state import State
from .extractor import extract
from .writer import make_core_points, write_note
from .normalize import extract_id
from .lock import AlreadyRunning, process_lock


def run_once(cfg):
    state = State(config.resolve(cfg, cfg["runtime"]["state_file"]))

    print("[1/4] 采集收藏夹链接…")
    links = collect(cfg, headless=True)
    print(f"      收藏夹内共 {len(links)} 条链接")

    todo = state.new_links(links)
    print(f"[2/4] 新增待处理 {len(todo)} 条")
    if not todo:
        print("无新增，结束。")
        return

    ok, fail = 0, 0
    for url, vid in todo:
        try:
            print(f"[3/4] 处理 {vid} …")
            data = extract(url, cfg)
            data["vid"] = vid
            core = make_core_points(data["transcript"], cfg)
            path = write_note(data, core, data["transcript"], cfg)
            state.mark(vid, url=data["source_url"], title=data["title"],
                       kind=data["kind"], note_path=path)
            print(f"      ✓ 已写入 {path}")
            ok += 1
        except Exception as e:
            fail += 1
            print(f"      ✗ {vid} 失败：{e}", file=sys.stderr)
            traceback.print_exc()

    print(f"[4/4] 完成：成功 {ok}，失败 {fail}")
    if fail:
        raise SystemExit(1)


def main():
    cfg = config.load()
    lock_path = config.resolve(
        cfg,
        cfg["runtime"].get("lock_file", "./state/pipeline.lock"),
    )
    try:
        with process_lock(lock_path):
            run_once(cfg)
    except AlreadyRunning as exc:
        print(f"跳过：{exc}")


if __name__ == "__main__":
    main()
