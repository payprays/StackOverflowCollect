from __future__ import annotations

import re
from bs4 import BeautifulSoup
from pathlib import Path


def html_to_text(html: str) -> str:
    """Convert Stack Overflow HTML snippets to readable plain text."""
    soup = BeautifulSoup(html, "html.parser")

    for code in soup.find_all("code"):
        code.insert_before("`")
        code.insert_after("`")

    for li in soup.find_all("li"):
        li.insert_before("\n- ")

    text = soup.get_text(separator="\n")
    normalized = "\n".join(line.strip() for line in text.splitlines())
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized


def is_file_empty(file_path: Path) -> bool:
    """Check if a file is empty."""
    try:
        return file_path.stat().st_size == 0
    except FileNotFoundError:
        return True


def is_file_chinese(file_path: Path) -> bool:
    """Check if a file contains Chinese characters."""
    chinese_char_pattern = re.compile(r"[\u4e00-\u9fff]")
    try:
        with file_path.open("r", encoding="utf-8") as f:
            content = f.read()
            return bool(chinese_char_pattern.search(content))
    except FileNotFoundError:
        return False
