"""News integration — task P3-BE-2."""

from backend.integrations.news.client import (
    Article,
    NewsClient,
    NewsError,
    normalize_article,
)

__all__ = [
    "Article",
    "NewsClient",
    "NewsError",
    "normalize_article",
]
