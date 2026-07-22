import tempfile
import unittest
from pathlib import Path

import aiofiles

from nazurin.models import File, Image


class FakeSession:
    async def download(self, _url, destination):
        async with aiofiles.open(destination, "wb") as file:
            await file.write(b"content")


class TestFileLocalPath(unittest.IsolatedAsyncioTestCase):
    async def test_download_uses_custom_local_path(self):
        with tempfile.TemporaryDirectory() as directory:
            local_path = Path(directory, "nested", "article.html")
            file = File("article.html", "https://example.com", local_path=local_path)
            file.destination = "Telegraph/Page"
            await file.download(FakeSession())
            assert file.path == str(local_path)
            async with aiofiles.open(local_path, "rb") as downloaded:
                assert await downloaded.read() == b"content"
            assert file.name == "article.html"
            assert file.destination.as_posix().endswith("Telegraph/Page")

    def test_image_positional_arguments_remain_compatible(self):
        image = Image("image.jpg", "https://example.com/image.jpg", "Target", "thumb")
        assert image._destination == "Target"
        assert image.thumbnail == "thumb"
