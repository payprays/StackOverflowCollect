import re


def model_token(model: str | None) -> str:
    """
    Normalize a model name to a filesystem-safe token.
    
    Rules:
    - Strip deployment suffixes (after ':')
    - Replace dots with underscores (preserve version: gpt-4.1 -> gpt-4_1)
    - Keep suffixes like 'mini', 'turbo', 'preview' 
    - Remove other non-alphanumeric characters except underscores
    - Lowercase
    
    Examples:
    - gpt-4.1       -> gpt4_1
    - gpt-4.1-mini  -> gpt4_1mini
    - gpt-4o        -> gpt4o
    - gpt-5.1       -> gpt5_1
    - o1-preview    -> o1preview
    - claude-3.5-sonnet -> claude3_5sonnet
    
    Returns "model" if empty.
    """
    if not model:
        return "model"
    
    # Strip deployment suffix (e.g., "model:deployment")
    name = model.split(":", 1)[0]
    
    # Replace dots with underscores to preserve version info
    name = name.replace(".", "_")
    
    # Remove non-alphanumeric characters except underscores
    token = re.sub(r"[^a-zA-Z0-9_]+", "", name).lower()
    
    # Clean up multiple underscores
    token = re.sub(r"_+", "_", token).strip("_")
    
    return token or "model"
