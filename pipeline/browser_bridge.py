"""Bridge Python orchestration to the project's Node Playwright runtime."""
import json
import os
import subprocess


def run_action(cfg, action, payload=None, interactive=False):
    runtime = cfg["runtime"]
    node = runtime.get("node_executable", "node")
    module = runtime.get("playwright_module", "playwright")
    script = os.path.join(cfg["_base_dir"], "scripts", "douyin_browser.mjs")
    args = [node, script, action, module, json.dumps(payload or {}, ensure_ascii=False)]
    if interactive:
        subprocess.run(args, check=True)
        return None
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "未知浏览器错误"
        raise RuntimeError(f"浏览器操作失败：{detail}")
    return json.loads(result.stdout)
