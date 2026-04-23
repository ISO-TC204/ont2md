import os
import sys
import logging
import traceback
from collections import defaultdict

from ontology_processor_ofn import process_ontology
from diagram_generator import generate_diagram
from markdown_generator import (
    generate_markdown,
    update_mkdocs_nav,
    generate_index,
    generate_pattern_markdown_file,
    generate_property_markdown,
)
from utils import get_qname, get_label, is_abstract, get_id, insert_spaces, get_preferred_prefix
from rdflib import RDF, OWL, URIRef, Graph, Literal
from rdflib.namespace import DCTERMS, SKOS, VANN

# -------------------- logging --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
log = logging.getLogger("ofn2mkdocs")

def main():
    log.info("Starting ofn2md.py (OFN → MkDocs + ODM diagrams)")

    if len(sys.argv) != 1:
        print("Usage: python ofn2mkdocs.py")
        sys.exit(1)

    root_dir = os.getcwd()
    mkdocs_path = os.path.join(root_dir, "mkdocs.yml")
    if not os.path.exists(mkdocs_path):
        print("Error: mkdocs.yml not found in current directory")
        sys.exit(1)

    docs_dir = os.path.join(root_dir, "docs")
    if not os.path.isdir(docs_dir):
        print("Error: docs directory not found")
        sys.exit(1)

    ofn_files = [os.path.join(docs_dir, f) for f in os.listdir(docs_dir) if f.lower().endswith('.ofn')]
    if not ofn_files:
        print("No .ofn files found in docs/")
        sys.exit(0)

    # Create diagrams directory
    diagrams_dir = os.path.join(docs_dir, "diagrams")
    os.makedirs(diagrams_dir, exist_ok=True)

    errors: list[str] = []

    # === 1) Process each OFN into its own graph; collect ontology_info + class ownership ===
    ontology_info: dict[str, dict] = {}
    class_to_onts: defaultdict[str, set] = defaultdict(set)
    ns_to_ontology: dict[str, str] = {}

    graphs: dict[str, tuple[Graph, str, dict, set, list, dict]] = {}

    for ofn_path in sorted(ofn_files):
        ont_name = os.path.splitext(os.path.basename(ofn_path))[0]
        log.info("Processing OFN: %s", ofn_path)

        per_file_info = {
            "title": insert_spaces(ont_name),
            "full_title": insert_spaces(ont_name),
            "description": "",
            "classes": set(),
            "imports": [],
            "draft": False,
            "file": ofn_path,
            "prefix": ont_name,
        }

        g, ns, prefix_map, classes, local_classes, prop_map = process_ontology(ofn_path, errors, per_file_info)
        if g is None:
            continue

        graphs[ont_name] = (g, ns, prefix_map, classes, local_classes, prop_map)
        ns_to_ontology[ns] = ont_name

        # Capture preferred prefix when present
        preferred_prefix = None
        for s in g.subjects(RDF.type, OWL.Ontology):
            for pref in g.objects(s, VANN.preferredNamespacePrefix):
                preferred_prefix = str(pref).strip()
                break
            if preferred_prefix:
                break
        if preferred_prefix:
            per_file_info["prefix"] = preferred_prefix

        # Title/desc/draft from RDF when present
        title = None
        for s in g.subjects(RDF.type, OWL.Ontology):
            t = g.value(s, DCTERMS.title) or g.value(s, DCTERMS.alternative)
            if isinstance(t, Literal):
                title = str(t)
                break
        if title:
            per_file_info["title"] = title
            per_file_info["full_title"] = title

        desc = None
        for s in g.subjects(RDF.type, OWL.Ontology):
            d = g.value(s, SKOS.definition) or g.value(s, DCTERMS.description)
            if isinstance(d, Literal):
                desc = str(d)
                break
        if desc:
            per_file_info["description"] = desc

        # Direct classes defined locally in this file (ns filter)
        direct_class_names = set()
        for cls in local_classes:
            if isinstance(cls, URIRef) and str(cls).startswith(ns):
                direct_class_names.add(get_label(g, cls))
        per_file_info["classes"] = direct_class_names

        for cls_name in direct_class_names:
            class_to_onts[cls_name].add(ont_name)

        ontology_info[ont_name] = per_file_info

    if not graphs:
        log.error("No OFN graphs were successfully processed.")
        sys.exit(1)

    # Choose a master graph (union) for cross-file linking/constraints
    unified_g = Graph()
    ns = None
    prefix_map: dict = {}
    all_classes: set = set()
    local_classes: list = []
    prop_map: dict = {}

    for ont_name, (g, g_ns, g_prefix_map, classes, locals_, props_) in graphs.items():
        for t in g:
            unified_g.add(t)
        ns = ns or g_ns
        prefix_map.update(g_prefix_map)
        all_classes |= set(classes)
        local_classes += list(locals_)
        prop_map.update(props_)

    local_classes = list({c for c in local_classes if isinstance(c, URIRef)})

    # Global collections used by diagram/markdown
    global_all_classes = {get_qname(c, ns, prefix_map) for c in all_classes if c != OWL.Thing}
    abstract_map = {get_qname(c, ns, prefix_map): is_abstract(c, unified_g, ns) for c in all_classes}

    # Draft flag: if any ontology is draft, watermark everything
    isDraft = any(info.get("draft") for info in ontology_info.values())

    processed_count = 0

    # === 2) Generate diagrams + Markdown class pages ===
    for cls in sorted(local_classes, key=lambda u: get_label(unified_g, u).lower()):
        cls_name = get_label(unified_g, cls)
        if cls_name == "ITSThing":
            continue
        cls_id = get_id(cls_name.replace(":", "_"))
        try:
            generate_diagram(
                unified_g,
                cls,
                cls_name,
                cls_id,
                ns,
                global_all_classes,
                abstract_map,
                "dummy.ofn",
                errors,
                prefix_map,
                "",
                ns_to_ontology,
            )
            generate_markdown(
                unified_g,
                cls,
                cls_name,
                global_all_classes,
                ns,
                docs_dir,
                errors,
                prefix_map,
                ns_to_ontology,
                class_to_onts,
                isDraft,
            )
            processed_count += 1
        except Exception as e:
            error_msg = f"Error processing class {cls_name}: {str(e)}\n{traceback.format_exc()}"
            errors.append(error_msg)
            log.error(error_msg)

    # === 3) Generate property pages (local properties only) ===
    prop_dir = os.path.join(docs_dir, "properties")
    os.makedirs(prop_dir, exist_ok=True)
    for prop_qname, prop_uri in prop_map.items():
        if str(prop_uri).startswith(ns):
            generate_property_markdown(
                unified_g,
                prop_uri,
                prop_qname,
                ns,
                prefix_map,
                docs_dir,
                global_all_classes,
                isDraft,
            )

    # === 4) Generate pattern pages + index ===
    preferred_prefix = get_preferred_prefix(unified_g) or ""
    for ont_name, ont in ontology_info.items():
        if ont_name == preferred_prefix:
            generate_index(unified_g, ont_name, ns, prefix_map, ont, docs_dir, ontology_info, errors, class_to_onts, isDraft)
        else:
            generate_pattern_markdown_file(unified_g, ont_name, ns, prefix_map, ont, docs_dir, class_to_onts, ontology_info)

    # === 5) Update mkdocs navigation ===
    try:
        update_mkdocs_nav(mkdocs_path, ontology_info, global_all_classes, errors, class_to_onts, ontology_info, ofn_files)
    except Exception as e:
        error_msg = f"Error updating mkdocs.yml: {str(e)}\n{traceback.format_exc()}"
        errors.append(error_msg)
        log.error(error_msg)

    log.info("Total processed classes: %d", processed_count)
    if errors:
        log.error("Errors occurred:")
        for err in errors:
            log.error(err)

if __name__ == "__main__":
    main()