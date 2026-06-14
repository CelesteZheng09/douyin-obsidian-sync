"""配置加载：读取 config.yaml，提供给各模块统一访问。"""
import os
import yaml

_CONFIG = None


def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env_file(path):
    if not path or not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as source:
        for raw_line in source:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def load(path=None, reload=False):
    global _CONFIG
    if _CONFIG is not None and not reload:
        return _CONFIG
    base = project_root()
    path = path or os.path.join(base, "config.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"未找到 {path}，请先复制 config.example.yaml 为 config.yaml 并填写。"
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_base_dir"] = base
    env_file = (cfg.get("runtime") or {}).get("env_file")
    if env_file:
        _load_env_file(resolve(cfg, env_file))
    _CONFIG = cfg
    return cfg


def resolve(cfg, rel):
    """把配置里的相对路径解析为基于项目根目录的绝对路径。"""
    if os.path.isabs(rel):
        return rel
    return os.path.join(cfg["_base_dir"], rel)
