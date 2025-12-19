import re

def is_chinese(text: str) -> bool:
    """Check if the text contains Chinese characters."""
    chinese_char_pattern = re.compile(r"[\u4e00-\u9fff]")
    return bool(chinese_char_pattern.search(text))

def is_valid_answer(text: str) -> bool:
    """Check if the answer text is valid (non-empty)."""
    return bool(text and text.strip())
