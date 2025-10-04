"""
amount_extractor.py
===================

This module implements reusable functions for extracting and normalising
monetary amounts from text (and optionally from images via OCR).
It forms the core of the pipeline described in Problem Statement 8 of
the SDE internship assignment, but is kept free of any web framework
dependencies so that the functions can be imported and tested in
isolation without requiring optional packages such as python-multipart.

Functions provided
------------------

extract_text_from_image
    Perform OCR on an uploaded image using pytesseract when
    available.  Raises a RuntimeError if the necessary libraries
    are missing.

find_numeric_tokens
    Locate numeric tokens (integers, floats or percentages) in a
    piece of text, correct common OCR mistakes and return them along
    with a context snippet.

classify_amounts
    Assign semantic labels to numeric tokens using a simple rule-based
    approach that inspects surrounding words for keywords like
    total, paid or due.

validate_amounts
    VERIFIES arithmetic relationships (paid + due ≈ total_bill) and flags inconsistencies.

The functions return plain Python objects (dataclasses or lists of
dictionaries) so they can be consumed by any web framework or unit
tests.  See amount_detector_service.py for an example of how to
expose these functions via FastAPI.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Union

try:
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False


def extract_text_from_image(file_bytes: bytes) -> str:
    """Attempt to perform OCR on a provided image.

    Raises:
        RuntimeError: If OCR libraries are unavailable.
    """
    if not _OCR_AVAILABLE:
        raise RuntimeError(
            "OCR functionality is not available – please install Pillow and pytesseract or provide a plain text input instead."
        )
    with Image.open(io.BytesIO(file_bytes)) as im:  # type: ignore[name-defined]
        return pytesseract.image_to_string(im)


@dataclass
class Token:
    """Represents a candidate numeric token extracted from the input text."""

    raw: str
    normalized: float
    context: str


def find_numeric_tokens(text: str, window: int = 5) -> Tuple[List[Token], int, int]:
    """Scan text to find numeric tokens and return them with context.

    Args:
        text: The full text to search.
        window: Number of words on either side of the match to include
            in the context snippet.

    Returns:
        A list of ``Token`` objects with raw and normalised values.
    """
    tokens: List[Token] = []
    confusion_map = str.maketrans({
        'O': '0', 'o': '0',
        'l': '1', 'I': '1', 'i': '1',
        'S': '5', 's': '5',
        'B': '8',  'b': '8',
        'Z': '2', 'z': '2',
        ',': '',
                  # Existing: Strip commas (thousands separator)
        ';': '.',
        # NEW: Treat semi-colon as a decimal point
        'E': '3', 'e': '3',
        'g': '9', 'G': '9',
        'A': '4', 'a': '4',
        '|': '1', 
        
    })
    total_tokens = 0
    tokens_corrected = 0
    words = re.findall(r"\S+", text)
    word_bounds: List[Tuple[int, int]] = []
    cursor = 0
    for w in words:
        start = text.find(w, cursor)
        end = start + len(w)
        word_bounds.append((start, end))
        cursor = end
        
        
        
    pattern = re.compile(r"(\d[\dOolISsBZ,]*\d|\d)(?:\.\d+)?%?")
    for match in pattern.finditer(text):
        
        total_tokens += 1
        raw_token = match.group()
        char_index = match.start()
        word_index = next((i for i, (s, e) in enumerate(word_bounds) if s <= char_index < e), 0)
        start_word = max(0, word_index - window)
        end_word = min(len(words), word_index + window + 1)
        context_snippet = " ".join(words[start_word:end_word])
        corrected = raw_token.translate(confusion_map)
        if raw_token != corrected:
            tokens_corrected += 1
        numeric_part = re.sub(r"[^\d\.]+", "", corrected)
        try:
            # Cast to float if decimal is present, otherwise to int then float (to handle large integers correctly)
            value = float(numeric_part) if '.' in numeric_part else float(int(numeric_part))
        except ValueError:
            continue
        tokens.append(Token(raw=raw_token, normalized=value, context=context_snippet))
    return tokens,tokens_corrected,total_tokens


def classify_amounts(tokens: List[Token]) -> List[Dict[str, object]]:
    """Assign semantic labels to normalised tokens based on context.

    The classifier operates in two stages.  First it checks whether
    the raw token contains a percentage sign and labels it as
    ``discount_pct``.  Otherwise it scans the surrounding context
    window (converted to lower case) for keywords.  The order of
    evaluation is chosen so that more specific labels like ``paid`` and
    ``due`` override generic labels like ``total_bill`` when both
    keywords appear in the same snippet.

    Args:
        tokens: List of tokens produced by ``find_numeric_tokens``.

    Returns:
        A list of dictionaries with ``type``, ``value`` and ``source``.
    """
    # Define the ordered keyword rules.  Later entries are only
    # considered if no earlier rule matched.
    rules: List[Tuple[str, List[str]]] = [
         ("total_bill", ["total", "grand", "amount", "balance", "subtotal","grana", "amount", "balance", "subtotal", "t0tal"]),
       
        ("paid", ["paid", "payment", "received", "settled","cash","paid", "paymeni", "receivcd", "settled","cash", "pald"]),
        ("due", ["due", "unpaid", "outstanding", "owed", "balance due"]),        
        ("tax", ["tax", "gst", "cgst", "sgst", "igst"])
        ,
         ("change", ["change", "returned", "overpayment"]),
       
    ]
    results: List[Dict[str, object]] = []
    for tok in tokens:
        # If the original token contains % then it's a discount percentage
        if '%' in tok.raw:
            label = 'discount_pct'
            segment=tok.context
        else:
            # Attempt to narrow the context to the nearest segment delimited
            # by vertical bars or newlines.
            segment = tok.context
            for part in re.split(r"[\|\n]", tok.context):
                if tok.raw in part:
                    segment = part
                    break
            context_lower = segment.lower()
            label = 'other'
            for type_name, keywords in rules:
                if any(kw in context_lower for kw in keywords):
                    label = type_name
                    break
        results.append({
            'type': label,
            'value': tok.normalized,
            'source': segment.strip(),
        })
    return results


def validate_amounts(amounts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """
    Verifies arithmetic relationships (paid + due ≈ total_bill).
    This function implements the "Validation & Reconciliation" guardrail.

    Args:
        amounts: List of classified amount dictionaries.

    Returns:
        A tuple containing the amounts list (potentially with added error entry)
        and a validation status string.
    """
    # Use next() with a default value of None to safely find the values
    total = next((a['value'] for a in amounts if a['type'] == 'total_bill'), None)
    paid = next((a['value'] for a in amounts if a['type'] == 'paid'), None)
    due = next((a['value'] for a in amounts if a['type'] == 'due'), None)

    # Simple check for total consistency
    TOLERANCE = 0.01

    if total is not None and paid is not None and due is not None:
        calculated_total = paid + due
        # Check if total is consistent with paid + due, allowing for float precision
        if abs(total - calculated_total) <= TOLERANCE:
            return amounts, "validation_ok"
        else:
            # Flagging inconsistency (adds a new entry to the amounts list)
            new_amounts = amounts + [
                {"type": "validation_error", "value": total - calculated_total, "source": f"Inconsistency: Total ({total}) != Paid ({paid}) + Due ({due})"}
            ]
            return new_amounts, "validation_inconsistent"

    return amounts, "validation_partial" # Not all fields needed for check were present

