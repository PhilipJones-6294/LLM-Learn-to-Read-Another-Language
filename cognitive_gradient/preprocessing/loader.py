import os


def load_novel(path: str) -> str:
    """Load novel from .txt or .epub, return plain text."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        return _load_epub(path)
    return _load_txt(path)


def _load_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_epub(path: str) -> str:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("ebooklib and beautifulsoup4 required for .epub: pip install ebooklib beautifulsoup4")

    book = epub.read_epub(path)
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text()
        if text.strip():
            chapters.append(text)
    return "\n\n".join(chapters)
