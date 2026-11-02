"""Client ANAF TVA v9: cereri HTTP POST, retry si parsarea raspunsului.

Doar biblioteca standard (urllib). Fara apeluri la instalare; testele
folosesc servere locale pe 127.0.0.1.
"""

import http.client
import json
import urllib.error
import urllib.request

from .normalize import normalize

DEFAULT_API_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
MAX_CUIS_PER_REQUEST = 100
MAX_ATTEMPTS = 3
REQUEST_INTERVAL = 1.0
# Pacing garantat: intervalul minim de 1s are o marja, pentru ca serverul
# masoara primirea cererii abia dupa ce clientul a pornit trimiterea.
PACE_MARGIN = 0.15


class AnafError(Exception):
    """Eroare de transport/HTTP, cu clasificarea necesara istoricului."""

    def __init__(self, kind, http_status=None, cod=None, message="", retry_after=None):
        super().__init__(message or cod or kind)
        self.kind = kind  # "timeout" | "connection" | "http"
        self.http_status = http_status
        self.cod = cod
        self.message = message
        self.retry_after = retry_after

    @property
    def transient(self):
        """Clasele reintoarce: timeout, conexiune, HTTP 429 si 5xx."""
        if self.kind in ("timeout", "connection"):
            return True
        if self.kind == "http":
            return self.http_status == 429 or (
                self.http_status is not None and 500 <= self.http_status <= 599
            )
        return False


class InvalidJson(AnafError):
    """Raspuns HTTP valabil, dar corpul nu este JSON valid (eroare permanenta)."""

    def __init__(self, http_status):
        super().__init__("http", http_status, "JSON_INVALID", "Raspuns JSON invalid")

    @property
    def transient(self):
        return False


def post_batch(api_url, cuits, date, timeout):
    """Trimite un lot (max 100 CUI) si intoarce (status, corp bytes).

    Ridica AnafError pentru timeout, eroare de conexiune sau HTTP >= 400.
    """
    payload = json.dumps(
        [{"cui": cui, "data": date} for cui in cuits], ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        retry_after = _parse_retry_after(error.headers.get("Retry-After"))
        raise AnafError(
            "http", error.code, "HTTP_" + str(error.code),
            "HTTP " + str(error.code), retry_after,
        ) from None
    except TimeoutError:
        raise AnafError("timeout", None, "TIMEOUT", "timeout la cerere HTTP") from None
    except (http.client.HTTPException, ConnectionResetError, OSError) as error:
        kind = "timeout" if isinstance(error, http.client.HTTPException) else "connection"
        cod = "TIMEOUT" if kind == "timeout" else "CONNECTION"
        raise AnafError(kind, None, cod, str(error)) from None
    except UnicodeDecodeError:
        raise InvalidJson(200) from None


def _parse_retry_after(value):
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


_FIELD_SOURCES = (
    ("denumire_anaf", "date_generale", "denumire"),
    ("nrRegCom", "date_generale", "nrRegCom"),
    ("sdenumire_Localitate", "adresa_sediu_social", "sdenumire_Localitate"),
    ("sdenumire_Strada", "adresa_sediu_social", "sdenumire_Strada"),
    ("snumar_Strada", "adresa_sediu_social", "snumar_Strada"),
    ("scod_Localitate", "adresa_sediu_social", "scod_Localitate"),
    ("sdenumire_Judet", "adresa_sediu_social", "sdenumire_Judet"),
    ("sdetalii_Adresa", "adresa_sediu_social", "sdetalii_Adresa"),
    ("scod_Postal", "adresa_sediu_social", "scod_Postal"),
)


def _clean_value(raw):
    """Valoare persistabila: text normalizat, numar simplu; None altfel."""
    if raw is None:
        return None
    if isinstance(raw, str):
        cleaned = normalize(raw)
        return cleaned if cleaned != "" else None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and raw.is_integer():
            return str(int(raw))
        return str(raw)
    return None


def parse_response(body, sent_cuis):
    """Extrage doar cele 9 campuri dintr-un raspuns ANAF valid.

    Intoarce (found, notfound, incomplete, anomalies):
    - found: dict kui -> {coloana: valoare} pentru elemente complete si valide;
    - notfound: CUI-uri din notFound care sunt in lotul trimis;
    - incomplete: CUI-uri trimise care nu au un element found valid (T10/T13);
    - anomalies: mesaje de raportare pentru CUI strain/duplicat, liste necunoscute etc.
    """
    sent_set = set(sent_cuis)
    try:
        text = body.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        raise InvalidJson(None) from None
    try:
        data = json.loads(text)
    except ValueError:
        raise InvalidJson(None) from None

    if not isinstance(data, dict):
        return {}, [], sorted(sent_set), ["structura raspuns invalida"]

    found_raw = data.get("found")
    notfound_raw = data.get("notFound")
    if found_raw is None:
        found_raw = []
    if not isinstance(found_raw, list):
        found_raw = []
    if notfound_raw is None:
        notfound_raw = []
    if not isinstance(notfound_raw, list):
        notfound_raw = []

    anomalies = []
    found = {}
    seen = set()
    for element in found_raw:
        if not isinstance(element, dict):
            anomalies.append("element found cu structura invalida")
            continue
        generales = element.get("date_generale")
        if not isinstance(generales, dict):
            anomalies.append("date_generale cu structura invalida")
            continue
        cui = generales.get("cui")
        if isinstance(cui, bool) or not isinstance(cui, int):
            anomalies.append("cui invalid in date_generale")
            continue
        if cui not in sent_set:
            anomalies.append("CUI strain in found: " + str(cui))
            continue
        if cui in seen:
            anomalies.append("CUI duplicat in found: " + str(cui))
            seen.discard(cui)
            found.pop(cui, None)
            continue
        subobjects_ok = isinstance(element.get("adresa_sediu_social"), dict)
        values = {}
        for column, section, key in _FIELD_SOURCES:
            source = generales if section == "date_generale" else element.get(section)
            if not isinstance(source, dict):
                values[column] = None
                continue
            values[column] = _clean_value(source.get(key))
        seen.add(cui)
        if values.get("denumire_anaf") is None and not subobjects_ok:
            # element gasit dar structura incompleta: tratat INCOMPLET (T10)
            anomalies.append("CUI cu subobiecte incomplete: " + str(cui))
            seen.discard(cui)
            found.pop(cui, None)
            continue
        found[cui] = values

    notfound = []
    for cui in notfound_raw:
        if isinstance(cui, bool) or not isinstance(cui, int):
            continue
        if cui in sent_set and cui not in notfound:
            notfound.append(cui)

    incomplete = [cui for cui in sent_set if cui not in found and cui not in notfound]
    return found, notfound, incomplete, anomalies


def split_batches(cuis, size=MAX_CUIS_PER_REQUEST):
    return [cuis[i:i + size] for i in range(0, len(cuis), size)]
