import pytest

from app.knowledge.ingestion.import_input import (
    allowed_domain, normalize_article_url, parse_import_input,
)


@pytest.mark.parametrize("url", [
    "http://localhost/a", "http://127.0.0.1/a", "http://[::1]/a",
    "http://192.168.1.2/a", "http://10.0.0.1/a", "http://172.16.0.1/a",
    "/article", "身形、腰線與比例", "javascript:alert(1)",
    "https://app.example.com/article",
])
def test_non_public_and_internal_input_is_rejected(url):
    with pytest.raises(ValueError):
        normalize_article_url(url, {"app.example.com"})


def test_markdown_heading_is_metadata_not_url():
    result = parse_import_input("# 身形、腰線與比例\n[文章](https://www.vogue.com/article)\nhttps://gq.com/story")
    assert result == [
        ("https://www.vogue.com/article", "身形、腰線與比例"),
        ("https://gq.com/story", "身形、腰線與比例"),
    ]


def test_normalization_deduplicates_www_case_fragment_and_default_port():
    assert normalize_article_url("https://WWW.VOGUE.COM:443/article#section") == normalize_article_url("https://vogue.com/article")


def test_subdomain_supported_without_accepting_suffix_spoof():
    assert allowed_domain("https://www.vogue.com/article", {"vogue.com"})
    assert allowed_domain("https://archive.vogue.com/article", {"www.vogue.com"})
    assert not allowed_domain("https://evilvogue.com/article", {"vogue.com"})
    assert not allowed_domain("https://vogue.com.evil.com/article", {"vogue.com"})
