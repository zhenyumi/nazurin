import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiofiles
import aiofiles.os

from nazurin.models import File
from nazurin.storage.local import Local


class TestGeneratedFileStorage(unittest.IsolatedAsyncioTestCase):
    async def test_local_preserves_page_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "workspace", "article.html")
            await aiofiles.os.makedirs(source.parent)
            async with aiofiles.open(source, "w") as source_file:
                await source_file.write("article")
            file = File("article.html", local_path=source)
            file.destination = "Telegraph/Page-01-01"

            with patch("nazurin.storage.local.DATA_DIR", directory):
                await Local().store([file])

            stored = Path(directory, file.destination, file.name)
            async with aiofiles.open(stored) as stored_file:
                assert await stored_file.read() == "article"

    async def test_s3_uses_destination_and_local_source(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"S3_ACCESS_KEY": "test", "S3_SECRET_KEY": "test"},
        ):
            module = importlib.import_module("nazurin.storage.s3")
            source = Path(directory, "workspace", "page.json")
            await aiofiles.os.makedirs(source.parent)
            async with aiofiles.open(source, "w") as source_file:
                await source_file.write("{}")
            file = File("page.json", local_path=source)
            file.destination = "Telegraph/Page-01-01"

            calls = []

            class FakeClient:
                def fput_object(self, **kwargs):
                    calls.append(kwargs)

            with patch.object(module.S3, "client", FakeClient()):
                await module.S3().upload(file)

            assert calls[0]["file_path"] == str(source)
            assert calls[0]["object_name"].endswith(
                "Telegraph/Page-01-01/page.json",
            )
