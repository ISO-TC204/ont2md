# ont2md

Generate a [MkDocs](https://www.mkdocs.org/) site (with ODM-style diagrams) from Turtle ontology files in `docs/`.

The main entry point for Turtle sources is `python/ttl2md.py`. Related scripts (`owl2md.py`, `ofn2md.py`) handle other formats and are not covered here.

## Prerequisites

Run the script from the **project root** (the directory that contains `mkdocs.yml` and `docs/`).

| Requirement | Purpose |
|-------------|---------|
| `mkdocs.yml` | Site configuration; navigation is rewritten on each run |
| `docs/` | Source `.ttl` files and generated Markdown output |
| Python 3 | Runtime |
| [RDFLib](https://rdflib.readthedocs.io/) | Parse and query Turtle |
| [Graphviz](https://graphviz.org/) (`dot` on `PATH`) | Render class diagrams |
| PyYAML | Update `mkdocs.yml` navigation |

Install Python dependencies (minimum):

```bash
pip install rdflib pyyaml graphviz
```

For building the site locally, also install MkDocs (for example [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)) and any plugins referenced in your `mkdocs.yml`.

## Usage

```bash
cd /path/to/your-mkdocs-project   # must contain mkdocs.yml and docs/
python python/ttl2md.py
```

Optional flag:

| Flag | Meaning |
|------|---------|
| `--create-missing` or `-c` | ReqView CSV includes concepts **without** `its-core:reqviewId` (empty `id` column for new ReqView objects). Default: only concepts that already have a ReqView ID. |

No other command-line arguments are accepted. Extra arguments print usage and exit with code `1`.

### Exit behavior

- **Missing `mkdocs.yml` or `docs/`** — error message, exit `1`
- **Invalid Turtle syntax** in a pattern file or optional shared SHACL file — error with line context, exit `2` (no partial site generation)
- **No `.ttl` files in `docs/`** — message and exit `0`
- **Per-class or nav/CSV errors** — logged; other outputs may still be written

## Turtle files in `docs/`

All files matching `docs/*.ttl` (case-insensitive extension) are loaded into one **unified RDF graph**. How each file is treated depends on its **basename**.

### File naming rules

| Pattern | Example | Role |
|---------|---------|------|
| `*-pattern.ttl` | `fuzzy-time-pattern.ttl` | **Pattern module** — overview page, nav section, and classes/properties declared in that file |
| `*-shacl.ttl` | `fuzzy-time-shacl.ttl` | **SHACL constraints** — merged into diagrams and formalization; not a separate nav “pattern” |
| `*-reqview.ttl` | `its-time-reqview.ttl` | **ReqView sidecar** — `its-core:reqviewId` annotations; excluded from site index, pattern pages, and MkDocs nav |
| Other `.ttl` | `core.ttl`, `its-time.ttl` | **Ontology modules** — metadata and locally declared classes/properties; may serve as the site “home” module |

Pattern module keys drop the `-pattern` suffix (for example `fuzzy-time-pattern.ttl` → module name `fuzzy-time`).

### Namespace and “local” concepts

The script determines the **master namespace** from, in order:

1. A `BASE <...>` declaration in any loaded file
2. `vann:preferredNamespaceUri` on an `owl:Ontology`
3. Fallback: `https://w3id.org/itsdata/time/v1/`

Only classes and properties whose IRIs start with that namespace are documented as local pages. Imported concepts appear in diagrams and links but do not get their own generated pages unless they are in the unified graph under that namespace.

Each pattern/module file should use a consistent `BASE` and preferred namespace metadata, as in the sample files under `docs/`.

### Recommended ontology metadata

On each `owl:Ontology` (especially in pattern and home modules):

| Property | Used for |
|----------|----------|
| `dcterms:title` | Pattern/module title and nav labels |
| `skos:definition` or `dcterms:description` | Overview and index text |
| `vann:preferredNamespaceUri` | Namespace resolution |
| `vann:preferredNamespacePrefix` | Home module selection, ReqView CSV filename |
| `its-core:draft` (`true`/`false`) | Draft banner on generated pages |

On classes, prefer `skos:definition`, `skos:example`, and `skos:note` where applicable.

### ReqView traceability

- Annotate concepts with `its-core:reqviewId` (typically in a `*-reqview.ttl` file).
- After each run, the script writes `docs/traceability/<preferredNamespacePrefix>.csv` for manual import into ReqView (“Update existing objects”).
- Without `--create-missing`, rows are emitted only for concepts that already have a ReqView ID.
- `ITSThing` and `TimeThing` are omitted from the CSV.

### Optional shared SHACL

If the file `ontology-its-core/docs/its-sh.ttl` exists at a configured path on the machine running the script, it is parsed when resolving `owl:imports` for pattern modules. Invalid syntax in that file aborts the run (exit `2`).

### Concept registry (optional)

`python/concept_registry.md` can declare extra local properties not fully typed in TTL. The processor may add them to the graph when their URIs fall under the master namespace.

## What the script generates

From the project root, under `docs/`:

| Output | Description |
|--------|-------------|
| `index.md` | Site home (module chosen by `vann:preferredNamespacePrefix` and file layout; see `resolve_home_ontology` in `utils.py`) |
| `classes/<ClassName>.md` | One page per **local** class (name = URI local name, e.g. `FuzzyTime`) |
| `classes/<ModuleName>.md` | Pattern overview for each `*-pattern.ttl` module |
| `properties/<prefix:local>.md` | One page per local object/datatype property |
| `diagrams/<ClassName>.dot.svg` (and related `.dot` / `.png`) | ODM-style diagrams (OWL + SHACL merged) |
| `traceability/<prefix>.csv` | ReqView update export |

`mkdocs.yml` **`nav`** is replaced to reflect patterns (or a flat Classes/Properties layout when no `*-pattern.ttl` files exist).

## Typical workflow

1. Edit Turtle under `docs/` (patterns, SHACL, ReqView sidecars as needed).
2. From the project root, run `python python/ttl2md.py` (add `-c` only when intentionally creating new ReqView objects).
3. Review generated Markdown and diagrams under `docs/`.
4. Build or deploy the site with MkDocs (`mkdocs serve` / `mkdocs build` or your CI workflow).

## Sample layout

This repository’s `docs/` folder illustrates the conventions:

- `core.ttl` — core module and home metadata (`vann:preferredNamespacePrefix` `its-time`)
- `fuzzy-time-pattern.ttl` / `schedule-pattern.ttl` — pattern OWL
- `fuzzy-time-shacl.ttl` / `schedule-shacl.ttl` — SHACL shapes
- `its-time-reqview.ttl` — ReqView IDs

## Related scripts

| Script | Input |
|--------|--------|
| `python/ttl2md.py` | Turtle (`.ttl`) |
| `python/owl2md.py` | RDF/XML (`.owl`) |
| `python/ofn2md.py` | OWL Functional Syntax (`.ofn`) |

All expect the same project layout (`mkdocs.yml`, `docs/`) and share diagram and Markdown generators.
