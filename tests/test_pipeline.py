import json
import os
import shlex
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import yaml

from pipeline.collector import collect, collect_details, extract_items, items_from_api
from pipeline.extractor import (
    _download_whisper_model,
    _duration,
    _prepare_hf_download_env,
    _slice_wav,
    extract_note_text,
    prepare_cookie_file,
)
from pipeline.normalize import extract_id, normalize, safe_filename
from pipeline.state import State
from pipeline.scheduler import build_cron_line, validate_cron
from pipeline.setup import cron_from_schedule
from pipeline.lock import AlreadyRunning, process_lock
from pipeline.writer import build_markdown, write_note


class CollectorTests(unittest.TestCase):
    @patch("pipeline.collector.run_action")
    def test_login_state_is_private(self, action):
        from pipeline.collector import do_login

        with tempfile.TemporaryDirectory() as tmp:
            cookie_path = Path(tmp, "secrets", "cookies.json")

            def create_cookie(*_args, **_kwargs):
                cookie_path.write_text("{}", encoding="utf-8")

            action.side_effect = create_cookie
            cfg = {
                "_base_dir": tmp,
                "douyin": {"cookies_file": "secrets/cookies.json"},
            }

            do_login(cfg)

            self.assertEqual(os.stat(cookie_path).st_mode & 0o777, 0o600)

    def test_extract_items_preserves_video_and_note_types(self):
        html = """
        <a href="/video/111">video</a>
        <a href="https://www.douyin.com/note/222">note</a>
        <a href="https://www.douyin.com/article/444">article</a>
        <a href="/user/self?modal_id=333">modal</a>
        """

        self.assertEqual(
            extract_items(html),
            [
                ("https://www.douyin.com/video/111", "111"),
                ("https://www.douyin.com/note/222", "222"),
                ("https://www.douyin.com/article/444", "444"),
                ("https://www.douyin.com/video/333", "333"),
            ],
        )

    def test_note_url_wins_when_same_id_also_appears_as_modal(self):
        html = '<a href="?modal_id=222"></a><a href="/note/222"></a>'

        self.assertEqual(
            extract_items(html),
            [("https://www.douyin.com/note/222", "222")],
        )

    def test_items_from_api_maps_video_article_and_note(self):
        self.assertEqual(
            items_from_api(
                [
                    {"aweme_id": "111", "aweme_type": 0},
                    {"aweme_id": "222", "aweme_type": 163},
                    {"aweme_id": "333", "aweme_type": 68, "has_images": True},
                ]
            ),
            [
                ("https://www.douyin.com/video/111", "111"),
                ("https://www.douyin.com/article/222", "222"),
                ("https://www.douyin.com/note/333", "333"),
            ],
        )

    @patch("pipeline.collector.run_action")
    @patch("pipeline.collector.os.path.exists", return_value=True)
    def test_collect_stops_when_target_folder_was_not_clicked(self, _exists, action):
        action.return_value = {
            "folderClicked": False,
            "visibleLinks": [{"href": "https://www.douyin.com/video/123"}],
        }
        cfg = {
            "_base_dir": "/tmp",
            "douyin": {
                "cookies_file": "cookies.json",
                "favorite_folder_name": "AI",
                "favorite_folder_id": "999",
                "profile_url": "https://example.test",
            },
        }

        with self.assertRaisesRegex(RuntimeError, "避免抓错内容"):
            collect(cfg)

    @patch("pipeline.collector.run_action")
    @patch("pipeline.collector.os.path.exists", return_value=True)
    def test_collect_uses_only_visible_card_links(self, _exists, action):
        action.return_value = {
            "folderClicked": True,
            "folderItems": [
                {"aweme_id": "123", "aweme_type": 0},
                {"aweme_id": "456", "aweme_type": 163},
            ],
            "visibleLinks": [
                {"href": "https://www.douyin.com/video/123", "text": "A"},
                {"href": "https://www.douyin.com/article/456", "text": "B"},
            ],
        }
        cfg = {
            "_base_dir": "/tmp",
            "douyin": {
                "cookies_file": "cookies.json",
                "favorite_folder_name": "AI",
                "favorite_folder_id": "999",
                "profile_url": "https://example.test",
            },
        }

        self.assertEqual(
            collect(cfg),
            [
                ("https://www.douyin.com/video/123", "123"),
                ("https://www.douyin.com/article/456", "456"),
            ],
        )

    @patch("pipeline.collector.run_action")
    @patch("pipeline.collector.os.path.exists", return_value=True)
    def test_collect_can_auto_discover_folder_id(self, _exists, action):
        action.return_value = {
            "folderClicked": True,
            "resolvedFolderId": "888",
            "folderItems": [{"aweme_id": "123", "aweme_type": 0}],
        }
        cfg = {
            "_base_dir": "/tmp",
            "douyin": {
                "cookies_file": "cookies.json",
                "favorite_folder_name": "AI",
                "favorite_folder_id": "",
                "profile_url": "https://example.test",
            },
        }

        details = collect_details(cfg)

        self.assertEqual(details["folder_id"], "888")
        self.assertEqual(details["items"], [("https://www.douyin.com/video/123", "123")])
        self.assertEqual(action.call_args.args[2]["folderId"], "")


