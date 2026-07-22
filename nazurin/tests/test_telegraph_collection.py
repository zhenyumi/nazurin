import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bson import BSON

from nazurin.bot import NazurinBot
from nazurin.database.mongo import Mongo
from nazurin.models import Document
from nazurin.utils.exceptions import AlreadyExistsError


class TestTelegraphCollection(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_stops_before_download_and_storage(self):
        illust = SimpleNamespace(download=AsyncMock())
        document = Document(id="Page-01-01", collection="telegraph", data={})
        match_result = SimpleNamespace(
            source=SimpleNamespace(name="telegraph"),
            match=SimpleNamespace(groups=lambda: ("Page-01-01",)),
        )
        sites = SimpleNamespace(
            match=lambda _urls: match_result,
            handle_update=AsyncMock(return_value=(illust, document)),
        )
        database_document = SimpleNamespace(exists=AsyncMock(return_value=True))
        database_collection = SimpleNamespace(
            document=lambda _key: database_document,
        )
        database = SimpleNamespace(collection=lambda _key: database_collection)
        storage = SimpleNamespace(store=AsyncMock())
        bot = SimpleNamespace(sites=sites, storage=storage)
        bot_module = importlib.import_module("nazurin.bot")

        with patch.object(
            bot_module,
            "Database",
            return_value=SimpleNamespace(driver=lambda: database),
        ), pytest.raises(AlreadyExistsError):
            await NazurinBot.update_collection(bot, ["https://telegra.ph/Page-01-01"])

        illust.download.assert_not_awaited()
        storage.store.assert_not_awaited()

    async def test_gallery_receives_link_instead_of_images(self):
        source_url = "https://telegra.ph/Page-01-01"
        illust = SimpleNamespace(
            download=AsyncMock(),
            metadata={"source_url": source_url},
        )
        document = Document(id="Page-01-01", collection="telegraph", data={})
        match_result = SimpleNamespace(
            source=SimpleNamespace(name="telegraph"),
            match=SimpleNamespace(groups=lambda: (source_url,)),
        )
        sites = SimpleNamespace(
            match=lambda _urls: match_result,
            handle_update=AsyncMock(return_value=(illust, document)),
        )
        database_document = SimpleNamespace(exists=AsyncMock(return_value=False))
        database_collection = SimpleNamespace(
            document=lambda _key: database_document,
            insert=AsyncMock(return_value=True),
        )
        database = SimpleNamespace(collection=lambda _key: database_collection)
        storage = SimpleNamespace(store=AsyncMock())
        bot = SimpleNamespace(
            sites=sites,
            storage=storage,
            send_message=AsyncMock(),
            send_to_gallery=AsyncMock(),
        )
        bot_module = importlib.import_module("nazurin.bot")

        with patch.object(
            bot_module,
            "Database",
            return_value=SimpleNamespace(driver=lambda: database),
        ), patch.object(bot_module.config, "GALLERY_ID", 123):
            result = await NazurinBot.update_collection(bot, [source_url])

        assert result is True
        illust.download.assert_awaited_once()
        bot.send_message.assert_awaited_once_with(123, source_url)
        bot.send_to_gallery.assert_not_awaited()
        storage.store.assert_awaited_once_with(illust)
        database_collection.insert.assert_awaited_once()

    async def test_metadata_uses_standard_mongo_insert_shape(self):
        page_path = "Page-01-01"
        image_count = 500
        data = {
            "path": page_path,
            "url": f"https://telegra.ph/{page_path}",
            "title": "Page",
            "content": [
                {
                    "tag": "img",
                    "attrs": {"src": f"https://images.example/{index}.jpg"},
                }
                for index in range(image_count)
            ],
            "views": 1,
            "canonical_path": page_path,
            "content_sha256": "0" * 64,
            "source_url": f"https://telegra.ph/{page_path}",
            "collected_at": 1.0,
        }
        collection = SimpleNamespace(
            insert_one=AsyncMock(
                return_value=SimpleNamespace(acknowledged=True),
            ),
        )
        mongo = object.__new__(Mongo)
        mongo._collection = collection

        assert BSON.encode({**data, "_id": page_path})
        assert await mongo.insert(page_path, data) is True

        assert data["_id"] == page_path
        collection.insert_one.assert_awaited_once_with(data)
        assert len(data["content"]) == image_count
