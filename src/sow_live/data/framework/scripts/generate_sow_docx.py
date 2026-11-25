#!/usr/bin/env python3
"""
SoW .docx generation engine for the SoW Skills Framework.

Produces a ShellKode-branded Statement of Work from a JSON content payload,
reproducing the exact fonts, colors, cover page, tables, and footer of the
reference proposal.

Usage:
    python generate_sow_docx.py <content.json> [output.docx]

The content JSON schema is documented in
the docx-formatter skill's references/content-schema.md
"""

import json
import os
import sys

from docx import Document
from docx.shared import Pt, Mm, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement, parse_xml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EMU_PER_INCH = 914400
A4_WIDTH_EMU = int(210 / 25.4 * EMU_PER_INCH)   # ~7559675
A4_HEIGHT_EMU = int(297 / 25.4 * EMU_PER_INCH)  # ~10692000


def load_style():
    with open(os.path.join(ROOT, "templates", "style-reference.json"), encoding="utf-8") as f:
        return json.load(f)


STYLE = load_style()


def rgb(hexstr):
    return RGBColor.from_string(hexstr.replace("#", ""))


def asset_path(rel):
    return os.path.join(ROOT, rel)


# ---------------------------------------------------------------------------
# Low-level XML helpers
# ---------------------------------------------------------------------------