class NormalizeTests(unittest.TestCase):
    def test_normalize_video_note_and_modal_urls(self):
        self.assertEqual(extract_id("https://x.test/video/123"), "123")
        self.assertEqual(
            normalize("https://www.douyin.com/note/456"),
            ("https://www.douyin.com/note/456", "note"),
        )
        self.assertEqual(
            normalize("https://www.douyin.com/article/654"),
            ("https://www.douyin.com/article/654", "note"),
        )
        self.assertEqual(
            normalize("https://www.douyin.com/user/self?modal_id=789"),
            ("https://www.douyin.com/video/789", "video"),
        )

    def test_safe_filename_removes_reserved_characters(self):
        self.assertEqual(safe_filename('a/b:c*?"<>|\n'), "a_b_c_______")


class StateTests(unittest.TestCase):
    def test_mark_persists_and_new_links_filters_processed_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "state", "processed.json")
            state = State(str(path))
            state.mark("123", title="done")

            reloaded = State(str(path))

            self.assertTrue(reloaded.is_done("123"))
            self.assertEqual(
                reloaded.new_links(
                    [
                        ("https://www.douyin.com/video/123", "123"),
                        ("https://www.douyin.com/note/456", "456"),
                    ]
                ),
                [("https://www.douyin.com/note/456", "456")],
            )


class LockTests(unittest.TestCase):
    def test_process_lock_rejects_overlapping_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "state", "pipeline.lock"))
            with process_lock(path):
                with self.assertRaises(AlreadyRunning):
                    with process_lock(path):
                        pass


class CookieTests(unittest.TestCase):
    def test_prepare_cookie_file_converts_playwright_storage_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "storage.json")
            target = Path(tmp, "cookies.txt")
            source.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "sessionid",
                                "value": "secret-value",
                                "domain": ".douyin.com",
                                "path": "/",
                                "expires": 1893456000,
                                "httpOnly": True,
                                "secure": True,
                                "sameSite": "Lax",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = prepare_cookie_file(str(source), str(target))

            self.assertEqual(result, str(target))
            text = target.read_text(encoding="utf-8")
            self.assertIn("# Netscape HTTP Cookie File", text)
            self.assertIn(".douyin.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\tsecret-value", text)
            self.assertEqual(os.stat(target).st_mode & 0o777, 0o600)


class AudioTests(unittest.TestCase):
    def test_huggingface_download_uses_regular_http_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            _prepare_hf_download_env()

            self.assertEqual(os.environ["HF_HUB_DISABLE_XET"], "1")
            self.assertEqual(os.environ["HF_HUB_DOWNLOAD_TIMEOUT"], "300")

    @patch("huggingface_hub.snapshot_download", return_value="/tmp/model")
    def test_model_download_is_serial_and_uses_long_timeout(self, download):
        cfg = {
            "_base_dir": "/tmp/project",
            "asr": {
                "model_size": "small",
                "model_dir": "./models/small",
                "download_workers": 1,
                "download_timeout": 300,
            },
        }

        result = _download_whisper_model(cfg)

        self.assertEqual(result, "/tmp/model")
        self.assertEqual(download.call_args.args, ("Systran/faster-whisper-small",))
        self.assertEqual(download.call_args.kwargs["max_workers"], 1)
        self.assertEqual(download.call_args.kwargs["etag_timeout"], 300)

    def test_slice_wav_keeps_requested_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "source.wav")
            target = Path(tmp, "slice.wav")
            with wave.open(str(source), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 32000)

            _slice_wav(str(source), str(target), 1, 0.5)

            self.assertAlmostEqual(_duration(str(target)), 0.5, places=2)


