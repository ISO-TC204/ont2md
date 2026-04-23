import os
import sys
import logging
import traceback
import re
from collections import defaultdict
from ontology_processor_owl import process_ontology
from diagram_generator import generate_diagram
from markdown_generator import (
    generate_markdown,
    update_mkdocs_nav,
    generate_index,
    generate_pattern_markdown_file,
    generate_property_markdown,
)
from utils import get_qname, get_label, is_abstract, get_id, get_ontology_metadata, insert_spaces, get_preferred_prefix
from rdflib import Graph, RDF, URIRef, Literal, Namespace
from rdflib.namespace import OWL, DCTERMS, SKOS, RDFS, DC

# -------------------- logging --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
log = logging.getLogger("owl2mkdocs")

def main():
    CDM1 = Namespace("https://w3id.org/citydata/part1/v1/")
    ITS_CORE = Namespace("https://w3id.org/itsdata/core/v1/")

    full_title = ""
    log.info("Starting owl2md.py (RDF/XML → MkDocs + ODM diagrams)")

    if len(sys.argv) != 1:
        print("Usage: python owl2mkdocs.py")
        sys.exit(1)

    # Check for mkdocs.yml in current directory
    root_dir = os.getcwd()
    mkdocs_path = os.path.join(root_dir, "mkdocs.yml")
    if not os.path.exists(mkdocs_path):
        print("Error: mkdocs.yml not found in current directory")
        sys.exit(1)

    # Check for docs directory
    docs_dir = os.path.join(root_dir, "docs")
    if not os.path.isdir(docs_dir):
        print("Error: docs directory not found")
        sys.exit(1)

    # Create diagrams directory if it doesn't exist
    diagrams_dir = os.path.join(docs_dir, "diagrams")
    if not os.path.exists(diagrams_dir):
        os.makedirs(diagrams_dir)
        log.info(f"Created diagrams directory: {diagrams_dir}")

    # Find all .owl files in docs directory
    owl_files = [os.path.join(docs_dir, f) for f in os.listdir(docs_dir) if f.lower().endswith('.owl')]
    if not owl_files:
        print("No .owl files found in docs/")
        sys.exit(0)

    errors: list[str] = []
    processed_count = 0

    # === 1) Process each OWL file (with owlready2 inside processor), collect ontology_info + class ownership ===
    ontology_info: dict[str, dict] = {}
    class_to_onts: defaultdict[str, set] = defaultdict(set)
    ns_to_ontology: dict[str, str] = {}
    graphs: dict[str, tuple[Graph, str, dict, set, list, dict]] = {}

    for owl_path in sorted(owl_files):
        ont_name = os.path.splitext(os.path.basename(owl_path))[0]
        per_file_info = {
            "title": insert_spaces(ont_name),
            "full_title": insert_spaces(ont_name),
            "description": "",
            "classes": set(),
            "imports": [],
            "draft": False,
            "file": owl_path,
            "prefix": ont_name,
        }

        g, ns, prefix_map, classes, local_classes, prop_map = process_ontology(owl_path, errors, per_file_info)
        if g is None:
            continue
        graphs[ont_name] = (g, ns, prefix_map, classes, local_classes, prop_map)
        ns_to_ontology[ns] = ont_name

        # Determine main module title if present
        is_main_module = get_ontology_metadata(g, ns, CDM1.mainModule)
        if is_main_module and is_main_module.lower() == "true":
            full_title = (
                get_ontology_metadata(g, ns, DCTERMS.title)
                or get_ontology_metadata(g, ns, DC.title)
                or per_file_info["title"]
            )
            per_file_info["full_title"] = full_title

        # Use local class names
        direct_class_names = set()
        for cls in local_classes:
            if isinstance(cls, URIRef) and str(cls).startswith(ns):
                direct_class_names.add(get_label(g, cls))
        per_file_info["classes"] = direct_class_names

        for cls_name in direct_class_names:
            class_to_onts[cls_name].add(ont_name)

        ontology_info[ont_name] = per_file_info

    if not graphs:
        log.error("No OWL graphs were successfully processed.")
        sys.exit(1)

    # === 2) Unify graphs for cross-file linking/constraints ===
    unified_g = Graph()
    ns = None
    prefix_map = {}
    all_classes: set = set()
    local_classes: list = []
    prop_map: dict = {}

    for _, (g, g_ns, g_prefix_map, classes, locals_, props_) in graphs.items():
        for t in g:
            unified_g.add(t)
        ns = ns or g_ns
        prefix_map.update(g_prefix_map)
        all_classes |= set(classes)
        local_classes += list(locals_)
        prop_map.update(props_)

    local_classes = list({c for c in local_classes if isinstance(c, URIRef)})

    global_all_classes = {get_qname(c, ns, prefix_map) for c in all_classes if c != OWL.Thing}
    abstract_map = {get_qname(c, ns, prefix_map): is_abstract(c, unified_g, ns) for c in all_classes}

    isDraft = any(info.get("draft") for info in ontology_info.values())

    # === 3) Generate diagrams + Markdown for every class ===
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
                "dummy.owl",
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

    # === 4) Generate property pages (local properties only) ===
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

    # === 5) Generate pattern pages + index ===
    preferred_prefix = get_preferred_prefix(unified_g) or ""
    for ont_name, ont in ontology_info.items():
        if ont_name == preferred_prefix:
            generate_index(unified_g, ont_name, ns, prefix_map, ont, docs_dir, ontology_info, errors, class_to_onts, isDraft)
        else:
            generate_pattern_markdown_file(unified_g, ont_name, ns, prefix_map, ont, docs_dir, class_to_onts, ontology_info)

    # === 6) Update mkdocs nav ===
    try:
        update_mkdocs_nav(mkdocs_path, ontology_info, global_all_classes, errors, class_to_onts, ontology_info, owl_files)
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