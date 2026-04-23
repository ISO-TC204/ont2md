# Ontology Project Rules - RITSO / ITS Data (TTL + SHACL + MkDocs)

You are an expert Python developer specializing in semantic web technologies:

- OWL 2
- SHACL
- Functional Syntax
- RDF/XML
- TURTLE
- RDFLib
- Graphviz (ODM-style diagrams)
- MkDocs + Markdown documentation generation

## Overview

This project attempts to produce a script that converts ontology files into a website that supports SVG and PNG diagrams where each diagram resembles an ODM diagram (i.e., it does not have to strictly conform). The strategy is to convert the ontology files into a series of DOT files and then render the DOT files with GraphViz. Each class will have one or more diagrams showing

1. its class,
2. its datatype properties as attributes,
3. its parent classes as generalized classes on top,
4. its object properties as class associations,
5. refinements to inherited object properties as dashed line associations to classes, and
6. refinements to datatype properities as stereotyped attributes.

Our goal is to produce a python script that will automate this process.

The website will be produced from our generated markdown files using Material for MkDocs. The source ontology is currently TURTLE (*.ttl), but will eventually be extended to support RDF/XML, eventually. A sample set of ontology files is provided in the docs directory using preferred annotation properties. The markdown files will include:

- an index for the entire site
- a page for each pattern (i.e., file containing a portion of the OW ontology)
- a page for each class
- a page for each property

## Core Principles

- Clearly identify all proposed modification to code; never change code without clear notification
- If directions change the instructions of this file, confirm and then also suggest updating this file

## Key Files & Their Purpose

- `utils.py` → helper functions (`get_qname`, `hyperlink_concept`, `get_shacl_constraints`, etc.)
- `diagram_generator.py` → Graphviz ODM diagram generation
- `markdown_generator.py` → Markdown page generation for classes and properties
- `ontology_processor_ttl.py` → loading and processing TTL files
- `ttl2md.py` → main orchestration script for ttl

File to worry about in the future:

- `ontology_processor_owl.py` → loading and processing RDF/XML files
- `ontology_processor_ofn.py` → loading and processing functional syntax files
- `owl2md.py` → main orchestration script for owl
- `ofn2md.py` → main orchestration script for functional syntax

## Coding Style

- Use type hints where possible (`g: Graph`, `cls: URIRef`, etc.)
- Keep functions focused and well-documented
- When modifying functions, try to maintain backward compatibility with existing calls, espeically for thos ein utils.py
- For properties, always generate pages under `docs/properties/`
- When creating hyperlinks for properties, use `properties/{qname}.md`

## SHACL Handling

- `sh:class` + cardinality → "exactly N ClassName"
- `sh:datatype` + cardinality → "exactly N xsd:duration"
- `sh:node` shapes should be merged with property shape constraints
- Prefer human-readable output in Formalization tables

## Hyperlinking Rules

- Local classes → base website + `/{name}.md`
- Local properties → base website + `/properties/{name}.md`
- External concepts → appropriate external URL or imported path

## Diagram Style

- Use Graphviz HTML-like labels (`<<TABLE>>`)
- Keep diagrams clean and ODM-compliant
- Merge OWL restrictions and SHACL constraints intelligently

Always think step-by-step and show clear before/after code when suggesting changes.
