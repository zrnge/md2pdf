#!/usr/bin/env python3
"""
md2pdf.py - Convert Markdown files to styled PDF documents.

Usage:
    python md2pdf.py input.md                  # outputs input.pdf
    python md2pdf.py input.md -o report.pdf    # custom output name
    python md2pdf.py input.md --a4             # A4 paper size

Dependencies:
    pip install reportlab

Supports: headings H1-H6, bold/italic/strikethrough, inline code,
          fenced code blocks, tables, blockquotes (with left border),
          horizontal rules, nested bullet/numbered lists, hyperlinks,
          page numbers, hard line breaks.
"""

import argparse
import re
import sys

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Preformatted, HRFlowable,
)
from reportlab.platypus.flowables import Flowable


# ── Color Palette ─────────────────────────────────────────────────────────

P = {
    "text":          "#1e1e2e",
    "h1":            "#1e1e2e",
    "h2":            "#313244",
    "h3":            "#45475a",
    "h4_6":          "#585b70",
    "code_bg":       "#1e1e2e",
    "code_fg":       "#022647",
    "code_border":   "#45475a",
    "inline_bg":     "#e6e9ef",
    "inline_fg":     "#d20f39",
    "quote_border":  "#111f35",
    "quote_bg":      "#f0f4ff",
    "quote_fg":      "#4c4f69",
    "hr":            "#ccd0da",
    "h1_rule":       "#1e1e2e",
    "h2_rule":       "#ccd0da",
    "thead_bg":      "#1e1e2e",
    "thead_fg":      "#cdd6f4",
    "trow1":         "#eff1f5",
    "trow2":         "#ffffff",
    "tgrid":         "#bcc0cc",
    "link":          "#1e66f5",
}

# Catppuccin Mocha syntax token colors
_TOKEN_COLORS = {}  # populated lazily after pygments import


def _build_token_colors():
    try:
        from pygments.token import Token as T
        return {
            T.Keyword:                  "#cba6f7",
            T.Keyword.Constant:         "#f38ba8",
            T.Keyword.Declaration:      "#cba6f7",
            T.Keyword.Namespace:        "#89b4fa",
            T.Keyword.Type:             "#f9e2af",
            T.Keyword.Reserved:         "#cba6f7",
            T.Name.Builtin:             "#f38ba8",
            T.Name.Builtin.Pseudo:      "#fab387",
            T.Name.Function:            "#89b4fa",
            T.Name.Function.Magic:      "#89dceb",
            T.Name.Class:               "#f9e2af",
            T.Name.Decorator:           "#f9e2af",
            T.Name.Exception:           "#f38ba8",
            T.Name.Tag:                 "#f38ba8",
            T.Name.Attribute:           "#89b4fa",
            T.String:                   "#a6e3a1",
            T.String.Doc:               "#585b70",
            T.String.Escape:            "#fab387",
            T.String.Interpol:          "#fab387",
            T.Number:                   "#fab387",
            T.Comment:                  "#585b70",
            T.Comment.Special:          "#f9e2af",
            T.Operator:                 "#89dceb",
            T.Operator.Word:            "#cba6f7",
            T.Punctuation:              "#cdd6f4",
            T.Literal:                  "#a6e3a1",
            T.Literal.Number:           "#fab387",
            T.Literal.String:           "#a6e3a1",
            T.Generic.Deleted:          "#f38ba8",
            T.Generic.Inserted:         "#a6e3a1",
            T.Generic.Heading:          "#89b4fa",
            T.Generic.Subheading:       "#cba6f7",
        }
    except ImportError:
        return {}


_DEFAULT_CODE_COLOR = "#080a0f"


def _token_color(ttype, color_map):
    """Walk up the pygments token hierarchy to find the nearest color."""
    t = ttype
    while t:
        if t in color_map:
            return color_map[t]
        try:
            t = t.parent
        except AttributeError:
            break
    return _DEFAULT_CODE_COLOR


