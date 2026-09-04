from app.services.article_collector import ArticleCollector


HTML = """
<html lang="zh-TW">
  <head>
    <meta property="og:title" content="夏日穿搭示範">
    <meta name="author" content="Editor A">
  </head>
  <body>
    <nav>navigation noise</nav>
    <article>
      <h1>夏日穿搭示範</h1>
      <p>炎熱天氣可以利用透氣的亞麻上衣搭配寬鬆長褲，維持俐落比例與活動舒適度。</p>
      <figure>
        <img src="/look-1.jpg" alt="白色亞麻上衣與卡其寬褲" width="800" height="1200">
        <figcaption>清爽的中性色搭配</figcaption>
      </figure>
      <h2>加入視覺焦點</h2>
      <p>整體採用中性色時，可以利用一件小面積彩色配件建立視覺焦點，避免全身顯得單調。</p>
      <aside>related stories</aside>
    </article>
  </body>
</html>
"""


def test_parse_article_extracts_text_images_and_blocks() -> None:
    collector = ArticleCollector({"example.com"}, "test-agent")
    article = collector.parse_html(HTML, "https://example.com/fashion/look")

    assert article.title == "夏日穿搭示範"
    assert article.author == "Editor A"
    assert len(article.blocks) == 2
    assert "related stories" not in article.text
    assert article.images[0].url == "https://example.com/look-1.jpg"
    assert article.images[0].caption == "清爽的中性色搭配"
    assert article.blocks[0].image_indexes == [0]


def test_rejects_page_without_article_body() -> None:
    collector = ArticleCollector({"example.com"}, "test-agent")
    try:
        collector.parse_html("<html><h1>Only a title</h1></html>", "https://example.com/x")
    except ValueError as error:
        assert "article body" in str(error)
    else:
        raise AssertionError("Expected missing article body to fail")
