"""
增量状态：维护已处理 video_id 清单，决定哪些链接是"新"的。
state 文件格式：
{
  "processed": {
     "<video_id>": {"url": "...", "title": "...", "kind": "video",
                    "processed_at": "2026-06-13T10:00:00", "note_path": "..."}
  }
}
"""
import json
import os
from datetime import datetime


class State:
    def __init__(self, path):
        self.path = path
        self.data = {"processed": {}}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        self.data.setdefault("processed", {})

    def is_done(self, vid):
        return vid in self.data["processed"]

    def mark(self, vid, **meta):
        meta["processed_at"] = datetime.now().isoformat(timespec="seconds")
        self.data["processed"][vid] = meta
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def new_links(self, links):
        """输入 [(url, vid), ...]，返回未处理过的子集。"""
        out = []
        for url, vid in links:
            if vid and not self.is_done(vid):
                out.append((url, vid))
        return out