def tokenize_code(code: str, lang: str):
    """Return list-of-lines, each line a list of (text, hex_color) tuples.
    Falls back to plain coloring if pygments is not installed."""
    global _TOKEN_COLORS
    if not _TOKEN_COLORS:
        _TOKEN_COLORS = _build_token_colors()

    try:
        from pygments.lexers import get_lexer_by_name, guess_lexer
        from pygments.util import ClassNotFound

        try:
            lexer = get_lexer_by_name(lang.lower()) if lang else guess_lexer(code)
        except (ClassNotFound, Exception):
            try:
                lexer = guess_lexer(code)
            except Exception:
                return [[(ln, _DEFAULT_CODE_COLOR)] for ln in code.split("\n")]

        lines = []
        current: list = []
        for ttype, value in lexer.get_tokens(code):
            color = _token_color(ttype, _TOKEN_COLORS)
            parts = value.split("\n")
            for idx, part in enumerate(parts):
                if idx > 0:
                    lines.append(current)
                    current = []
                if part:
                    current.append((part, color))
        if current:
            lines.append(current)
        return lines

    except ImportError:
        return [[(ln, _DEFAULT_CODE_COLOR)] for ln in code.split("\n")]


class SyntaxCodeBlock(Flowable):
    """Canvas-drawn syntax-highlighted code block."""

    FONT      = "Courier"
    FONT_SIZE = 8
    LEADING   = 12
    PAD_H     = 14   # horizontal padding
    PAD_V     = 10   # vertical padding
    BG        = "#1e1e2e"
    BORDER    = "#45475a"
    GUTTER_W  = 36   # width reserved for line numbers
    NUM_COLOR = "#585b70"

    def __init__(self, token_lines, show_line_numbers=True):
        super().__init__()
        self.token_lines = token_lines
        self.show_line_numbers = show_line_numbers
        self._w = self._h = 0

    def wrap(self, availWidth, availHeight):
        self._w = availWidth
        self._h = len(self.token_lines) * self.LEADING + 2 * self.PAD_V
        return self._w, self._h

    def draw(self):
        c = self.canv
        w, h = self._w, self._h

        # Background
        c.setFillColor(HexColor(self.BG))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # Subtle border
        c.setStrokeColor(HexColor(self.BORDER))
        c.setLineWidth(0.5)
        c.rect(0, 0, w, h, fill=0, stroke=1)

        # Gutter separator
        if self.show_line_numbers:
            c.setStrokeColor(HexColor(self.BORDER))
            c.setLineWidth(0.3)
            c.line(self.GUTTER_W, 0, self.GUTTER_W, h)

        c.setFont(self.FONT, self.FONT_SIZE)
        y = h - self.PAD_V - self.FONT_SIZE

        for lineno, line_tokens in enumerate(self.token_lines, start=1):
            # Line number
            if self.show_line_numbers:
                c.setFillColor(HexColor(self.NUM_COLOR))
                num_str = str(lineno)
                nw = c.stringWidth(num_str, self.FONT, self.FONT_SIZE)
                c.drawString(self.GUTTER_W - nw - 6, y, num_str)
                x = float(self.GUTTER_W + self.PAD_H)
            else:
                x = float(self.PAD_H)

            for text, color in line_tokens:
                c.setFillColor(HexColor(color))
                c.drawString(x, y, text)
                x += c.stringWidth(text, self.FONT, self.FONT_SIZE)

            y -= self.LEADING


# ── Styles ────────────────────────────────────────────────────────────────

