"""ANAF TVA v9 JSON transport and conservative response interpretation."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .normalization import normalize_text
from .storage import update_anaf_fields

DEFAULT_API_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
MAX_BATCH_SIZE = 100
MAX_ATTEMPTS = 3
_FIELD_MAP = (
    ("date_generale", "denumire", 0),
    ("date_generale", "nrRegCom", 1),
    ("adresa_sediu_social", "sdenumire_Localitate", 2),
    ("adresa_sediu_social", "sdenumire_Strada", 3),
    ("adresa_sediu_social", "snumar_Strada", 4),
    ("adresa_sediu_social", "scod_Localitate", 5),
    ("adresa_sediu_social", "sdenumire_Judet", 6),
    ("adresa_sediu_social", "sdetalii_Adresa", 7),
    ("adresa_sediu_social", "scod_Postal", 8),
)


class RequestFailure(Exception):
    """A request failed after the permitted retries or returned invalid JSON."""


class ProtocolFailure(Exception):
    """The response has no usable top-level found/notFound structure."""


class RequestPacer:
    """Keep request start times at least one second apart per client."""

    def __init__(self, interval: float = 1.0, clock=time.monotonic, sleeper=time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleeper = sleeper
        self.next_start = 0.0

    def wait(self, extra_delay: float = 0.0) -> float:
        now = self.clock()
        delay = max(0.0, self.next_start - now, extra_delay)
        if delay:
            self.sleeper(delay)
        started = self.clock()
        self.next_start = started + self.interval
        return started


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


@dataclass(frozen=True)
class BatchResponse:
    payload: dict
    attempts: int


class AnafClient:
    def __init__(self, api_url: str = DEFAULT_API_URL, timeout: float = 20.0,
                 opener=urlopen, pacer: RequestPacer | None = None):
        self.api_url = api_url
        self.timeout = timeout
        self.opener = opener
        self.pacer = pacer or RequestPacer()
        self.request_count = 0

    def fetch(self, cuis: list[int], query_date: str) -> BatchResponse:
        if not cuis or len(cuis) > MAX_BATCH_SIZE:
            raise ValueError("Lotul trebuie sa contina intre 1 si 100 CUI")
        body = json.dumps(
            [{"cui": cui, "data": query_date} for cui in cuis],
            separators=(",", ":"),
        ).encode("utf-8")
        retry_delay = 0.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.pacer.wait(retry_delay)
            self.request_count += 1
            request = Request(
                self.api_url,
                data=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read()
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RequestFailure("raspuns JSON invalid") from exc
                if not isinstance(payload, dict):
                    raise RequestFailure("raspuns JSON invalid")
                return BatchResponse(payload, attempt)
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                retry_after = _retry_after_seconds(exc.headers.get("Retry-After"))
                exc.close()
                if not retryable:
                    raise RequestFailure(f"HTTP {exc.code} permanent") from exc
                retry_delay = retry_after
                if retry_delay is None:
                    retry_delay = float(attempt)
                if attempt == MAX_ATTEMPTS:
                    raise RequestFailure(f"HTTP {exc.code} dupa {attempt} incercari") from exc
            except (TimeoutError, OSError, URLError) as exc:
                if attempt == MAX_ATTEMPTS:
                    raise RequestFailure(f"eroare de conexiune dupa {attempt} incercari") from exc
                retry_delay = float(attempt)
        raise RequestFailure("cererea a esuat")


@dataclass
class ApplyResult:
    found: int = 0
    not_found: int = 0
    incomplete: int = 0
    anomalies: int = 0


def _valid_cui(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def apply_payload(path, requested: list[int], payload: dict) -> ApplyResult:
    """Validate a response then update only complete, unambiguous found entries."""
    if not isinstance(payload.get("found"), list) or not isinstance(payload.get("notFound"), list):
        raise ProtocolFailure("raspuns fara liste found si notFound valide")

    requested_set = set(requested)
    found_entries: dict[int, tuple[str | None, ...]] = {}
    found_counts: Counter[int] = Counter()
    invalid_found: set[int] = set()
    anomalies = 0
    for entry in payload["found"]:
        if not isinstance(entry, dict):
            anomalies += 1
            continue
        general = entry.get("date_generale")
        cui = _valid_cui(general.get("cui")) if isinstance(general, dict) else None
        if cui is None:
            anomalies += 1
            continue
        found_counts[cui] += 1
        if cui not in requested_set:
            anomalies += 1
            continue
        address = entry.get("adresa_sediu_social")
        if not isinstance(general, dict) or not isinstance(address, dict):
            invalid_found.add(cui)
            anomalies += 1
            continue
        values: list[str | None] = [None] * 9
        valid = True
        for object_name, key, index in _FIELD_MAP:
            source = general if object_name == "date_generale" else address
            value = source.get(key)
            if value is None or value == "":
                values[index] = None
            elif isinstance(value, str):
                values[index] = normalize_text(value)
            else:
                valid = False
                break
        if valid:
            found_entries[cui] = tuple(values)
        else:
            invalid_found.add(cui)
            anomalies += 1

    not_found_counts: Counter[int] = Counter()
    for value in payload["notFound"]:
        cui = _valid_cui(value)
        if cui is None or cui not in requested_set:
            anomalies += 1
            continue
        not_found_counts[cui] += 1
        if not_found_counts[cui] > 1:
            anomalies += 1

    duplicate_found_anomalies = sum(count - 1 for count in found_counts.values() if count > 1)
    result = ApplyResult(anomalies=anomalies + duplicate_found_anomalies)
    for cui in requested:
        is_found = found_counts[cui] > 0
        is_not_found = not_found_counts[cui] > 0
        duplicate = found_counts[cui] > 1 or not_found_counts[cui] > 1
        conflict = is_found and is_not_found
        if is_found and is_not_found:
            result.anomalies += 1
        if is_found and not duplicate and not conflict and cui not in invalid_found and cui in found_entries:
            update_anaf_fields(path, cui, found_entries[cui])
            result.found += 1
        elif is_not_found and not is_found and not duplicate:
            result.not_found += 1
        else:
            result.incomplete += 1
    return result
