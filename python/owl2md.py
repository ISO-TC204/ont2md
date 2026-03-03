# owl2mkdocs.py
import os
import sys
import logging
import traceback
import re
from collections import defaultdict
from ontology_processor_owl import process_ontology
from diagram_generator import generate_diagram
from markdown_generator import generate_markdown, update_mkdocs_nav, generate_index
from utils import get_qname, get_label, is_abstract, get_id, get_ontology_metadata, insert_spaces
from rdflib import Graph, RDF, XSD, URIRef, Literal, Namespace
from rdflib.namespace import OWL, DCTERMS, SKOS, RDFS, DC

# -------------------- logging --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s")
log = logging.getLogger("owl2mkdocs")

def generate_pattern_markdown(ont_name: str, ont: dict, docs_dir: str, class_to_onts: defaultdict, ontology_info: dict):
    """Generate the per-pattern Markdown page, now including imported patterns."""
    filename = os.path.join(docs_dir, f"{ont_name}.md")
    title = f"# {insert_spaces(ont_name)}\n\n"
    desc = ont["description"] or ""
    top_desc = f"{desc}\n\n" if desc else ""

    # === NEW: Imports section ===
    imports_md = ""
    if ont.get("imports"):
        imports_md = "This pattern imports the following patterns:\n\n"
        for imp_name in sorted(ont["imports"]):
            display = insert_spaces(imp_name)
            if imp_name in ontology_info:                     # local pattern → link to its .md
                imports_md += f"- [{display}]({imp_name}.md)\n"
            else:                                             # external / unknown → plain text
                imports_md += f"- {display}\n"
        imports_md += "\n"

    members_md = "This pattern consists of the following classes:\n\n"
    i = 0
    for cls_name in sorted(ont["classes"], key=str.lower):
        if cls_name == 'ITSThing':
            continue
        i += 1
        display_cls = insert_spaces(cls_name)
        if len(class_to_onts[cls_name]) > 1:
            display_cls += f" ({ont_name})"
        members_md += f"- [{display_cls}]({cls_name}.md)\n"
    if i == 0:
        members_md = "This pattern does not contain any classes.\n\n"
    filename_owl = ont_name + ".owl"
    formal = f"\nThe formal definition of this pattern is available in [{os.path.splitext(filename_owl)[1][1:].upper()} Syntax]({filename_owl}).\n\n"
    content = title + top_desc + imports_md + members_md + formal
    with open(filename, "w", encoding="utf-8") as f:
#        f.write("![Draft for review only](/assets/img/draft_for_review.svg)\n\n")
        f.write(content)
    log.info("Generated pattern Markdown at %s", filename)

