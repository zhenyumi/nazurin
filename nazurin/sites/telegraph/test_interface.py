import re
import unittest

import pytest

from nazurin.utils.exceptions import NazurinError

from .interface import normalize_page_url, patterns


class TestTelegraphInterface(unittest.TestCase):
    def test_supported_hosts_match(self):
        assert re.search(patterns[0], "https://telegra.ph/Page-01-01")
        assert re.search(patterns[0], "https://graph.org/Page-01-01")

    def test_unrelated_hosts_do_not_match(self):
        assert not re.search(patterns[0], "https://api.telegra.ph/getPage/Page")
        assert not re.search(patterns[0], "https://telegra.ph.example.com/Page")

    def test_normalizes_url(self):
        page_path, source_url = normalize_page_url(
            "https://GRAPH.ORG/Sample-Page-01-01/?source=x#section",
        )
        assert page_path == "Sample-Page-01-01"
        assert source_url == "https://graph.org/Sample-Page-01-01"

    def test_hosts_share_document_path(self):
        telegra_path, _ = normalize_page_url("https://telegra.ph/Page-01-01")
        graph_path, _ = normalize_page_url("https://graph.org/Page-01-01")
        assert telegra_path == graph_path

    def test_rejects_invalid_path(self):
        for url in [
            "https://telegra.ph/",
            "https://telegra.ph/..",
            "https://telegra.ph/one%2Ftwo",
        ]:
            with pytest.raises(NazurinError):
                normalize_page_url(url)
