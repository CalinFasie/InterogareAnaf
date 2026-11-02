"""Normalizarea diacriticelor romanesti in corespondentele latine.

Mapare explicita (fara NFD pe tot textul): afecteaza doar caracterele
romanesti specificate in SPEC si pastreaza intacte celelalte simboluri,
punctuarea, cifrele si spatiile semnificative.
"""

_TRANSLIT = {
    "ă": "a",
    "Ă": "A",
    "â": "a",
    "Â": "A",
    "î": "i",
    "Î": "I",
    "ș": "s",
    "ş": "s",
    "Ș": "S",
    "Ş": "S",
    "ț": "t",
    "ţ": "t",
    "Ț": "T",
    "Ţ": "T",
}

# str.translate primeste mapping cu chei pe puncte de cod (int).
TRANSLIT_TABLE = {ord(key): value for key, value in _TRANSLIT.items()}


def normalize(value):
    """Returneaza textul cu diacriticele romanesti transliterate sau None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.translate(TRANSLIT_TABLE)
    return value
