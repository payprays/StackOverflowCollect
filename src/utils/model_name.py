import re


def model_token(model: str | None) -> str:
    """
    Normalize a model name to a filesystem-safe token.
    Rules:
    - Take the part before any ':' (strip deployment suffixes).
    - Take the part before the first '.' (e.g., gpt-5.1 -> gpt-5).
    - Remove non-alphanumeric characters.
    - Lowercase.
    Returns "model" if empty.
    """
    if not model:
        return "model"
    name = model.split(":", 1)[0]
    if "." in name:
        name = name.split(".", 1)[0]
    token = re.sub(r"[^a-zA-Z0-9]+", "", name).lower()
    return token or "model"
