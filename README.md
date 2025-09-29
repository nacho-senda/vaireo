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

If you plan to export the results to Google Sheets, create a Google Cloud
service account with access to the destination spreadsheet, download its JSON
credentials, and share the sheet with the service account email address.

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

### Exporting directly to Google Sheets

```bash
python scraper.py \
  --google-sheet-id 1c0dlguFV7zmsozEC9haJ0fWdtfRCCgTABIByZwqhQIg \
  --worksheet-id 1115054056 \
  --google-credentials credentials.json
```

The command above publishes the normalised records into the worksheet whose
`gid` matches the provided value, mirroring the column order of the shared
template. When `--google-credentials` is omitted the scraper falls back to the
`GOOGLE_APPLICATION_CREDENTIALS` environment variable. Records are written with
one header row followed by one row per startup; tags are joined as a comma
separated string for readability within the sheet.

### Dry runs during development

```bash
python scraper.py --dry-run --log-level DEBUG
```

Enable `--dry-run` to execute the workflow without writing results to disk. This
is helpful when iterating on new parsers. Pair it with `--log-level DEBUG` to
inspect parsing output and HTTP requests in real time.

## Output schema

Each record emitted by the scraper follows the Vaireo dealflow schema below.
The field names are aligned with the spreadsheet you provided so that the JSON
output can be ingested without additional mapping.

| Campo                     | Descripción                                                                 |
|---------------------------|-----------------------------------------------------------------------------|
| `id`                      | Identificador único de la startup (si la fuente lo expone).                 |
| `nombre`                  | Nombre de la startup.                                                       |
| `sector`                  | Sector principal en el que opera.                                           |
| `sub_sector`              | Subsector o categoría específica.                                           |
| `pais`                    | País de origen.                                                             |
| `estado`                  | Estado o etapa actual (por ejemplo, seed, growth).                          |
| `descripcion`             | Resumen de la propuesta de valor.                                           |
| `website`                 | URL oficial de la compañía.                                                 |
| `tags`                    | Lista de etiquetas libres asociadas a la startup.                           |
| `tecnologia_principal`    | Tecnología central que impulsa la solución.                                 |
| `eficiencia_hidrica`      | Indicador relacionado con eficiencia en el uso de agua.                     |
| `tecnologias_regenerativas` | Tecnologías regenerativas aplicadas.                                      |
| `impacto_medioambiental`  | Resumen del impacto medioambiental positivo.                                |
| `impacto_social`          | Descripción del impacto social.                                             |
| `modelo_digital`          | Información sobre el modelo digital del negocio.                            |
| `indicador_sostenibilidad`| Métrica o señal de sostenibilidad reportada por la fuente.                  |
| `fuente_datos`            | Nombre de la fuente que aportó la información.                              |
| `scraped_at`              | Marca temporal (epoch) del momento de recolección.                          |

Los campos que no estén presentes en la fuente se normalizan como cadenas
vacías (`""`), salvo `tags`, que siempre es una lista. Esto facilita integrar
datos provenientes de fuentes heterogéneas.

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
