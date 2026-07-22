import unittest

from .renderer import TelegraphRenderer, collect_image_references


class TestTelegraphRenderer(unittest.TestCase):
    def setUp(self):
        self.page = {
            "path": "Page-01-01",
            "url": "https://telegra.ph/Page-01-01",
            "title": "Title <unsafe>",
            "author_name": "Author & Co.",
            "author_url": "https://example.com/profile?a=1&b=2",
            "content": [],
        }

    def render(self, content, image_paths=None):
        page = {**self.page, "content": content}
        return TelegraphRenderer(
            page,
            "https://telegra.ph/Page-01-01",
            image_paths,
        ).render()

    def test_renders_structured_content_in_order(self):
        html = self.render(
            [
                {"tag": "h3", "children": ["Heading"]},
                {"tag": "p", "children": ["Paragraph"]},
                {
                    "tag": "ul",
                    "children": [{"tag": "li", "children": ["Item"]}],
                },
                {"tag": "blockquote", "children": ["Quote"]},
                {
                    "tag": "pre",
                    "children": [{"tag": "code", "children": ["x < y"]}],
                },
            ],
        )
        assert html.index("Heading") < html.index("Paragraph") < html.index("Item")
        assert "<blockquote>Quote</blockquote>" in html
        assert "<pre><code>x &lt; y</code></pre>" in html
        assert "Title &lt;unsafe&gt;" in html
        assert "Author &amp; Co." in html

    def test_escapes_links_and_rejects_dangerous_schemes(self):
        html = self.render(
            [
                {
                    "tag": "a",
                    "attrs": {"href": "https://example.com/?a=1&b=2", "onclick": "x"},
                    "children": ["Safe"],
                },
                {
                    "tag": "a",
                    "attrs": {"href": "javascript:alert(1)"},
                    "children": ["Unsafe"],
                },
            ],
        )
        assert 'href="https://example.com/?a=1&amp;b=2"' in html
        assert "onclick" not in html
        assert "javascript:" not in html
        assert "Unsafe" in html

    def test_rewrites_images_and_degrades_embeds(self):
        content = [
            {"tag": "img", "attrs": {"src": "/file/first.jpg"}},
            {"tag": "img", "attrs": {"src": "https://example.com/second.png"}},
            {"tag": "iframe", "attrs": {"src": "https://example.com/embed"}},
            {"tag": "video", "attrs": {"src": "https://example.com/video"}},
        ]
        html = self.render(content, {1: "assets/001.jpg"})
        assert 'src="assets/001.jpg"' in html
        assert "https://example.com/second.png" in html
        assert "Embedded content" in html
        assert ">Video</a>" in html
        assert "<iframe" not in html
        assert "<video" not in html

    def test_unknown_nodes_keep_only_children(self):
        html = self.render(
            [
                {
                    "tag": "script",
                    "attrs": {"src": "https://example.com/script.js"},
                    "children": ["visible <text>"],
                },
            ],
        )
        assert "<script" not in html
        assert "script.js" not in html
        assert "visible &lt;text&gt;" in html

    def test_collects_all_http_images_in_order(self):
        references = collect_image_references(
            [
                {"tag": "img", "attrs": {"src": "/file/one.jpg"}},
                {
                    "tag": "figure",
                    "children": [
                        {
                            "tag": "img",
                            "attrs": {"src": "https://example.com/two.jpg"},
                        },
                    ],
                },
            ],
            "https://telegra.ph/Page-01-01",
        )
        assert [reference.occurrence for reference in references] == [1, 2]
        assert [reference.url for reference in references] == [
            "https://telegra.ph/file/one.jpg",
            "https://example.com/two.jpg",
        ]