def main():
    CDM1 = Namespace("https://w3id.org/citydata/part1/v1/")
    full_title = ""
    log.info("Starting owl2mkdocs.py")
    # Check if script is called without arguments
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

    # Initialize global collections
    global_patterns = defaultdict(list)
    global_all_classes = set()
    abstract_map = {}
    ontology_info = defaultdict(dict)
    errors = []
    processed_count = 0
    class_to_onts = defaultdict(list)

    # Step 1: Parse each file for metadata and classes (using rdflib to avoid import errors)
    ns_to_ontology = {}
    for owl_path in sorted(owl_files):
        ontology_name = os.path.splitext(os.path.basename(owl_path))[0]
        log.debug("Extracting metadata and classes from %s", owl_path)
        temp_g = Graph()
        with open(owl_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace(' xml:', ' xmlns:')
        content = content.replace('rdf:about=":', 'rdf:about="')
        content = content.replace('rdf:resource=":', 'rdf:resource="')
        try:
            temp_g.parse(data=content, format='xml')
            log.debug("Parsed %s with %d triples for metadata/classes", owl_path, len(temp_g))
        except Exception as e:
            log.warning("XML parse failed for %s: %s", owl_path, str(e))
            continue

        # Get ns from ontology IRI or default xmlns
        ns = None
        default_ns_match = re.search(r'xmlns\s*=\s*"([^"]+)"', content)
        if default_ns_match:
            ns = default_ns_match.group(1)
        else:
            for s in temp_g.subjects(RDF.type, OWL.Ontology):
                ns = str(s)
                break
        if not ns:
            ns = "https://w3id.org/citydata/part1/v1/"
        # Normalize to base namespace (remove last segment if pattern name appended)
        if ns.endswith('/'):
            ns = ns.rstrip('/')
        last_segment = ns.rsplit('/', 1)[-1]
        if last_segment == ontology_name or last_segment == ontology_name.lower():
            ns = ns.rsplit('/', 1)[0] + '/'
        else:
            ns += '/'
        log.debug("Normalized ns for %s: %s", ontology_name, ns)


        title = get_ontology_metadata(temp_g, ns, DCTERMS.alternative) or get_ontology_metadata(temp_g, ns, DCTERMS.title) or insert_spaces(ontology_name)
        is_main_module = get_ontology_metadata(temp_g, ns, CDM1.mainModule)
        if is_main_module and is_main_module.lower() == 'true':
            full_title = get_ontology_metadata(temp_g, ns, DCTERMS.title) or get_ontology_metadata(temp_g, ns, DC.title) or title
        log.info("Extracted title for %s: %s", ontology_name, full_title)
        desc = get_ontology_metadata(temp_g, ns, SKOS.definition) or get_ontology_metadata(temp_g, ns, DCTERMS.description) or ""

        # Collect defined classes
        classes_temp = set(temp_g.subjects(RDF.type, OWL.Class)) - {OWL.Thing}
        defined_classes = []
        for c in classes_temp:
            if (temp_g.value(c, RDFS.label) is not None or
                temp_g.value(c, DCTERMS.description) is not None or
                temp_g.value(c, SKOS.definition) is not None or
                list(temp_g.objects(c, RDFS.subClassOf))):
                defined_classes.append(c)
        log.debug("Found %d defined classes in %s", len(defined_classes), owl_path)

        local_classes_temp = set()
        for c in defined_classes:
            c_str = str(c)
            if c_str.startswith(ns):
                cls_name = get_label(temp_g, c)
                if cls_name != 'ITSThing':
                    local_classes_temp.add(cls_name)
                    log.debug("Added class to %s: %s (URI: %s)", ontology_name, cls_name, c_str)
            else:
                log.debug("Skipped class URI not matching ns: %s", c_str)

        imports = []
        for imp in temp_g.objects(None, OWL.imports):
            imp_str = str(imp).rstrip('/#')
            import_name = imp_str.rsplit('/', 1)[-1] if '/' in imp_str else imp_str
            imports.append(import_name)

        ontology_info[ontology_name] = {
            "title": title,
            "full_title": full_title,
            "description": desc,
            "classes": local_classes_temp,
            "imports": imports                   
        }
        ns_to_ontology[ns] = ontology_name

    # Step 2: Load full graph (rdflib multi-parse)
    g = Graph()
    for owl_path in owl_files:
        try:
            g.parse(owl_path, format='xml')
            log.debug("Parsed %s into full graph (%d triples total)", owl_path, len(g))
        except Exception as e:
            log.warning("Failed to parse %s into full graph: %s", owl_path, str(e))

    # ns for full g (use fixed base)
#    ns = "https://w3id.org/citydata/part1/v1/"
    log.info("Using fixed ns for full graph: %s", ns)

    # prefix_map must be defined here before use
    prefix_map = dict(g.namespaces())
    for owl_path in owl_files:
        with open(owl_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Grab all xmlns:prefix="uri"
        ns_matches = re.findall(r'xmlns:(\w+)\s*=\s*"([^"]+)"', content)
        for prefix, uri in ns_matches:
            if prefix not in prefix_map:
                prefix_map[prefix] = uri
                log.info("Added missing prefix from %s: %s = %s", owl_path, prefix, uri)
    log.info("Extracted %d prefixes from full graph", len(prefix_map))
    log.debug("Prefix map: %s", prefix_map)

    # prop_map
    prop_map = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        qn = get_qname(g, p, ns, prefix_map)
        prop_map[qn] = p
    for p in g.subjects(RDF.type, OWL.DatatypeProperty):
        qn = get_qname(g, p, ns, prefix_map)
        prop_map[qn] = p

    # Collect classes from full g
    classes = set(g.subjects(RDF.type, OWL.Class)) - {OWL.Thing}
    log.info("Total classes in full graph: %d", len(classes))

    # local_classes from per-pattern collections
    local_classes = []
    for ont_name, ont in ontology_info.items():
        for cls_name in ont["classes"]:
            # Find URI in full g
            for c in g.subjects(RDF.type, OWL.Class):
                if get_label(g, c) == cls_name:
                    local_classes.append(c)
                    break
    local_classes = list(set(local_classes))
    log.info("Aggregated %d local classes from patterns", len(local_classes))

    # Update global collections
    for cls in classes:
        cls_qname = get_qname(g, cls, ns, prefix_map)
        abstract_map[cls_qname] = is_abstract(cls, g, ns)
        if cls_qname != 'ITSThing':
            global_all_classes.add(cls_qname)

    # Populate global_patterns and class_to_onts from per-pattern classes
    for ont_name, ont in ontology_info.items():
        global_patterns[ont_name] = [(cls_name, ont_name) for cls_name in ont["classes"]]
        for cls_name in ont["classes"]:
            class_to_onts[cls_name].append(ont_name)

    # Process classes for diagrams and Markdown using full g
    for cls in sorted(local_classes, key=lambda u: get_label(g, u).lower()):
        cls_name = get_label(g, cls)
        if cls_name == 'ITSThing':
            continue
        cls_id = get_id(cls_name)
        log.debug("Processing class: %s", cls_name)

        try:
            # Use a dummy owl_path for diagrams, since no per-file
            dummy_path = owl_files[0]
            generate_diagram(g, cls, cls_name, cls_id, ns, global_all_classes, abstract_map, dummy_path, errors, prefix_map, "", ns_to_ontology)  # empty ontology_name

            # Generate Markdown - use empty ontology_name, adjust file_path to docs_dir
            generate_markdown(g, cls, cls_name, global_patterns, global_all_classes, ns, docs_dir, errors, prefix_map, prop_map, "", ns_to_ontology, class_to_onts)
            processed_count += 1

        except Exception as e:
            error_msg = f"Error processing class {cls_name}: {str(e)}\n{traceback.format_exc()}"
            errors.append(error_msg)
            log.error(error_msg)

    # Generate pattern markdowns
    for ont_name, ont in ontology_info.items():
        generate_pattern_markdown(ont_name, ont, docs_dir, class_to_onts, ontology_info)

    # Update mkdocs.yml navigation
    try:
        update_mkdocs_nav(mkdocs_path, global_patterns, global_all_classes, errors, class_to_onts, ontology_info, owl_files)
    except Exception as e:
        error_msg = f"Error updating mkdocs.yml: {str(e)}\n{traceback.format_exc()}"
        errors.append(error_msg)
        log.error(error_msg)

    # Generate index.md
    try:
        generate_index(docs_dir, owl_files, ontology_info, global_patterns, errors, class_to_onts, full_title)
    except Exception as e:
        error_msg = f"Error generating index.md: {str(e)}\n{traceback.format_exc()}"
        errors.append(error_msg)
        log.error(error_msg)

    log.info("Total processed classes: %d", processed_count)
    if errors:
        log.error("Errors occurred:")
        for err in errors:
            log.error(err)

if __name__ == "__main__":
    main()