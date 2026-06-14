"""
内容提取：把单个链接 → (title, kind, transcript_text)。

视频类：yt-dlp 下载 → PyAV 抽 16k 单声道 wav → faster-whisper 转写，
        超长音频按 config.asr.chunk_seconds 切片并加 OFFSET 合并。
图文类：用登录态浏览器渲染 note 页，展开"更多"，抓详情区正文文字。
        （图文文字在 DOM 中，这里取可见文本；个别被截断的可由 Codex 端补截图 OCR）

返回 dict: {title, kind, transcript, source_url}
"""
import json
import os
import re
import subprocess
import sys
import wave

from . import config
from .browser_bridge import run_action
from .normalize import normalize, extract_id


def _run(cmd):
    print("[cmd]", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)


def prepare_cookie_file(storage_state_path, output_path):
    """Convert Playwright storage_state JSON to a Netscape cookie jar."""
    with open(storage_state_path, "r", encoding="utf-8") as source:
        state = json.load(source)
    cookies = state.get("cookies", [])
    if not cookies:
        raise RuntimeError("登录态文件中没有 Cookie，请重新扫码登录")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as target:
        target.write("# Netscape HTTP Cookie File\n")
        target.write("# Generated from Playwright storage_state. Do not edit.\n")
        for cookie in cookies:
            domain = cookie.get("domain", "")
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            path = cookie.get("path") or "/"
            secure = "TRUE" if cookie.get("secure") else "FALSE"
            expires = max(0, int(cookie.get("expires") or 0))
            name = str(cookie.get("name", "")).replace("\t", "")
            value = str(cookie.get("value", "")).replace("\t", "")
            target.write(
                f"{domain}\t{include_subdomains}\t{path}\t{secure}\t"
                f"{expires}\t{name}\t{value}\n"
            )
    os.chmod(tmp, 0o600)
    os.replace(tmp, output_path)
    os.chmod(output_path, 0o600)
    return output_path


def download_video(url, workdir, cfg):
    """yt-dlp 下载视频，返回 mp4 路径与标题。"""
    os.makedirs(workdir, exist_ok=True)
    out_tmpl = os.path.join(workdir, "%(id)s.%(ext)s")
    storage_state = config.resolve(cfg, cfg["douyin"]["cookies_file"])
    cookie_jar = config.resolve(
        cfg,
        cfg["douyin"].get("yt_dlp_cookies_file", "./secrets/douyin_cookies.txt"),
    )
    prepare_cookie_file(storage_state, cookie_jar)
    base_cmd = [
        sys.executable, "-m", "yt_dlp", "--no-check-certificate",
        "--cookies", cookie_jar, "--no-playlist",
    ]
    # 先取标题
    title = subprocess.run(
        [*base_cmd, "--get-title", url],
        capture_output=True, text=True, check=True,
    ).stdout.strip() or "untitled"
    _run([*base_cmd, "-o", out_tmpl, url])
    # 找下载出来的视频文件
    vid = extract_id(url)
    for f in os.listdir(workdir):
        if f.startswith(vid) and f.rsplit(".", 1)[-1] in ("mp4", "mkv", "webm"):
            return os.path.join(workdir, f), title
    raise RuntimeError("yt-dlp 未产出视频文件")


def to_wav(mp4_path, workdir):
    import av

    wav = os.path.join(workdir, "audio.wav")
    with av.open(mp4_path) as container, wave.open(wav, "wb") as output:
        if not container.streams.audio:
            raise RuntimeError("下载的视频中没有音轨")
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        for frame in container.decode(stream):
            for converted in resampler.resample(frame):
                output.writeframes(converted.to_ndarray().tobytes())
        for converted in resampler.resample(None):
            output.writeframes(converted.to_ndarray().tobytes())
    return wav


