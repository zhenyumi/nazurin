import unittest
from unittest.mock import patch

import pytest

from nazurin.utils.exceptions import NazurinError
from nazurin.utils.helpers import FILENAME_MAX_LENGTH

from .api import Telegraph, validate_page_path
from .models import build_archive_name


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    async def json(self):
        return self.payload


class FakeRequest:
    response = None
    requested_url = None
    requested_params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def get(self, url, **kwargs):
        type(self).requested_url = url
        type(self).requested_params = kwargs.get("params")
        return type(self).response


class TestTelegraphAPI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.envelope = {
            "ok": True,
            "result": {
                "path": "Page-01-01",
                "url": "https://telegra.ph/Page-01-01",
                "title": "Page",
                "description": "Description",
                "views": 10,
                "content": [{"tag": "p", "children": ["Text"]}],
            },
        }

    async def test_get_page_uses_official_read_api(self):
        FakeRequest.response = FakeResponse(self.envelope)
        with patch("nazurin.sites.telegraph.api.Request", FakeRequest):
            raw, page = await Telegraph().get_page("Page-01-01")
        assert raw is self.envelope
        assert page["content"] == self.envelope["result"]["content"]
        assert FakeRequest.requested_url.endswith("/getPage/Page-01-01")
        assert FakeRequest.requested_params == {"return_content": "true"}

    async def test_rejects_api_error(self):
        FakeRequest.response = FakeResponse({"ok": False, "error": "PAGE_NOT_FOUND"})
        with (
            patch("nazurin.sites.telegraph.api.Request", FakeRequest),
            pytest.raises(NazurinError, match="PAGE_NOT_FOUND"),
        ):
            await Telegraph().get_page("Missing-01-01")

    async def test_accepts_empty_content(self):
        envelope = {
            **self.envelope,
            "result": {**self.envelope["result"], "content": []},
        }
        FakeRequest.response = FakeResponse(envelope)
        with patch("nazurin.sites.telegraph.api.Request", FakeRequest):
            _, page = await Telegraph().get_page("Page-01-01")
        assert page["content"] == []

    async def test_rejects_missing_content(self):
        result = {**self.envelope["result"]}
        result.pop("content")
        FakeRequest.response = FakeResponse({"ok": True, "result": result})
        with (
            patch("nazurin.sites.telegraph.api.Request", FakeRequest),
            pytest.raises(NazurinError),
        ):
            await Telegraph().get_page("Page-01-01")

    def test_validate_page_path(self):
        assert validate_page_path("/Page-01-01/") == "Page-01-01"
        for value in ["", "..", "one%2Ftwo", "one\\two"]:
            with pytest.raises(NazurinError):
                validate_page_path(value)

    def test_archive_name_uses_title_and_stable_path_hash(self):
        first = build_archive_name(self.envelope["result"])
        second = build_archive_name(
            {**self.envelope["result"], "description": "Changed"},
        )
        assert first == second
        assert first.startswith("Page (")
        assert "Page-01-01" not in first

    def test_archive_name_sanitizes_and_bounds_long_title(self):
        page = {
            **self.envelope["result"],
            "title": "folder/name " + "长" * 400,
        }
        archive_name = build_archive_name(page)
        assert "/" not in archive_name
        assert len(archive_name) == FILENAME_MAX_LENGTH
