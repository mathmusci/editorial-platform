from editorial.extractors import ReadingTimeExtractor, build_extractor
from editorial.config.models import ProcessorConfig
from editorial.models import Article


def test_reading_time_extractor_counts_words_without_mutating_article():
    article = Article(
        title="Short title",
        summary="One two three four five.",
        content="Six seven eight nine ten.",
    )
    original = article.model_dump()
    extractor = ReadingTimeExtractor(words_per_minute=5)

    extraction = extractor.extract(article)

    assert article.model_dump() == original
    assert extraction.article_id == article.id
    assert extraction.extractor == "reading_time"
    assert extraction.kind == "reading_time"
    assert extraction.payload == {
        "word_count": 12,
        "reading_minutes": 3,
        "words_per_minute": 5,
    }


def test_build_reading_time_extractor_from_config():
    config = ProcessorConfig(type="reading_time", settings={"words_per_minute": 100})

    extractor = build_extractor(config)

    assert isinstance(extractor, ReadingTimeExtractor)
    assert extractor.words_per_minute == 100