class SetupTests(unittest.TestCase):
    def test_schedule_presets_generate_cron(self):
        self.assertEqual(cron_from_schedule("daily", "09:30"), "30 9 * * *")
        self.assertEqual(cron_from_schedule("weekdays", "18:05"), "5 18 * * 1-5")
        self.assertEqual(cron_from_schedule("weekly", "08:00", weekday=6), "0 8 * * 6")
        self.assertEqual(cron_from_schedule("hourly", interval=4), "0 */4 * * *")

    def test_schedule_rejects_invalid_time(self):
        with self.assertRaises(ValueError):
            cron_from_schedule("daily", "25:00")


class SchedulerTests(unittest.TestCase):
    def test_build_cron_line_uses_absolute_paths_and_marker(self):
        cfg = {
            "_base_dir": "/tmp/project with spaces",
            "runtime": {"schedule": "0 10 * * *"},
        }

        line = build_cron_line(cfg, python_executable="/tmp/venv/bin/python")

        self.assertIn("0 10 * * *", line)
        self.assertIn(shlex.quote(str(Path("/tmp/project with spaces").resolve())), line)
        self.assertIn(f"{Path('/tmp/venv/bin/python').resolve()} -m pipeline.run", line)
        self.assertIn("# douyin-obsidian-sync:", line)

    def test_validate_cron_rejects_shell_content(self):
        with self.assertRaises(ValueError):
            validate_cron("0 10 * * *; curl bad.test")


class ExtractorTests(unittest.TestCase):
    @patch("pipeline.extractor.run_action")
    def test_article_uses_complete_detail_markdown(self, action):
        action.return_value = {
            "data": {
                "aweme_detail": {
                    "desc": "fallback",
                    "article_info": {
                        "article_title": "Article title",
                        "article_content": json.dumps({"markdown": "完整正文"}),
                        "has_more": False,
                    },
                }
            }
        }
        cfg = {
            "_base_dir": "/tmp",
            "douyin": {"cookies_file": "cookies.json"},
        }

        data = extract_note_text("https://www.douyin.com/article/123", cfg)

        self.assertEqual(data["title"], "Article title")
        self.assertEqual(data["transcript"], "完整正文")

    @patch("pipeline.extractor.run_action")
    def test_note_uses_detail_description_without_page_chrome(self, action):
        action.return_value = {
            "data": {
                "aweme_detail": {
                    "desc": "干净的图文正文",
                }
            }
        }
        cfg = {
            "_base_dir": "/tmp",
            "douyin": {"cookies_file": "cookies.json"},
        }

        data = extract_note_text("https://www.douyin.com/note/123", cfg)

        self.assertEqual(data["title"], "干净的图文正文")
        self.assertEqual(data["transcript"], "干净的图文正文")
        action.assert_called_once_with(
            cfg,
            "detail-api",
            {"cookiesFile": "/tmp/cookies.json", "awemeId": "123"},
        )


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.meta = {
            "source_url": "https://www.douyin.com/video/123",
            "vid": "123",
            "kind": "video",
            "title": '标题: "带引号"',
        }

    def test_frontmatter_is_valid_yaml(self):
        markdown = build_markdown(self.meta, "- 观点", "[00:00] 逐字稿")
        frontmatter = markdown.split("---", 2)[1]

        parsed = yaml.safe_load(frontmatter)

        self.assertEqual(parsed["title"], self.meta["title"])
        self.assertEqual(parsed["video_id"], "123")
        self.assertEqual(parsed["tags"], ["douyin", "AI学习"])

    def test_write_note_rejects_subdir_outside_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "obsidian": {
                    "vault_path": tmp,
                    "notes_subdir": "../outside",
                }
            }

            with self.assertRaises(ValueError):
                write_note(self.meta, "- 观点", "逐字稿", cfg)


if __name__ == "__main__":
    unittest.main()
