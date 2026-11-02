"""Text normalization shared by CSV import and ANAF response handling."""

import unicodedata

_ROMANIAN_DIACRITICS = str.maketrans({
    "ă": "a", "Ă": "A", "â": "a", "Â": "A",
    "î": "i", "Î": "I", "ș": "s", "Ș": "S",
    "ş": "s", "Ş": "S", "ț": "t", "Ț": "T",
    "ţ": "t", "Ţ": "T",
})


def normalize_text(value: str) -> str:
    """Replace Romanian diacritics while preserving all other text verbatim."""
    return unicodedata.normalize("NFC", value).translate(_ROMANIAN_DIACRITICS)
