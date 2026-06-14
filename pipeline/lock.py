"""Cross-process lock for preventing overlapping pipeline runs on macOS/Linux."""
import contextlib
import os


class AlreadyRunning(RuntimeError):
    pass


@contextlib.contextmanager
def process_lock(path):
    import fcntl

    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning("已有一个同步任务正在运行") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
