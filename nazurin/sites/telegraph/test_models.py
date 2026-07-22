import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiofiles
import aiofiles.os

from nazurin.utils.exceptions import NazurinError

from .models import TelegraphIllust

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
)
EXPECTED_DOWNLOADS = 3


class FakeImageRequest:
    downloads = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def download(self, url, destination):
        type(self).downloads += 1
        if "fail" in url:
            raise NazurinError("download failed")
        async with aiofiles.open(destination, "wb") as file:
            await file.write(PNG)


class TestTelegraphIllust(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeImageRequest.downloads = 0
        self.page = {
            "path": "Page-01-01",
            "url": "https://telegra.ph/Page-01-01",
            "title": "Page",
            "author_name": "Author",
            "content": [
                {"tag": "p", "children": ["Before"]},
                {"tag": "img", "attrs": {"src": "/file/first"}},
                {"tag": "img", "attrs": {"src": "/file/fail.jpg"}},
                {
                    "tag": "img",
                    "attrs": {"src": "https://images.example/third.jpg"},
                },
                {"tag": "p", "children": ["After"]},
            ],
        }
        self.envelope = {"ok": True, "result": self.page}

    async def test_prepares_page_directory_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "nazurin.sites.telegraph.models.TEMP_DIR",
            directory,
        ), patch("nazurin.sites.telegraph.models.Request", FakeImageRequest):
            illust = TelegraphIllust(
                self.envelope,
                self.page,
                self.page["url"],
                "Telegraph/Page-01-01",
            )
            await illust.download()

            assert illust._workspace is not None
            assert illust.archive_name.startswith("Page (")
            assert illust.archive_name.endswith(")")
            assert Path(illust._workspace).parent.name == illust.archive_name
            assert Path(illust._workspace).name.startswith("work-")
            assert [image.name for image in illust.images] == ["001.png", "003.png"]
            assert all(
                image.destination.as_posix().endswith(
                    "Telegraph/Page-01-01/assets",
                )
                for image in illust.images
            )
            assert [file.name for file in illust.files] == [
                "article.html",
                "page.json",
            ]
            assert all(
                [
                    await aiofiles.os.path.exists(file.path)
                    for file in illust.all_files
                ],
            )
            async with aiofiles.open(illust.page_file.path) as page_file:
                assert json.loads(await page_file.read()) == self.envelope

            async with aiofiles.open(illust.article_file.path) as article_file:
                html = await article_file.read()
            assert 'src="assets/001.png"' in html
            assert 'src="assets/003.png"' in html
            assert "https://telegra.ph/file/fail.jpg" in html
            assert (
                html.index("Before")
                < html.index("assets/001.png")
                < html.index("After")
            )

            await illust.download()
            assert FakeImageRequest.downloads == EXPECTED_DOWNLOADS

    async def test_content_hash_is_stable(self):
        first = TelegraphIllust(
            self.envelope,
            self.page,
            self.page["url"],
            "Telegraph/Page-01-01",
        )
        second = TelegraphIllust(
            self.envelope,
            {**self.page, "views": 999},
            self.page["url"],
            "Telegraph/Page-01-01",
        )
        assert first.metadata["content_sha256"] == second.metadata["content_sha256"]