def build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CodeBlock", parent=styles["Code"],
        fontName="Courier", fontSize=8, leading=11,
        backColor=HexColor(P["code_bg"]),
        textColor=HexColor(P["code_fg"]),
        borderColor=HexColor(P["code_border"]),
        borderWidth=0.5, borderPadding=(8, 10, 8, 10),
        spaceBefore=8, spaceAfter=8,
    ))

    styles.add(ParagraphStyle(
        name="BlockQuoteInner", parent=styles["Normal"],
        fontSize=10, leading=14,
        fontName="Helvetica-Oblique",
        textColor=HexColor(P["quote_fg"]),
        leftIndent=0, rightIndent=0,
        spaceBefore=0, spaceAfter=0,
    ))

    styles.add(ParagraphStyle(
        name="TCell", parent=styles["Normal"],
        fontSize=8.5, leading=12,
    ))
    styles.add(ParagraphStyle(
        name="TCellBold", parent=styles["Normal"],
        fontSize=8.5, leading=12,
        fontName="Helvetica-Bold",
        textColor=HexColor(P["thead_fg"]),
    ))

    # Bullet styles for up to 4 indent levels
    for lvl in range(1, 5):
        base = 12 + (lvl - 1) * 18
        styles.add(ParagraphStyle(
            name=f"Bullet{lvl}", parent=styles["Normal"],
            fontSize=10, leading=14,
            leftIndent=base + 14, bulletIndent=base,
            spaceBefore=1, spaceAfter=1,
        ))

    # Headings
    styles["Title"].fontSize = 24
    styles["Title"].fontName = "Helvetica-Bold"
    styles["Title"].textColor = HexColor(P["h1"])
    styles["Title"].spaceAfter = 4
    styles["Title"].spaceBefore = 0
    styles["Title"].leading = 28
    styles["Title"].alignment = TA_LEFT      # left-align like real markdown
    styles["Title"].keepWithNext = 1

    styles["Heading1"].fontSize = 18
    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].textColor = HexColor(P["h1"])
    styles["Heading1"].spaceBefore = 22
    styles["Heading1"].spaceAfter = 4
    styles["Heading1"].keepWithNext = 1

    styles["Heading2"].fontSize = 14
    styles["Heading2"].fontName = "Helvetica-Bold"
    styles["Heading2"].textColor = HexColor(P["h2"])
    styles["Heading2"].spaceBefore = 16
    styles["Heading2"].spaceAfter = 3
    styles["Heading2"].keepWithNext = 1

    styles["Heading3"].fontSize = 12
    styles["Heading3"].fontName = "Helvetica-BoldOblique"
    styles["Heading3"].textColor = HexColor(P["h3"])
    styles["Heading3"].spaceBefore = 12
    styles["Heading3"].spaceAfter = 3
    styles["Heading3"].keepWithNext = 1

    styles["Heading4"].fontSize = 11
    styles["Heading4"].fontName = "Helvetica-Bold"
    styles["Heading4"].textColor = HexColor(P["h4_6"])
    styles["Heading4"].spaceBefore = 10
    styles["Heading4"].spaceAfter = 2

    styles["Heading5"].fontSize = 10.5
    styles["Heading5"].fontName = "Helvetica-Bold"
    styles["Heading5"].textColor = HexColor(P["h4_6"])
    styles["Heading5"].spaceBefore = 8
    styles["Heading5"].spaceAfter = 2

    styles["Heading6"].fontSize = 10
    styles["Heading6"].fontName = "Helvetica-BoldOblique"
    styles["Heading6"].textColor = HexColor(P["h4_6"])
    styles["Heading6"].spaceBefore = 8
    styles["Heading6"].spaceAfter = 2

    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 15
    styles["Normal"].textColor = HexColor(P["text"])

    return styles


# ── Helpers ───────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    """Escape XML entities without double-escaping existing HTML entities."""
    # Only escape & when it is NOT already the start of an HTML entity
    text = re.sub(r"&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text


def inline(text: str) -> str:
    """Convert inline markdown to ReportLab XML markup.
    Handles escaping internally — do NOT pre-escape the input."""
    # ── 1. Extract and protect code spans ──────────────────────────────
    code_spans = []

    def save_code(m):
        content = m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        idx = len(code_spans)
        code_spans.append(
            f'<font name="Courier" size="9" color="{P["inline_fg"]}"'
            f' backColor="{P["inline_bg"]}"> {content} </font>'
        )
        return f"\x00CODE{idx}\x00"

    text = re.sub(r"`([^`]+)`", save_code, text)

    # ── 2. Escape remaining XML characters ─────────────────────────────
    text = esc(text)

    # ── 3. Inline formatting ────────────────────────────────────────────
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", text)
    # Bold + italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)
    # Links
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (
            f'<link href="{m.group(2)}" color="{P["link"]}">'
            f'<u>{m.group(1)}</u></link>'
        ),
        text,
    )

    # ── 4. Restore code spans ───────────────────────────────────────────
    for i, span in enumerate(code_spans):
        text = text.replace(f"\x00CODE{i}\x00", span)

    return text


