# vaireo

A Python scraper for tracking startups dealflow.

## Getting Started

1. Clone the repository
2. (Recommended) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies: `pip install -r requirements.txt`
4. Run the scraper: `python scraper.py`

## Usage

The scraper exposes a command line interface for configuring which startup
sources to query and where to persist the output. The default configuration
contains a sample JSON feed definition that you can replace with your own
sources.

### Basic scrape

```bash
python scraper.py
```

The command above will fetch all default sources and write normalised dealflow
records to `dealflow.json` in the repository root.

### Selecting specific sources

```bash
python scraper.py --sources sample_api
```

Provide one or more source names to limit execution to only those endpoints.
Source identifiers are defined in `DEFAULT_SOURCES` within `scraper.py`.

### Customising the output

```bash
python scraper.py --output data/dealflow.json --timeout 20
```

Use `--output` to choose a different destination file and `--timeout` to tweak
HTTP request behaviour.

### Dry runs during development

```bash
python scraper.py --dry-run --log-level DEBUG
```

Enable `--dry-run` to execute the workflow without writing results to disk. This
is helpful when iterating on new parsers. Pair it with `--log-level DEBUG` to
inspect parsing output and HTTP requests in real time.

## Extending the scraper

To add a new source:

1. Implement a parser function in `scraper.py` that converts the source's raw
   response into dictionaries containing `name`, `description`, `url`, and
   optional metadata such as `stage`.
2. Create a `SourceConfig` entry and append it to `DEFAULT_SOURCES`.
3. Document the new source in this README so other contributors know how to use
   it.

## Purpose

This project collects and analyzes dealflow data from startup sources.

## Contributing

Feel free to submit pull requests or open issues!