def set_cell_background(cell, hex_fill):
    """Apply solid shading to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill.replace("#", ""))
    tc_pr.append(shd)


def set_table_borders(table, color="BFBFBF", size_pt=0.5):
    """Apply thin borders to every side of every cell."""
    sz = str(int(size_pt * 8))  # eighths of a point
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color.replace("#", ""))
        borders.append(el)
    tbl_pr.append(borders)


def _emu(val_emu):
    return str(int(val_emu))


def add_floating_image(paragraph, image_path, x_emu, y_emu, w_emu, h_emu, behind=True):
    """Anchor an image at an absolute page position, optionally behind text."""
    run = paragraph.add_run()
    # Register the image as an inline picture first to get a valid rId, then
    # convert the inline drawing into a floating anchor.
    from docx.image.image import Image as DocxImage  # noqa: F401
    inline = run.add_picture(image_path, width=Emu(w_emu), height=Emu(h_emu))
    # inline is an InlineShape; grab its drawing element
    drawing = run._r.find(qn("w:drawing"))
    inline_el = drawing.find(qn("wp:inline"))
    blip = inline_el.find(".//" + qn("a:blip"))
    embed_rid = blip.get(qn("r:embed"))
    doc_pr = inline_el.find(qn("wp:docPr"))
    doc_pr_id = doc_pr.get("id")
    doc_pr_name = doc_pr.get("name")

    behind_val = "1" if behind else "0"
    anchor_xml = f'''
    <wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
               xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
               xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
               distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="0"
               behindDoc="{behind_val}" locked="0" layoutInCell="1" allowOverlap="1">
      <wp:simplePos x="0" y="0"/>
      <wp:positionH relativeFrom="page"><wp:posOffset>{_emu(x_emu)}</wp:posOffset></wp:positionH>
      <wp:positionV relativeFrom="page"><wp:posOffset>{_emu(y_emu)}</wp:posOffset></wp:positionV>
      <wp:extent cx="{_emu(w_emu)}" cy="{_emu(h_emu)}"/>
      <wp:effectExtent l="0" t="0" r="0" b="0"/>
      <wp:wrapNone/>
      <wp:docPr id="{doc_pr_id}" name="{doc_pr_name}"/>
      <wp:cNvGraphicFramePr/>
      <a:graphic>
        <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
          <pic:pic>
            <pic:nvPicPr>
              <pic:cNvPr id="{doc_pr_id}" name="{doc_pr_name}"/>
              <pic:cNvPicPr/>
            </pic:nvPicPr>
            <pic:blipFill>
              <a:blip r:embed="{embed_rid}"/>
              <a:stretch><a:fillRect/></a:stretch>
            </pic:blipFill>
            <pic:spPr>
              <a:xfrm><a:off x="0" y="0"/><a:ext cx="{_emu(w_emu)}" cy="{_emu(h_emu)}"/></a:xfrm>
              <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
            </pic:spPr>
          </pic:pic>
        </a:graphicData>
      </a:graphic>
    </wp:anchor>'''
    anchor = parse_xml(anchor_xml)
    drawing.remove(inline_el)
    drawing.append(anchor)


def add_floating_textbox(paragraph, x_emu, y_emu, w_emu, h_emu, runs, align="left"):
    """
    Add a borderless floating text box at an absolute page position.

    `runs` is a list of dicts: {text, font, size, color, bold}
    """
    para_xml = []
    for r in runs:
        color = r.get("color", "000000").replace("#", "")
        size_half = int(r.get("size", 11) * 2)
        bold = '<w:b/>' if r.get("bold") else ''
        font = r.get("font", "DM Sans")
        text = (r.get("text", "")
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        para_xml.append(
            f'<w:r><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>{bold}'
            f'<w:color w:val="{color}"/><w:sz w:val="{size_half}"/></w:rPr>'
            f'<w:t xml:space="preserve">{text}</w:t></w:r>'
        )
    jc = {"left": "left", "center": "center", "right": "right"}.get(align, "left")
    txbx_content = (
        f'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:pPr><w:jc w:val="{jc}"/></w:pPr>' + "".join(para_xml) + '</w:p>'
    )

    run = paragraph.add_run()
    drawing_xml = f'''
    <w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
               xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
               xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
      <wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="5"
                 behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="page"><wp:posOffset>{_emu(x_emu)}</wp:posOffset></wp:positionH>
        <wp:positionV relativeFrom="page"><wp:posOffset>{_emu(y_emu)}</wp:posOffset></wp:positionV>
        <wp:extent cx="{_emu(w_emu)}" cy="{_emu(h_emu)}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:wrapNone/>
        <wp:docPr id="{1000 + hash(str(runs)) % 5000}" name="tb"/>
        <wp:cNvGraphicFramePr/>
        <a:graphic>
          <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
            <wps:wsp>
              <wps:cNvSpPr txBox="1"/>
              <wps:spPr>
                <a:xfrm><a:off x="0" y="0"/><a:ext cx="{_emu(w_emu)}" cy="{_emu(h_emu)}"/></a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                <a:noFill/>
                <a:ln><a:noFill/></a:ln>
              </wps:spPr>
              <wps:txbx>
                <w:txbxContent>{txbx_content}</w:txbxContent>
              </wps:txbx>
              <wps:bodyPr rot="0" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t"/>
            </wps:wsp>
          </a:graphicData>
        </a:graphic>
      </wp:anchor>
    </w:drawing>'''
    run._r.append(parse_xml(drawing_xml))


# ---------------------------------------------------------------------------
# Document setup
# ---------------------------------------------------------------------------

def setup_page(section):
    section.page_width = Mm(STYLE["page"]["width_mm"])
    section.page_height = Mm(STYLE["page"]["height_mm"])
    section.top_margin = Mm(STYLE["page"]["margin_top_mm"])
    section.bottom_margin = Mm(STYLE["page"]["margin_bottom_mm"])
    section.left_margin = Mm(STYLE["page"]["margin_left_mm"])
    section.right_margin = Mm(STYLE["page"]["margin_right_mm"])


def _apply_run_style(run, spec):
    run.font.name = spec["font"]
    run.font.size = Pt(spec["size"])
    run.font.bold = spec.get("bold", False)
    run.font.color.rgb = rgb(spec["color"])
    # ensure east-asian / hAnsi font is set too
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), spec["font"])
    rfonts.set(qn("w:hAnsi"), spec["font"])


def setup_styles(doc):
    ts = STYLE["text_styles"]
    # Normal / body
    normal = doc.styles["Normal"]
    normal.font.name = ts["body"]["font"]
    normal.font.size = Pt(ts["body"]["size"])
    normal.font.color.rgb = rgb(ts["body"]["color"])

    mapping = {"Heading 1": "heading1", "Heading 2": "heading2", "Heading 3": "heading3"}
    for style_name, key in mapping.items():
        spec = ts[key]
        st = doc.styles[style_name]
        st.font.name = spec["font"]
        st.font.size = Pt(spec["size"])
        st.font.bold = spec["bold"]
        st.font.color.rgb = rgb(spec["color"])
        # kill the default "based on" blue-underline / spacing quirks
        st.paragraph_format.space_before = Pt(12)
        st.paragraph_format.space_after = Pt(6)


def add_footer(section):
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(STYLE["footer"]["text"] + "    ")
    run.font.name = "DM Sans"
    run.font.size = Pt(8)
    run.font.color.rgb = rgb("666666")
    if STYLE["footer"]["show_page_number"]:
        fld_begin = OxmlElement("w:fldSimple")
        fld_begin.set(qn("w:instr"), "PAGE")
        run2 = p.add_run()
        run2.font.size = Pt(8)
        run2.font.color.rgb = rgb("666666")
        # simple PAGE field
        r = run2._r
        fldchar1 = OxmlElement("w:fldChar"); fldchar1.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = " PAGE "
        fldchar2 = OxmlElement("w:fldChar"); fldchar2.set(qn("w:fldCharType"), "end")
        r.append(fldchar1); r.append(instr); r.append(fldchar2)


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------

def build_cover(doc, cover):
    ts = STYLE["text_styles"]
    p = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()

    # Full-page background artwork behind everything
    art = asset_path(STYLE["assets"]["cover_art"])
    if os.path.exists(art):
        add_floating_image(p, art, 0, 0, A4_WIDTH_EMU, A4_HEIGHT_EMU, behind=True)

    # Logo top-left
    logo = asset_path(STYLE["assets"]["logo"])
    if os.path.exists(logo):
        logo_w = int(2.4 * EMU_PER_INCH)
        logo_h = int(1.7 * EMU_PER_INCH)
        add_floating_image(p, logo, int(0.9 * EMU_PER_INCH), int(0.7 * EMU_PER_INCH),
                           logo_w, logo_h, behind=False)

    # Client name
    add_floating_textbox(
        p, int(0.9 * EMU_PER_INCH), int(2.6 * EMU_PER_INCH),
        int(6.0 * EMU_PER_INCH), int(0.6 * EMU_PER_INCH),
        [{"text": cover.get("client_name", "{{client_legal_name}}"),
          **{k: ts["cover_client_name"][k] for k in ("font", "size", "color", "bold")}}],
    )
    # Project title
    add_floating_textbox(
        p, int(0.9 * EMU_PER_INCH), int(3.15 * EMU_PER_INCH),
        int(6.0 * EMU_PER_INCH), int(0.6 * EMU_PER_INCH),
        [{"text": cover.get("project_title", "{{project_title}}"),
          **{k: ts["cover_project_title"][k] for k in ("font", "size", "color", "bold")}}],
    )
    # Prepared By block in the dark bottom-left corner
    add_floating_textbox(
        p, int(0.9 * EMU_PER_INCH), int(9.4 * EMU_PER_INCH),
        int(3.2 * EMU_PER_INCH), int(1.2 * EMU_PER_INCH),
        [{"text": "Prepared By:", **{k: ts["cover_prepared_label"][k] for k in ("font", "size", "color", "bold")}}],
    )
    add_floating_textbox(
        p, int(0.9 * EMU_PER_INCH), int(9.75 * EMU_PER_INCH),
        int(3.2 * EMU_PER_INCH), int(0.4 * EMU_PER_INCH),
        [{"text": cover.get("author", "{{author}}"),
          **{k: ts["cover_author"][k] for k in ("font", "size", "color", "bold")}}],
    )
    add_floating_textbox(
        p, int(0.9 * EMU_PER_INCH), int(10.05 * EMU_PER_INCH),
        int(3.2 * EMU_PER_INCH), int(0.4 * EMU_PER_INCH),
        [{"text": cover.get("website", STYLE["company"]["website"]),
          **{k: ts["cover_url"][k] for k in ("font", "size", "color", "bold")}}],
    )

    # page break to leave the cover page
    from docx.enum.text import WD_BREAK
    p.add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# Table of contents (static, generated from body headings)
# ---------------------------------------------------------------------------

def build_toc(doc, body):
    ts = STYLE["text_styles"]
    title = doc.add_paragraph()
    run = title.add_run("Table of contents")
    _apply_run_style(run, ts["toc_title"])
    for block in body:
        if block.get("block") == "h1":
            num = block.get("number", "")
            text = block.get("text", "")
            line = doc.add_paragraph()
            r = line.add_run(f"{num}. {text}" if num else text)
            r.font.name = "DM Sans"
            r.font.size = Pt(11)
            r.font.bold = True
            r.font.color.rgb = rgb("000000")
    from docx.enum.text import WD_BREAK
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# Body block rendering
# ---------------------------------------------------------------------------

def render_heading(doc, block, level):
    num = block.get("number", "")
    text = block.get("text", "")
    label = f"{num}. {text}" if num else text
    doc.add_heading(label, level=level)


def render_paragraph(doc, block):
    ts = STYLE["text_styles"]
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    text = block.get("text", "")
    run = p.add_run(text)
    _apply_run_style(run, ts["body"])


def render_bullets(doc, block, level=0):
    ts = STYLE["text_styles"]
    for item in block.get("items", []):
        if isinstance(item, dict):
            text = item.get("text", "")
            children = item.get("children", [])
        else:
            text = item
            children = []
        p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
        run = p.add_run(text)
        _apply_run_style(run, ts["body"])
        for child in children:
            cp = doc.add_paragraph(style="List Bullet 2")
            cr = cp.add_run(child if isinstance(child, str) else child.get("text", ""))
            _apply_run_style(cr, ts["body"])


def render_table(doc, block):
    ts = STYLE["text_styles"]
    header = block.get("header", [])
    rows = block.get("rows", [])
    center_cols = set(block.get("align_center_cols", []))
    ncols = len(header) if header else (len(rows[0]) if rows else 1)

    table = doc.add_table(rows=0, cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    if header:
        hrow = table.add_row().cells
        for j, htext in enumerate(header):
            set_cell_background(table.rows[0].cells[j], STYLE["table"]["header_fill"])
            cell = hrow[j]
            cell.paragraphs[0].text = ""
            r = cell.paragraphs[0].add_run(str(htext))
            _apply_run_style(r, ts["table_header"])
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for row in rows:
        # phase/group spanning row: {"group": "Phase 2A ..."}
        if isinstance(row, dict) and "group" in row:
            grow = table.add_row().cells
            merged = grow[0]
            for c in grow[1:]:
                merged = merged.merge(c)
            merged.paragraphs[0].text = ""
            r = merged.paragraphs[0].add_run(row["group"])
            _apply_run_style(r, {"font": "DM Sans", "size": 10, "bold": True, "color": "000000"})
            set_cell_background(merged, "E8EEFB")
            continue
        cells = table.add_row().cells
        for j, val in enumerate(row):
            cells[j].paragraphs[0].text = ""
            r = cells[j].paragraphs[0].add_run(str(val))
            _apply_run_style(r, ts["table_body"])
            if j in center_cols:
                cells[j].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    set_table_borders(table, STYLE["table"]["border_color"], STYLE["table"]["border_size_pt"])


def render_image(doc, block):
    path = block.get("path", "")
    width_in = block.get("width_in", 6.5)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if path and os.path.exists(path):
        p.add_run().add_picture(path, width=Emu(int(width_in * EMU_PER_INCH)))
    else:
        r = p.add_run(f"[Architecture diagram placeholder: {path or 'not provided'}]")
        r.font.italic = True
        r.font.color.rgb = rgb("666666")
    if block.get("caption"):
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cr = cap.add_run(block["caption"])
        cr.font.size = Pt(9)
        cr.font.italic = True
        cr.font.color.rgb = rgb("666666")


def render_body(doc, body):
    from docx.enum.text import WD_BREAK
    for block in body:
        kind = block.get("block")
        if kind == "h1":
            render_heading(doc, block, 1)
        elif kind == "h2":
            render_heading(doc, block, 2)
        elif kind == "h3":
            render_heading(doc, block, 3)
        elif kind == "p":
            render_paragraph(doc, block)
        elif kind == "bullets":
            render_bullets(doc, block)
        elif kind == "table":
            render_table(doc, block)
        elif kind == "image":
            render_image(doc, block)
        elif kind == "pagebreak":
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate(content, output_path):
    doc = Document()
    setup_page(doc.sections[0])
    setup_styles(doc)

    cover = content.get("cover", {})
    build_cover(doc, cover)

    body = content.get("body", [])
    if content.get("include_toc", True):
        build_toc(doc, body)

    render_body(doc, body)

    add_footer(doc.sections[0])

    doc.save(output_path)
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_sow_docx.py <content.json> [output.docx]")
        sys.exit(1)
    content_file = sys.argv[1]
    with open(content_file, encoding="utf-8") as f:
        content = json.load(f)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        cover = content.get("cover", {})
        client = cover.get("client_name", "Client").split(",")[0].strip()
        title = cover.get("project_title", "Statement of Work").strip()
        output_path = f"{client} - {title}.docx"

    path = generate(content, output_path)
    print(f"Generated: {path}")


if __name__ == "__main__":
    main()