def make_blockquote(content: str, styles) -> Table:
    """Wrap a paragraph in a styled table that draws a left-border blockquote."""
    para = Paragraph(content, styles["BlockQuoteInner"])
    t = Table([[para]], colWidths=["100%"])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor(P["quote_bg"])),
        ("LINEBEFORE", (0, 0), (0, -1), 4, HexColor(P["quote_border"])),
        ("BOX", (0, 0), (-1, -1), 0.3, HexColor(P["quote_border"])),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def parse_list_block(lines, start, styles):
    """Parse contiguous list lines (with nesting via indentation).
    Returns (flowables, next_index)."""
    flowables = []
    i = start
    n = len(lines)

    def indent_of(line):
        return len(line) - len(line.lstrip(" \t"))

    base_indent = indent_of(lines[i]) if i < n else 0
    num_counter = {}  # indent_level → running number

    while i < n:
        line = lines[i]
        if not line.strip():
            break

        ul = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        ol = re.match(r"^(\s*)\d+\.\s+(.*)$", line)

        if not ul and not ol:
            break

        cur_indent = indent_of(line)
        if cur_indent < base_indent:
            break

        lvl = max(1, min(4, (cur_indent // 2) + 1))

        if ul:
            item_text = ul.group(2).strip()
            flowables.append(
                Paragraph(inline(item_text), styles[f"Bullet{lvl}"], bulletText="\u2022")
            )
        else:
            item_text = ol.group(2).strip()
            num_counter[lvl] = num_counter.get(lvl, 0) + 1
            # Reset deeper levels when we go back up
            for deeper in [k for k in num_counter if k > lvl]:
                del num_counter[deeper]
            flowables.append(
                Paragraph(
                    inline(item_text), styles[f"Bullet{lvl}"],
                    bulletText=f"{num_counter[lvl]}.",
                )
            )
        i += 1

    return flowables, i


# ── Page number footer ────────────────────────────────────────────────────

def _page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#9ca0b0"))
    canvas.drawRightString(
        doc.pagesize[0] - doc.rightMargin,
        doc.bottomMargin - 16,
        f"Page {canvas.getPageNumber()}",
    )
    canvas.restoreState()


# ── Core parser ───────────────────────────────────────────────────────────

def md_to_flowables(md_text: str, styles):
    flowables = []
    lines = md_text.split("\n")
    i = 0
    n = len(lines)
    first_h1 = True

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── blank line ──────────────────────────────────────────────────
        if not stripped:
            flowables.append(Spacer(1, 5))
            i += 1
            continue

        # ── heading ─────────────────────────────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            lvl = len(m.group(1))
            text = inline(m.group(2).strip())
            if lvl == 1 and first_h1:
                first_h1 = False
                flowables.append(Paragraph(text, styles["Title"]))
                flowables.append(HRFlowable(
                    width="100%", thickness=2,
                    color=HexColor(P["h1_rule"]),
                    spaceBefore=2, spaceAfter=10,
                ))
            elif lvl == 1:
                flowables.append(Paragraph(text, styles["Heading1"]))
                flowables.append(HRFlowable(
                    width="100%", thickness=1,
                    color=HexColor(P["h1_rule"]),
                    spaceBefore=2, spaceAfter=6,
                ))
            elif lvl == 2:
                flowables.append(Paragraph(text, styles["Heading2"]))
                flowables.append(HRFlowable(
                    width="100%", thickness=0.5,
                    color=HexColor(P["h2_rule"]),
                    spaceBefore=2, spaceAfter=4,
                ))
            else:
                sname = f"Heading{min(lvl, 6)}"
                flowables.append(Paragraph(text, styles[sname]))
            i += 1
            continue

        # ── horizontal rule ─────────────────────────────────────────────
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            flowables.append(HRFlowable(
                width="100%", thickness=1,
                color=HexColor(P["hr"]),
                spaceBefore=8, spaceAfter=8,
            ))
            i += 1
            continue

        # ── fenced code block ────────────────────────────────────────────
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing ```
            raw = "\n".join(code_lines)
            # Hard-escape for Preformatted (no inline markup)
            raw = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            flowables.append(Preformatted(raw, styles["CodeBlock"]))
            continue

        # ── blockquote ──────────────────────────────────────────────────
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            flowables.append(make_blockquote(inline(" ".join(buf)), styles))
            flowables.append(Spacer(1, 4))
            continue

        # ── table ────────────────────────────────────────────────────────
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                raw = lines[i].strip()
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    i += 1
                    continue
                rows.append(cells)
                i += 1
            if rows:
                header = rows[0]
                body = rows[1:]
                col_count = len(header)
                avail = 6.5 * inch
                col_w = avail / max(col_count, 1)

                tdata = [[Paragraph(inline(c), styles["TCellBold"]) for c in header]]
                for row in body:
                    padded = (row + [""] * col_count)[:col_count]
                    tdata.append([Paragraph(inline(c), styles["TCell"]) for c in padded])

                t = Table(tdata, colWidths=[col_w] * col_count, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND",   (0, 0), (-1, 0),  HexColor(P["thead_bg"])),
                    ("TEXTCOLOR",    (0, 0), (-1, 0),  HexColor(P["thead_fg"])),
                    ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
                    ("ROWHEIGHT",    (0, 0), (-1, 0),  20),
                    ("GRID",         (0, 0), (-1, -1), 0.4, HexColor(P["tgrid"])),
                    ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING",   (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
                    ("LEFTPADDING",  (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                     [HexColor(P["trow1"]), HexColor(P["trow2"])]),
                ]))
                flowables.append(Spacer(1, 6))
                flowables.append(t)
                flowables.append(Spacer(1, 6))
            continue

        # ── list (ordered or unordered, with nesting) ────────────────────
        if re.match(r"^\s*[-*+]\s", line) or re.match(r"^\s*\d+\.\s", line):
            items, i = parse_list_block(lines, i, styles)
            flowables.extend(items)
            continue

        # ── regular paragraph (catch-all) ────────────────────────────────
        buf = []
        while i < n:
            s = lines[i].strip()
            if not s:
                break
            if (s.startswith("#") or s.startswith("```") or
                    s.startswith(">") or s.startswith("|") or
                    re.match(r"^[-*_]{3,}\s*$", s) or
                    re.match(r"^\s*\d+\.\s", lines[i]) or
                    re.match(r"^\s*[-*+]\s", lines[i])):
                break
            # Hard line break: trailing two spaces
            if lines[i].endswith("  "):
                buf.append(s + "<br/>")
            else:
                buf.append(s)
            i += 1
        if buf:
            flowables.append(Paragraph(inline(" ".join(buf)), styles["Normal"]))
        elif i < n:
            # Safety: advance past any line that matched nothing
            i += 1

    return flowables


# ── PDF generation ────────────────────────────────────────────────────────

def convert(input_path: str, output_path: str, pagesize=letter):
    with open(input_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    styles = build_styles()
    flowables = md_to_flowables(md_text, styles)

    if not flowables:
        flowables.append(Paragraph("(empty document)", styles["Normal"]))

    doc = SimpleDocTemplate(
        output_path,
        pagesize=pagesize,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.95 * inch,
    )
    doc.build(flowables, onFirstPage=_page_footer, onLaterPages=_page_footer)
    print(f"[+] PDF written to: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Convert Markdown to PDF")
    parser.add_argument("input", help="Path to .md file")
    parser.add_argument("-o", "--output", help="Output PDF path (default: <input>.pdf)")
    parser.add_argument("--a4", action="store_true", help="Use A4 paper (default: Letter)")
    args = parser.parse_args()

    if not args.input.endswith(".md"):
        print("[!] Warning: input does not end with .md", file=sys.stderr)

    output = args.output or args.input.rsplit(".", 1)[0] + ".pdf"
    convert(args.input, output, pagesize=A4 if args.a4 else letter)


if __name__ == "__main__":
    main()
