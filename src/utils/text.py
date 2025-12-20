from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import List, cast
from textwrap import dedent as dedent

from bs4 import BeautifulSoup, NavigableString, Tag, PageElement, XMLParsedAsHTMLWarning

# Suppress XMLParsedAsHTMLWarning - we're parsing HTML fragments, not XML
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def html_to_text(html: str) -> str:
    """
    将 Stack Overflow 的 HTML 转成更规整的 Markdown 风格文本，尽量保留代码块、列表和链接。
    - <pre><code> => fenced code block，尝试读取 language-* 作为语言提示
    - <code> => 行内反引号
    - <h1>-<h6> => 对应级别的标题
    - <ul>/<ol>/<li> => 列表，支持简单缩进
    - <blockquote> => 引用
    - <a> => [text](href)
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()

    def render(node: PageElement | Tag | NavigableString, indent: int = 0) -> str:
        if isinstance(node, NavigableString):
            return str(node)

        name = getattr(node, "name", None)
        # Handle case where node might not be Tag but also not NavigableString (e.g. Comment)
        if not name: 
            return ""

        children_text = "".join(render(cast(Tag, child), indent) for child in node.children)


        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            return f"{'#' * level} {children_text.strip()}\n\n"
        if name == "br":
            return "\n"
        if name in {"p", "div"}:
            return f"{children_text.strip()}\n\n"
        if name in {"strong", "b"}:
            return f"**{children_text.strip()}**"
        if name in {"em", "i"}:
            return f"*{children_text.strip()}*"
        if name == "code":
            # 行内 code，如果父级是 pre 会在 pre 处理中处理
            return f"`{children_text}`"
        if name == "pre":
            # 处理 <pre><code class="language-xxx">...</code></pre>
            code_child = node.find("code")
            lang = ""
            if code_child:
                # language-xxx / lang-xxx
                classes = code_child.get("class") or []
                for c in classes:
                    if c.startswith(("language-", "lang-")):
                        lang = c.split("-", 1)[1]
                        break
            code_text = code_child.get_text() if code_child else children_text
            code_text = code_text.strip("\n")
            return f"```{lang}\n{code_text}\n```\n\n"
        if name in {"ul", "ol"}:
            lines: List[str] = []
            for idx, li in enumerate(node.find_all("li", recursive=False), start=1):
                prefix = "-" if name == "ul" else f"{idx}."
                body = "".join(
                    render(child, indent + 2) for child in li.children
                ).strip()
                lines.append(" " * indent + f"{prefix} {body}")
            return "\n".join(lines) + "\n"
        if name == "li":
            return f"- {children_text.strip()}\n"
        if name == "blockquote":
            quoted = "\n".join(
                f"> {line}" if line.strip() else ">"
                for line in children_text.strip().splitlines()
            )
            return quoted + "\n\n"
        if name == "a":
            href = node.get("href", "").strip()
            text = children_text.strip() or href
            return f"[{text}]({href})" if href else text
        if name == "img":
            alt = node.get("alt", "").strip() or "image"
            src = node.get("src", "").strip()
            return f"![{alt}]({src})" if src else alt

        return children_text

    raw = render(soup)
    # 清理多余空行和空白
    lines = [line.rstrip() for line in raw.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


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
