import re
import yaml
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)

def preprocess_helm_template(yaml_content: str) -> str:
    """Simple preprocessing of Helm templates to prevent yaml.safe_load failure.
    
    EXACT LOGIC FROM evaluationCoverage/compare_filed_new.py
    """
    # Remove {{- ... }} and {{ ... }} blocks
    content = re.sub(r'\{\{-\s*.+?\s*\}\}', '', yaml_content, flags=re.DOTALL)
    content = re.sub(r'\{\{\s*.+?\s*\}\}', '', content, flags=re.DOTALL)
    content = re.sub(r'\.\.\.', '', content, flags=re.DOTALL)

    # Clean empty lines
    lines = content.split('\n')
    cleaned_lines = [line for line in lines if line.strip() != '']
    return '\n'.join(cleaned_lines)

def get_all_keys(data: Any, parent_key: str = '', separator: str = '.') -> Set[str]:
    """Recursively get all field keys from YAML data (flattened and lowercased).
    
    EXACT LOGIC FROM evaluationCoverage/compare_filed_new.py
    """
    keys = set()
    
    if isinstance(data, dict):
        for key, value in data.items():
            # Convert key to lowercase
            key_lower = str(key).lower()
            new_key = f"{parent_key}{separator}{key_lower}" if parent_key else key_lower
            
            # Add current key
            keys.add(new_key)
            
            # Recursive handling
            if isinstance(value, (dict, list)):
                keys.update(get_all_keys(value, new_key, separator))
    
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_key = f"{parent_key}{separator}[{i}]" if parent_key else f"[{i}]"
            
            # Recursive handling
            if isinstance(item, (dict, list)):
                keys.update(get_all_keys(item, new_key, separator))
    
    return keys

# Regex from compare_filed_new.py (Relaxed to support generic blocks)
YAML_BLOCK_REGEX = r"```(?:yaml)?\n(.*?)```"

def extract_yaml(text: str) -> Optional[List[str]]:
    """Extract YAML code blocks from text, supporting multi-doc split.
    
    EXACT LOGIC FROM evaluationCoverage/compare_filed_new.py
    """
    if not text:
        return None
    
    text = str(text)
    # Extract all yaml code blocks
    matches = re.findall(YAML_BLOCK_REGEX, text, re.DOTALL)
    if not matches:
        return None
    
    # Process each block, split multi-doc YAML
    all_yamls = []
    for yaml_block in matches:
        yaml_block = yaml_block.strip()
        if not yaml_block:
            continue
        
        # Split by ---
        docs = re.split(r'\n\s*---\s*\n', yaml_block)
        
        for doc in docs:
            doc = doc.strip()
            # Remove leading ---
            if doc.startswith('---'):
                lines = doc.split('\n', 1)
                if len(lines) > 1 and lines[0].strip() == '---':
                    doc = lines[1].strip()
                elif lines[0].strip() == '---':
                    continue
            
            if doc:
                all_yamls.append(doc)
    
    return all_yamls if all_yamls else None

    return all_yamls if all_yamls else None

def compare_single_pair(gold_yaml_str: str, pred_yaml_str: str) -> Dict[str, Any]:
    """Compare a single pair of YAML strings (Benchmark Logic)."""
    # Preprocess
    gold_str = preprocess_helm_template(gold_yaml_str)
    pred_str = preprocess_helm_template(pred_yaml_str)
    
    try:
        # Parse
        gold_data = yaml.safe_load(gold_str)
        pred_data = yaml.safe_load(pred_str)
        
        if gold_data is None:
            return {'error': 'Gold parsed to None'}
        # Pred can be None (treated as empty)
        
        # Get Keys
        gold_keys = get_all_keys(gold_data)
        if pred_data:
            pred_keys = get_all_keys(pred_data)
        else:
            pred_keys = set()
            
        # Calc
        missing_in_pred = gold_keys - pred_keys
        existing_in_pred = gold_keys & pred_keys
        
        total = len(gold_keys)
        existing = len(existing_in_pred)
        ratio = existing / total if total > 0 else 0
        
        return {
            'total_fields': total,
            'existing_fields': existing,
            'missing_fields': list(missing_in_pred),
            'coverage_ratio': ratio,
            'coverage_percentage': round(ratio * 100, 2),
            'error': None
        }
    except Exception as e:
        return {'error': str(e), 'coverage_percentage': 0.0}


def calculate_coverage(reference_text: str, generated_text: str) -> Dict[str, Any]:
    """Calculate coverage using EXACT benchmark strategy:
       1. Find FIRST valid YAML block in Reference (Gold).
       2. Compare it against ALL Generated (Pred) blocks.
       3. Return the BEST match (highest coverage).
    """
    if not limit_string(reference_text):
        return {'error': 'reference_answer content is empty'}
    
    # 1. Extract YAML blocks
    gold_yamls = extract_yaml(reference_text)
    pred_yamls = extract_yaml(generated_text)
    
    if not gold_yamls:
         return {'error': 'No YAML blocks found in reference answer', 'coverage_percentage': 0.0}

    # 2. Find FIRST valid Gold block
    valid_gold_yaml = None
    for block in gold_yamls:
        # Check validity by trying to parse keys
        res = compare_single_pair(block, block) # Self-check
        if not res.get('error'):
            valid_gold_yaml = block
            break
            
    if not valid_gold_yaml:
        return {'error': 'Reference has YAML blocks but none are valid', 'coverage_percentage': 0.0}

    # 3. If no pred blocks, 0 coverage
    if not pred_yamls:
        # Still need gold stats
        res = compare_single_pair(valid_gold_yaml, "")
        return res

    # 4. Find BEST match in Preds
    best_result = None
    best_coverage = -1.0
    
    for pred_block in pred_yamls:
        res = compare_single_pair(valid_gold_yaml, pred_block)
        
        # Benchmark skips errors in preds silently
        if res.get('error'):
            continue
            
        cov = res.get('coverage_percentage', 0.0)
        if cov > best_coverage:
            best_coverage = cov
            best_result = res
            
    if best_result:
        return best_result
    else:
        # All preds failed or empty
        return compare_single_pair(valid_gold_yaml, "")

def limit_string(s):
    return s and s.strip()

