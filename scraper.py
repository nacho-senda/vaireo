"""Startup dealflow scraper entry point.

This module provides a composable scraping workflow for collecting dealflow
information from multiple startup sources. The architecture is intentionally
modular to make it easy to plug in new sources: define a configuration entry,
implement a parser, and optionally customise the normalisation or persistence
steps.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib import error, request


LOGGER = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for a single startup source.

    Attributes:
        name: Human readable identifier for the source.
        url: HTTP(S) endpoint containing startup dealflow information.
        parser: Callable that converts raw HTTP responses into python
            dictionaries following the :func:`normalise_deal` input schema.
        notes: Optional text describing the source. Helpful when onboarding new
            team members or when the source requires extra context (authentication,
            rate limits, etc.).
    """

    name: str
    url: str
    parser: Callable[[str, "SourceConfig"], Iterable[Dict[str, Any]]]
    notes: Optional[str] = None


def fetch_url(url: str, *, timeout: int = 10) -> str:
    """Retrieve raw text from a URL.

    Parameters
    ----------
    url:
        The URL to fetch. HTTP redirects are handled transparently by
        :mod:`urllib`.
    timeout:
        Timeout for the request in seconds.

    Returns
    -------
    str
        Text response body from the request. An empty string is returned if the
        request fails, allowing the orchestrator to proceed with other sources
        without raising an exception.
    """

    try:
        LOGGER.debug("Fetching URL %s", url)
        with request.urlopen(url, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read()
            return body.decode(charset)
    except error.URLError as exc:
        LOGGER.error("Failed to fetch %s: %s", url, exc)
        return ""


def parse_sample_json(response_text: str, source: SourceConfig) -> Iterable[Dict[str, Any]]:
    """Parse a JSON feed containing startup deals.

    The parser expects the remote endpoint to return a JSON array of objects.
    Each object should contain ``name``, ``description``, ``url`` and optionally
    ``stage`` or ``status`` fields. This example parser is intentionally simple
    to make it easy to copy when adding new sources.
    """

    if not response_text.strip():
        return []

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        LOGGER.error("Source %s did not return valid JSON: %s", source.name, exc)
        return []

    if not isinstance(payload, list):
        LOGGER.warning("Source %s returned a non-list payload: %r", source.name, type(payload))
        return []

    for raw_entry in payload:
        if not isinstance(raw_entry, dict):
            LOGGER.debug("Skipping non-dict entry in %s: %r", source.name, raw_entry)
            continue

        # The example feed might provide either the Spanish field names used by
        # the downstream sheet or the original English ones (``name``,
        # ``description``...).  We normalise here so the rest of the pipeline can
        # rely on a consistent schema.
        yield {
            "id": raw_entry.get("id") or raw_entry.get("uuid") or "",
            "nombre": raw_entry.get("nombre") or raw_entry.get("name", ""),
            "sector": raw_entry.get("sector", ""),
            "sub_sector": raw_entry.get("sub_sector") or raw_entry.get("subsector", ""),
            "pais": raw_entry.get("pais") or raw_entry.get("country", ""),
            "estado": raw_entry.get("estado") or raw_entry.get("stage") or raw_entry.get("status", ""),
            "descripcion": raw_entry.get("descripcion") or raw_entry.get("description", ""),
            "website": raw_entry.get("website") or raw_entry.get("url", ""),
            "tags": raw_entry.get("tags") or raw_entry.get("labels", []),
            "tecnologia_principal": raw_entry.get("tecnologia_principal")
            or raw_entry.get("primary_technology", ""),
            "eficiencia_hidrica": raw_entry.get("eficiencia_hidrica") or "",
            "tecnologias_regenerativas": raw_entry.get("tecnologias_regenerativas")
            or raw_entry.get("regenerative_tech", ""),
            "impacto_medioambiental": raw_entry.get("impacto_medioambiental")
            or raw_entry.get("environmental_impact", ""),
            "impacto_social": raw_entry.get("impacto_social") or raw_entry.get("social_impact", ""),
            "modelo_digital": raw_entry.get("modelo_digital") or raw_entry.get("digital_model", ""),
            "indicador_sostenibilidad": raw_entry.get("indicador_sostenibilidad")
            or raw_entry.get("sustainability_indicator", ""),
            "fuente_datos": raw_entry.get("fuente_datos") or source.name,
        }


OUTPUT_FIELDS = [
    "id",
    "nombre",
    "sector",
    "sub_sector",
    "pais",
    "estado",
    "descripcion",
    "website",
    "tags",
    "tecnologia_principal",
    "eficiencia_hidrica",
    "tecnologias_regenerativas",
    "impacto_medioambiental",
    "impacto_social",
    "modelo_digital",
    "indicador_sostenibilidad",
    "fuente_datos",
    "scraped_at",
]


def _coerce_tags(value: Any) -> List[str]:
    """Convert the ``tags`` field into a normalised list of strings."""

    if not value:
        return []
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    if isinstance(value, (list, tuple, set)):
        normalised: List[str] = []
        for item in value:
            if not item:
                continue
            normalised.append(str(item).strip())
        return normalised
    return [str(value).strip()]


def normalise_deal(raw_deal: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise parsed data to the Vaireo dealflow schema."""

    normalised: Dict[str, Any] = {
        "id": str(raw_deal.get("id", "")).strip(),
        "nombre": raw_deal.get("nombre", "").strip(),
        "sector": raw_deal.get("sector", "").strip(),
        "sub_sector": raw_deal.get("sub_sector", "").strip(),
        "pais": raw_deal.get("pais", "").strip(),
        "estado": raw_deal.get("estado", "").strip(),
        "descripcion": raw_deal.get("descripcion", "").strip(),
        "website": raw_deal.get("website", "").strip(),
        "tags": _coerce_tags(raw_deal.get("tags")),
        "tecnologia_principal": raw_deal.get("tecnologia_principal", "").strip(),
        "eficiencia_hidrica": raw_deal.get("eficiencia_hidrica", "").strip(),
        "tecnologias_regenerativas": raw_deal.get("tecnologias_regenerativas", "").strip(),
        "impacto_medioambiental": raw_deal.get("impacto_medioambiental", "").strip(),
        "impacto_social": raw_deal.get("impacto_social", "").strip(),
        "modelo_digital": raw_deal.get("modelo_digital", "").strip(),
        "indicador_sostenibilidad": raw_deal.get("indicador_sostenibilidad", "").strip(),
        "fuente_datos": raw_deal.get("fuente_datos", "unknown").strip() or "unknown",
        "scraped_at": int(time.time()),
    }

    for field in OUTPUT_FIELDS:
        if field not in normalised:
            normalised[field] = ""

    return normalised


DEFAULT_SOURCES: Dict[str, SourceConfig] = {
    "sample_api": SourceConfig(
        name="Sample Startup API",
        url="https://example.com/api/deals.json",
        parser=parse_sample_json,
        notes=(
            "Replace this entry with the actual API endpoint you want to scrape. "
            "To add more sources, duplicate the SourceConfig entry and point it to your "
            "target endpoint along with a parser function that knows how to interpret the response."
        ),
    ),
}


def persist_to_json(deals: Iterable[Dict[str, Any]], output_path: pathlib.Path) -> None:
    """Write normalised deal data to a JSON file."""

    records = list(deals)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, ensure_ascii=False)
    LOGGER.info("Persisted %s deals to %s", len(records), output_path.resolve())


def persist_to_google_sheet(
    deals: Sequence[Dict[str, Any]],
    spreadsheet_id: str,
    worksheet_id: int,
    *,
    credentials_path: Optional[pathlib.Path] = None,
    clear_worksheet: bool = True,
) -> None:
    """Upload the normalised deals into a Google Sheets worksheet.

    Parameters
    ----------
    deals:
        Normalised dealflow records to upload.
    spreadsheet_id:
        Identifier of the Google Sheets document (visible in the sheet URL).
    worksheet_id:
        Numeric worksheet identifier (``gid``) that receives the data.
    credentials_path:
        Optional path to a service account JSON file. If omitted, the function
        will look for the ``GOOGLE_APPLICATION_CREDENTIALS`` environment
        variable, matching the behaviour of the Google SDKs.
    clear_worksheet:
        Whether to clear the existing contents of the worksheet before writing
        the new payload.
    """

    if not deals:
        LOGGER.info("No deals collected; skipping Google Sheets upload.")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:  # pragma: no cover - import failure is logged
        LOGGER.error("gspread dependencies are required for Google Sheets upload: %s", exc)
        raise

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    credential_source: Optional[pathlib.Path] = None
    if credentials_path:
        credential_source = credentials_path
    else:
        env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if env_path:
            credential_source = pathlib.Path(env_path)

    if not credential_source or not credential_source.exists():
        raise FileNotFoundError(
            "Google Sheets upload requires a service account JSON file. "
            "Provide --google-credentials or set GOOGLE_APPLICATION_CREDENTIALS."
        )

    credentials = Credentials.from_service_account_file(str(credential_source), scopes=scopes)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
    if worksheet is None:
        raise ValueError(f"Worksheet with gid={worksheet_id} not found in spreadsheet {spreadsheet_id}.")

    rows = _format_rows_for_sheet(deals)

    if clear_worksheet:
        worksheet.clear()

    worksheet.update("A1", rows)
    LOGGER.info(
        "Uploaded %s deals to Google Sheets worksheet %s (gid=%s)",
        len(deals),
        worksheet.title,
        worksheet_id,
    )


def _format_rows_for_sheet(deals: Sequence[Dict[str, Any]]) -> List[List[Any]]:
    """Transform normalised dealflow dictionaries into worksheet rows."""

    rows: List[List[Any]] = [OUTPUT_FIELDS]
    for deal in deals:
        row: List[Any] = []
        for field in OUTPUT_FIELDS:
            value = deal.get(field, "")
            if field == "tags" and isinstance(value, list):
                row.append(", ".join(str(tag) for tag in value))
            else:
                row.append(value)
        rows.append(row)
    return rows


def run_workflow(
    sources: Iterable[SourceConfig],
    *,
    timeout: int,
    output: Optional[pathlib.Path],
    dry_run: bool,
    google_sheet_id: Optional[str],
    worksheet_id: Optional[int],
    google_credentials: Optional[pathlib.Path],
) -> List[Dict[str, Any]]:
    """Execute the end-to-end scraping workflow for the provided sources.

    Parameters
    ----------
    sources:
        The set of data sources to scrape.
    timeout:
        HTTP timeout (seconds) applied to each request.
    output:
        Optional JSON file path for persisting the collected payload.
    dry_run:
        When ``True`` the function skips all persistence operations.
    google_sheet_id:
        If provided alongside ``worksheet_id`` the collected records are sent to
        the corresponding Google Sheets document.
    worksheet_id:
        Numeric gid of the worksheet that should be updated.
    google_credentials:
        Optional path to a Google service account JSON file used for
        authentication with the Sheets API.
    """

    collected: List[Dict[str, Any]] = []

    for source in sources:
        LOGGER.info("Scraping %s (%s)", source.name, source.url)
        response_text = fetch_url(source.url, timeout=timeout)
        if not response_text:
            LOGGER.warning("No response received from %s", source.name)
            continue

        for raw_deal in source.parser(response_text, source):
            normalised = normalise_deal(raw_deal)
            collected.append(normalised)

    if output and not dry_run:
        persist_to_json(collected, output)
    elif dry_run:
        LOGGER.info("Dry run enabled; skipping persistence. %s deals collected.", len(collected))

    if google_sheet_id and worksheet_id is not None and not dry_run:
        persist_to_google_sheet(
            collected,
            google_sheet_id,
            worksheet_id,
            credentials_path=google_credentials,
        )
    elif google_sheet_id and worksheet_id is not None and dry_run:
        LOGGER.info(
            "Dry run enabled; skipping Google Sheets upload. %s deals collected.",
            len(collected),
        )
    elif google_sheet_id or worksheet_id is not None:
        LOGGER.warning(
            "Google Sheets upload requested but missing configuration. Provide both "
            "--google-sheet-id and --worksheet-id."
        )

    return collected


def build_parser() -> argparse.ArgumentParser:
    """Create a command line parser for the scraper script."""

    parser = argparse.ArgumentParser(description="Scrape startup dealflow data from multiple sources.")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=list(DEFAULT_SOURCES.keys()),
        help=(
            "Names of the sources to scrape. Available sources: "
            f"{', '.join(sorted(DEFAULT_SOURCES))}. "
            "Add new sources by updating DEFAULT_SOURCES in scraper.py."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout (seconds).",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("dealflow.json"),
        help="Path to write the collected dealflow JSON payload.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect data without writing it to disk.",
    )
    parser.add_argument(
        "--google-sheet-id",
        help="Destination Google Sheets document ID (from the sheet URL).",
    )
    parser.add_argument(
        "--worksheet-id",
        type=int,
        help="Destination worksheet gid within the Google Sheet.",
    )
    parser.add_argument(
        "--google-credentials",
        type=pathlib.Path,
        help="Path to a Google service account JSON file for sheet access.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Configure console logging verbosity.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point orchestrating the scraping workflow.

    The orchestration process performs the following steps:

    1. Parse CLI arguments and select the sources to scrape.
    2. Perform HTTP requests to fetch each source's payload.
    3. Delegate response parsing to the source-specific parser functions.
    4. Normalise the parsed data to a shared schema for downstream consumers.
    5. Persist the results to JSON (unless ``--dry-run`` is enabled).

    To extend the scraper with a new source:

    * Write a parser function that converts the raw HTTP response to the
      dictionary format expected by :func:`normalise_deal`.
    * Create a :class:`SourceConfig` entry referencing the parser and URL.
    * Add the new configuration to ``DEFAULT_SOURCES`` (or surface it via your
      preferred configuration mechanism).
    * Optionally document usage examples in ``README.md`` to help other
      contributors discover the source.

    The CLI also exposes optional flags to push the normalised output directly
    into a Google Sheets worksheet. Provide both ``--google-sheet-id`` and
    ``--worksheet-id`` along with service account credentials to enable this
    behaviour.
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")

    selected_sources: List[SourceConfig] = []
    for source_name in args.sources:
        config = DEFAULT_SOURCES.get(source_name)
        if not config:
            LOGGER.error("Unknown source '%s'. Available sources: %s", source_name, ", ".join(DEFAULT_SOURCES))
            continue
        selected_sources.append(config)

    if not selected_sources:
        LOGGER.error("No valid sources specified. Exiting without scraping.")
        return 1

    run_workflow(
        selected_sources,
        timeout=args.timeout,
        output=args.output,
        dry_run=args.dry_run,
        google_sheet_id=args.google_sheet_id,
        worksheet_id=args.worksheet_id,
        google_credentials=args.google_credentials,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
