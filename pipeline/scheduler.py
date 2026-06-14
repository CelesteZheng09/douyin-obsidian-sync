"""Install and manage the pipeline in the current user's crontab."""
import argparse
import hashlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from . import config


CRON_FIELD_RE = re.compile(r"^[\d*/?,\-]+$")


def validate_cron(expression):
    fields = expression.split()
    if len(fields) != 5 or not all(CRON_FIELD_RE.match(field) for field in fields):
        raise ValueError("runtime.schedule 必须是五段 cron 表达式，例如：0 10 * * *")
    return expression


def marker(cfg):
    digest = hashlib.sha256(cfg["_base_dir"].encode()).hexdigest()[:12]
    return f"# douyin-obsidian-sync:{digest}"


def build_cron_line(cfg, python_executable=None):
    schedule = validate_cron(cfg["runtime"]["schedule"])
    root = Path(cfg["_base_dir"]).resolve()
    python = Path(python_executable or sys.executable).resolve()
    log_path = root / "run.log"
    command = (
        f"cd {shlex.quote(str(root))} && "
        f"{shlex.quote(str(python))} -m pipeline.run "
        f">> {shlex.quote(str(log_path))} 2>&1"
    )
    return f"{schedule} {command} {marker(cfg)}"


def _read_crontab():
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "无法读取 crontab")
    return result.stdout


def _write_crontab(text):
    subprocess.run(["crontab", "-"], input=text, text=True, check=True)


def _without_entry(text, entry_marker):
    lines = [line for line in text.splitlines() if entry_marker not in line]
    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def install(cfg):
    current = _read_crontab()
    clean = _without_entry(current, marker(cfg))
    line = build_cron_line(cfg)
    _write_crontab(f"{clean}{line}\n")
    print(f"定时任务已安装：{cfg['runtime']['schedule']}")
    print(f"日志：{Path(cfg['_base_dir'], 'run.log')}")


def uninstall(cfg):
    current = _read_crontab()
    updated = _without_entry(current, marker(cfg))
    _write_crontab(updated)
    print("定时任务已卸载")


def status(cfg):
    lines = [line for line in _read_crontab().splitlines() if marker(cfg) in line]
    if not lines:
        print("定时任务未安装")
        return 1
    print("定时任务已安装：")
    print("\n".join(lines))
    return 0


def main():
    parser = argparse.ArgumentParser(description="管理本地 cron 定时同步任务")
    parser.add_argument("action", choices=["install", "status", "uninstall"])
    args = parser.parse_args()
    cfg = config.load()
    if args.action == "install":
        install(cfg)
    elif args.action == "uninstall":
        uninstall(cfg)
    else:
        raise SystemExit(status(cfg))


if __name__ == "__main__":
    main()
