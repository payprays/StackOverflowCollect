from pathlib import Path
from src.utils.text import html_to_text, is_file_chinese, is_file_empty


def test_html_to_text_simple():
    html = "<p>Hello <b>World</b></p>"
    text = html_to_text(html)
    assert "**World**" in text
    assert "Hello" in text


def test_html_to_text_code():
    html = "<pre><code>print('hello')</code></pre>"
    text = html_to_text(html)
    assert "```" in text
    assert "print('hello')" in text


def test_html_to_text_link():
    html = '<a href="https://example.com">Link</a>'
    text = html_to_text(html)
    assert "[Link](https://example.com)" in text


def test_is_file_chinese(tmp_path):
    f = tmp_path / "chn.txt"
    f.write_text("你好", encoding="utf-8")
    assert is_file_chinese(f)

    f2 = tmp_path / "eng.txt"
    f2.write_text("Hello", encoding="utf-8")
    assert not is_file_chinese(f2)


def test_is_file_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.touch()
    assert is_file_empty(f)

    f2 = tmp_path / "filled.txt"
    f2.write_text("data")
    assert not is_file_empty(f2)
