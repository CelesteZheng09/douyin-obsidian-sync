"""Interactive setup wizard for a local Douyin -> Obsidian installation."""
import argparse
import getpass
import os
import re
from pathlib import Path

import yaml

from . import config
from .collector import collect_details, do_login


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def cron_from_schedule(kind, time_value="10:00", weekday=1, interval=6):
    """Build a five-field cron expression from a friendly schedule choice."""
    if kind == "custom":
        return time_value.strip()
    if kind == "hourly":
        hours = int(interval)
        if not 1 <= hours <= 23:
            raise ValueError("小时周期必须在 1-23 之间")
        return f"0 */{hours} * * *"
    if not TIME_RE.match(time_value):
        raise ValueError("时间必须使用 HH:MM，例如 10:00")
    hour, minute = time_value.split(":")
    if kind == "daily":
        return f"{int(minute)} {int(hour)} * * *"
    if kind == "weekdays":
        return f"{int(minute)} {int(hour)} * * 1-5"
    if kind == "weekly":
        day = int(weekday)
        if not 0 <= day <= 6:
            raise ValueError("星期必须在 0-6 之间，0 代表星期日")
        return f"{int(minute)} {int(hour)} * * {day}"
    raise ValueError(f"不支持的周期：{kind}")


def default_config():
    template = Path(config.project_root(), "config.example.yaml")
    with template.open("r", encoding="utf-8") as source:
        return yaml.safe_load(source)


def save_config(cfg, path=None):
    target = Path(path or Path(config.project_root(), "config.yaml"))
    target.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def save_runtime_secret(api_key, cfg):
    env_path = Path(config.resolve({**cfg, "_base_dir": config.project_root()}, cfg["runtime"]["env_file"]))
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(f"OPENAI_API_KEY={api_key}\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    return env_path


def ask(prompt, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default or ""


def ask_yes_no(prompt, default=True):
    hint = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "是"}


def choose_schedule():
    print("\n运行周期：1) 每天  2) 工作日  3) 每周  4) 每 N 小时  5) 自定义 cron")
    choice = ask("请选择", "1")
    if choice == "4":
        return cron_from_schedule("hourly", interval=int(ask("每隔多少小时", "6")))
    if choice == "5":
        return cron_from_schedule("custom", ask("五段 cron 表达式", "0 10 * * *"))
    time_value = ask("运行时间（HH:MM）", "10:00")
    if choice == "2":
        return cron_from_schedule("weekdays", time_value)
    if choice == "3":
        weekday = int(ask("星期几（0=周日，1=周一 ... 6=周六）", "1"))
        return cron_from_schedule("weekly", time_value, weekday=weekday)
    return cron_from_schedule("daily", time_value)


def run_wizard(login=False, discover=False, install_schedule=False):
    cfg = default_config()
    print("抖音收藏夹 -> Obsidian 配置向导\n")
    cfg["douyin"]["favorite_folder_name"] = ask("抖音收藏夹名称", "AI学习")
    cfg["douyin"]["favorite_folder_id"] = ""
    cfg["obsidian"]["vault_path"] = str(
        Path(ask("Obsidian Vault 绝对路径")).expanduser().resolve()
    )
    cfg["obsidian"]["notes_subdir"] = ask(
        "Vault 内目标子目录", "_LLM/sources/web_clips/AI学习"
    )
    cfg["runtime"]["schedule"] = choose_schedule()
    mode = ask("核心观点模式（openai/manual）", "openai").lower()
    if mode not in {"openai", "manual"}:
        raise ValueError("核心观点模式只能是 openai 或 manual")
    cfg["summarize"]["mode"] = mode
    if mode == "openai":
        cfg["summarize"]["openai_base_url"] = ask(
            "OpenAI 兼容 API 地址", cfg["summarize"]["openai_base_url"]
        )
        cfg["summarize"]["openai_model"] = ask(
            "模型名称", cfg["summarize"]["openai_model"]
        )
        if ask_yes_no("把 API Key 安全保存到本机 secrets/runtime.env？", True):
            api_key = getpass.getpass("OPENAI_API_KEY（输入不会显示）: ").strip()
            if api_key:
                secret_path = save_runtime_secret(api_key, cfg)
                print(f"密钥已保存到：{secret_path}（权限 0600，不会提交 Git）")
        else:
            print("请在运行环境中设置 OPENAI_API_KEY。")

    target = save_config(cfg)
    print(f"\n配置已写入：{target}")

    loaded = config.load(str(target), reload=True)
    if login or ask_yes_no("现在扫码登录抖音并保存登录态？", True):
        do_login(loaded)
    if discover or ask_yes_no("现在验证收藏夹并自动识别收藏夹 ID？", True):
        details = collect_details(loaded, headless=False)
        cfg["douyin"]["favorite_folder_id"] = details["folder_id"]
        save_config(cfg, target)
        config.load(str(target), reload=True)
        print(f"收藏夹验证成功：ID={details['folder_id']}，共 {len(details['items'])} 条内容")
    if install_schedule or ask_yes_no("现在安装定时任务？", True):
        from .scheduler import install

        install(config.load(str(target), reload=True))


def main():
    parser = argparse.ArgumentParser(description="配置抖音收藏夹到 Obsidian 的同步流水线")
    parser.add_argument("--login", action="store_true", help="配置后直接打开登录")
    parser.add_argument("--discover", action="store_true", help="配置后直接识别收藏夹 ID")
    parser.add_argument("--install-schedule", action="store_true", help="配置后直接安装定时任务")
    args = parser.parse_args()
    run_wizard(args.login, args.discover, args.install_schedule)


if __name__ == "__main__":
    main()
