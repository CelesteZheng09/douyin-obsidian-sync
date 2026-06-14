"""工具函数：URL 归一化、video_id 提取、链接类型判断、文件名清洗。"""
import re

ID_RE = re.compile(r"(?:modal_id=|/(?:video|note|article)/)(\d+)")


def extract_id(url):
    """从任意抖音链接中提取数字 video/note id。"""
    m = ID_RE.search(url)
    return m.group(1) if m else None


def normalize(url, kind=None):
    """
    把 user/self?modal_id=<ID> 归一化为可直接打开的详情页。
    kind: "video" / "note" / None(未知，默认按 video)
    """
    vid = extract_id(url)
    if not vid:
        return url, None
    if kind == "note" or "/note/" in url:
        return f"https://www.douyin.com/note/{vid}", "note"
    if kind == "article" or "/article/" in url:
        return f"https://www.douyin.com/article/{vid}", "note"
    return f"https://www.douyin.com/video/{vid}", "video"


_INVALID = re.compile(r'[\\/:*?"<>|\n\r\t]')


def safe_filename(name, maxlen=80):
    """清洗标题用于文件名，去掉非法字符并截断。"""
    name = _INVALID.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    return name[:maxlen] if name else "untitled"
