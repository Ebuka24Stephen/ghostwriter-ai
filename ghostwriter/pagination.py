import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

_CAPTION_RE = re.compile(r"^(?:Table|Figure|Fig\.?|Illustration)\b", re.IGNORECASE)
_HEADING_TEXT_RE = re.compile(r"^(?:CHAPTER\b|\d+(?:\.\d+)*\s+[A-Z])")
_SHORT_WORDS = 30


def _is_caption(text):
    return bool(text) and bool(_CAPTION_RE.match(text))


def _is_heading_paragraph(p):
    style = p.style.name if p.style is not None else ""
    if "Heading" in style:
        return True
    text = p.text.strip()
    if not text:
        return False
    if _HEADING_TEXT_RE.match(text) and len(text) < 60:
        return True
    if len(text) < 60 and text.isupper() and re.search(r"[A-Za-z]", text):
        return True
    return False


def _is_short(text):
    return bool(text) and len(text.split()) <= _SHORT_WORDS


def _has_image(p):
    p_elem = p._p
    return (
        p_elem.find(qn("w:drawing")) is not None
        or p_elem.find(qn("w:pict")) is not None
        or any(True for _ in p_elem.iter(qn("pic:pic")))
    )


def _is_table_elem(elem):
    return elem is not None and elem.tag == qn("w:tbl")


def apply_pagination(doc):
    paras = doc.paragraphs
    for idx, p in enumerate(paras):
        pf = p.paragraph_format
        pf.widow_control = True
        text = p.text.strip()

        if _is_heading_paragraph(p):
            pf.keep_with_next = True
            pf.keep_together = True
            continue

        if _is_caption(text):
            pf.keep_with_next = True
            pf.keep_together = True
            continue

        if _is_short(text):
            pf.keep_together = True

        nxt = paras[idx + 1] if idx + 1 < len(paras) else None
        if _has_image(p) and nxt is not None and _is_caption(nxt.text.strip()):
            pf.keep_with_next = True
        elif _is_short(text):
            if nxt is not None and _has_image(nxt):
                pf.keep_with_next = True
            elif _is_table_elem(p._p.getnext()):
                pf.keep_with_next = True

    for table in doc.tables:
        for row in table.rows:
            tr_pr = row._tr.get_or_add_trPr()
            if tr_pr.find(qn("w:cantSplit")) is None:
                tr_pr.append(OxmlElement("w:cantSplit"))
