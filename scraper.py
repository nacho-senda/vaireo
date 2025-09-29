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
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional
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
        yield {
            "name": raw_entry.get("name", ""),
            "description": raw_entry.get("description", ""),
            "url": raw_entry.get("url", ""),
            "stage": raw_entry.get("stage") or raw_entry.get("status"),
            "source": source.name,
        }


def normalise_deal(raw_deal: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise parsed data to a consistent schema.

    Normalisation ensures downstream consumers do not have to worry about
    variations between sources. Add additional fields here if you need them for
    analytics (e.g. geography, industry, founder data).
    """

    return {
        "name": raw_deal.get("name", "").strip(),
        "description": raw_deal.get("description", "").strip(),
        "url": raw_deal.get("url", "").strip(),
        "stage": raw_deal.get("stage") or "unknown",
        "source": raw_deal.get("source", "unknown"),
        "scraped_at": int(time.time()),
    }


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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(list(deals), handle, indent=2, ensure_ascii=False)
    LOGGER.info("Persisted %s deals to %s", output_path, output_path.resolve())


def run_workflow(
    sources: Iterable[SourceConfig],
    *,
    timeout: int,
    output: Optional[pathlib.Path],
    dry_run: bool,
) -> List[Dict[str, Any]]:
    """Execute the end-to-end scraping workflow for the provided sources."""

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

    run_workflow(selected_sources, timeout=args.timeout, output=args.output, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
