"""Shared spaCy NER PDF highlighting utilities."""

import ast


def parse_rgb_color(color_value):
    """Safely parse an RGB tuple string like '(0, 1, 1)' or return tuple directly."""
    if isinstance(color_value, (tuple, list)) and len(color_value) == 3:
        return tuple(float(c) for c in color_value)
    parsed = ast.literal_eval(str(color_value).strip())
    if isinstance(parsed, (tuple, list)) and len(parsed) == 3:
        return tuple(float(c) for c in parsed)
    raise ValueError(f"Invalid RGB color: {color_value}")


def highlight_pdf_entities(doc, nlp, rules, progress_callback=None):
    """Highlight spaCy NER entities on each page of a PyMuPDF document according to rules."""
    total_pages = len(doc)
    for i, page in enumerate(doc):
        text = page.get_text()
        spacy_doc = nlp(text)
        for ent in spacy_doc.ents:
            for rule in rules:
                label = rule.get("label", "").strip()
                if not label:
                    continue
                if ent.label_ == label.upper():
                    try:
                        color = parse_rgb_color(rule["color"])
                        insts = page.search_for(ent.text, quads=False)
                        for inst in insts:
                            if page.get_textbox(inst).strip() == ent.text:
                                annot = page.add_highlight_annot(inst)
                                annot.set_colors(stroke=color)
                                annot.update()
                        break
                    except Exception:
                        pass
        if progress_callback is not None and total_pages > 0:
            progress_callback((i + 1) / total_pages)
