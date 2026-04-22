# ontology_processor_ttl.py
import os
import logging
import traceback
import re
from rdflib import Graph, RDF, OWL, RDFS, URIRef, Literal
from rdflib.namespace import DC, DCTERMS, SKOS, SH

from utils import (
    get_qname, get_ontology_metadata, _norm_base,
    get_leaf_classes, collect_oneOf, collect_list,
    update_concept_registry, parse_concept_registry
)

log = logging.getLogger("ttl2mkdocs")


def parse_concept_registry(script_dir):
    """Same as before – kept for consistency."""
    registry_path = os.path.join(script_dir, "concept_registry.md")
    if not os.path.exists(registry_path):
        with open(registry_path, 'w', encoding='utf-8') as f:
            f.write("| base_uri | name | type | description |\n|----------|------|------|-------------|\n")
        log.info(f"Created new concept_registry.md in {script_dir}")
        return {}
    content = open(registry_path, 'r', encoding='utf-8').read()
    lines = content.splitlines()
    registry = {}
    in_table = False
    headers = None
    for line in lines:
        if line.strip().startswith('|'):
            if not in_table:
                headers = [h.strip().lower() for h in line.split('|') if h.strip()]
                in_table = True
            elif headers and not line.strip().startswith('|---'):
                values = [v.strip() for v in line.split('|') if v.strip()]
                if len(values) < 3:
                    continue
                try:
                    base_uri = values[headers.index('base_uri')]
                    name = values[headers.index('name')]
                    concept_type = values[headers.index('type')]
                    description = values[headers.index('description')] if 'description' in headers and len(values) > headers.index('description') else ''
                    uri = f"{base_uri}{name}"
                    registry[uri] = {'type': concept_type, 'description': description}
                except Exception:
                    pass
    log.debug(f"Loaded {len(registry)} entries from concept_registry.md")
    return registry


def _extract_master_namespace(ttl_files: list) -> str:
    """Find the true master base namespace from BASE declaration or vann:preferredNamespaceUri."""
    for ttl_path in ttl_files:
        try:
            with open(ttl_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 1. Direct BASE declaration (most reliable for your files)
            base_match = re.search(r'BASE\s+<([^>]+)>', content, re.IGNORECASE)
            if base_match:
                ns = base_match.group(1).rstrip('#/') + '/'
                log.info(f"Found master namespace from BASE: {ns}")
                return ns

            # 2. vann:preferredNamespaceUri on any ontology
            pref_match = re.search(r'vann:preferredNamespaceUri\s+<([^>]+)>', content)
            if pref_match:
                ns = pref_match.group(1).rstrip('#/') + '/'
                log.info(f"Found master namespace from vann:preferredNamespaceUri: {ns}")
                return ns

        except Exception as e:
            log.warning(f"Could not read {ttl_path} for namespace: {e}")

    # Fallback
    log.warning("No BASE or vann:preferredNamespaceUri found – using default")
    return "https://w3id.org/itsdata/time/v1/"


def process_ttl_files(ttl_files: list, errors: list) -> tuple:
    """
    Load ALL .ttl files into ONE unified graph.
    Uses the TRUE master base namespace (from BASE) so local_classes works correctly.
    """
    g = Graph()

    # Load every file
    for ttl_path in ttl_files:
        try:
            g.parse(ttl_path, format='turtle')
            log.info(f"Loaded {os.path.basename(ttl_path)} — total triples now {len(g)}")
        except Exception as e:
            error_msg = f"Failed to parse {ttl_path}: {str(e)}"
            errors.append(error_msg)
            log.error(error_msg)

    if len(g) == 0:
        raise ValueError("No triples loaded from any TTL file")

    # === CRITICAL FIX: Get the master base namespace ===
    ns = _extract_master_namespace(ttl_files)
    log.info(f"Using master base namespace: {ns}")

    # Build prefix map
    prefix_map = dict(g.namespaces())
    if ns not in prefix_map:
        prefix_map[ns] = ":"

    # Registry (only add local properties)
    script_dir = os.path.dirname(os.path.realpath(__file__))
    registry = parse_concept_registry(script_dir)

    for uri, info in registry.items():
        u = URIRef(uri)
        if str(u).startswith(ns):
            if info['type'] == 'object_property':
                g.add((u, RDF.type, OWL.ObjectProperty))
            elif info['type'] == 'datatype_property':
                g.add((u, RDF.type, OWL.DatatypeProperty))

    # Collect classes (OWL + SHACL targets)
    classes = set(g.subjects(RDF.type, OWL.Class)) - {OWL.Thing}
    for shape in g.subjects(RDF.type, SH.NodeShape):
        target = g.value(shape, SH.targetClass)
        if target and isinstance(target, URIRef):
            classes.add(target)

    # Local classes = only those under the master namespace
    local_classes = [cls for cls in classes if str(cls).startswith(ns)]

    log.info(f"Collected {len(classes)} total classes, {len(local_classes)} local classes under master ns")

    # Property map (only local)
    prop_map = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        if str(p).startswith(ns):
            qn = get_qname(p, ns, prefix_map)
            prop_map[qn] = p
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        if str(p).startswith(ns):
            qn = get_qname(p, ns, prefix_map)
            prop_map[qn] = p

    # Add registry properties that belong to this master ns
    for uri, info in registry.items():
        if info['type'] in ('object_property', 'datatype_property') and str(uri).startswith(ns):
            u = URIRef(uri)
            qn = get_qname(u, ns, prefix_map)
            prop_map[qn] = u

    return g, ns, prefix_map, classes, local_classes, prop_map