def _duration(wav):
    with wave.open(wav, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _slice_wav(source, target, start_seconds, duration_seconds):
    with wave.open(source, "rb") as src, wave.open(target, "wb") as dst:
        rate = src.getframerate()
        src.setpos(min(src.getnframes(), int(start_seconds * rate)))
        dst.setnchannels(src.getnchannels())
        dst.setsampwidth(src.getsampwidth())
        dst.setframerate(rate)
        frames = src.readframes(int(duration_seconds * rate))
        dst.writeframes(frames)


def _prepare_hf_download_env():
    # The Xet transport can stall on constrained networks; keep the model on
    # Hugging Face's regular HTTP download path unless the user opts back in.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")


def _download_whisper_model(cfg):
    """Download the configured model once using a resumable, serial transfer."""
    from faster_whisper.utils import _MODELS
    from huggingface_hub import snapshot_download

    _prepare_hf_download_env()
    a = cfg["asr"]
    model_size = a["model_size"]
    repo_id = model_size if "/" in model_size else _MODELS.get(model_size)
    if not repo_id:
        raise ValueError(f"不支持的 Whisper 模型：{model_size}")

    default_dir = f"./.models/faster-whisper-{model_size.replace('/', '--')}"
    model_dir = config.resolve(cfg, a.get("model_dir", default_dir))
    required = ("config.json", "model.bin", "tokenizer.json")
    if all(os.path.isfile(os.path.join(model_dir, name)) for name in required):
        return model_dir

    os.makedirs(model_dir, exist_ok=True)
    return snapshot_download(
        repo_id,
        local_dir=model_dir,
        allow_patterns=[
            "config.json",
            "preprocessor_config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
        ],
        max_workers=a.get("download_workers", 1),
        etag_timeout=a.get("download_timeout", 300),
    )


def transcribe(wav, cfg):
    """faster-whisper 转写，超长自动切片 + OFFSET 合并。返回带时间戳文本。"""
    from faster_whisper import WhisperModel
    a = cfg["asr"]
    model_path = _download_whisper_model(cfg)
    model = WhisperModel(model_path, device=a["device"],
                         compute_type=a["compute_type"],
                         cpu_threads=a.get("cpu_threads", 4))
    chunk = a.get("chunk_seconds", 2400)
    total = _duration(wav)
    lines = []
    offset = 0
    while offset < total:
        if offset == 0 and total <= chunk:
            seg_wav = wav
        else:
            seg_wav = wav.replace(".wav", f"_{offset}.wav")
            _slice_wav(wav, seg_wav, offset, chunk)
        segments, _ = model.transcribe(
            seg_wav, language=a["language"], beam_size=5, vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt="以下是一段中文视频的逐字稿。",
        )
        for s in segments:
            t = s.start + offset
            lines.append(f"[{int(t//60):02d}:{int(t%60):02d}] {s.text.strip()}")
        offset += chunk
    return "\n".join(lines)


def extract_note_text(url, cfg):
    """图文 note：用登录态浏览器抓详情正文。"""
    cookies = config.resolve(cfg, cfg["douyin"]["cookies_file"])
    vid = extract_id(url)
    result = run_action(
        cfg,
        "detail-api",
        {"cookiesFile": cookies, "awemeId": vid},
    )
    detail = (result.get("data") or {}).get("aweme_detail") or {}
    if "/article/" in url:
        info = detail.get("article_info") or {}
        try:
            content = json.loads(info.get("article_content") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("article 详情正文不是有效 JSON") from exc
        body = (content.get("markdown") or "").strip()
        if not body or info.get("has_more"):
            raise RuntimeError("article 正文为空或仍被截断")
        return {
            "title": info.get("article_title") or detail.get("desc") or "untitled",
            "kind": "note",
            "transcript": body,
            "source_url": url,
        }

    description = (detail.get("desc") or "").strip()
    if description:
        return {
            "title": description,
            "kind": "note",
            "transcript": description,
            "source_url": url,
        }

    # Keep a rendered-page fallback for unusual note types whose detail API
    # does not expose a textual description.
    result = run_action(
        cfg,
        "note",
        {"cookiesFile": cookies, "url": url},
    )
    return {
        "title": result.get("title") or "untitled",
        "kind": "note",
        "transcript": result.get("body") or "",
        "source_url": url,
    }


def extract(url, cfg):
    norm_url, kind = normalize(url)
    workdir = config.resolve(cfg, cfg["runtime"]["workdir"])
    vid = extract_id(norm_url)
    workdir = os.path.join(workdir, vid)
    if kind == "note":
        return extract_note_text(norm_url, cfg)
    mp4, title = download_video(norm_url, workdir, cfg)
    wav = to_wav(mp4, workdir)
    text = transcribe(wav, cfg)
    return {"title": title, "kind": "video", "transcript": text,
            "source_url": norm_url}
