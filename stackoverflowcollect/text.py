from __future__ import annotations

import re
from bs4 import BeautifulSoup


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
