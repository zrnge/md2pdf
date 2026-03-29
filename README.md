# md2pdf

Convert Markdown files to styled PDF documents — preserving headings, tables, code blocks, blockquotes, lists, links, and more.

## Features

- **Headings H1–H6** with visual separators and distinct typography
- **Bold**, *italic*, ~~strikethrough~~, and `inline code`
- **Fenced code blocks** with dark theme styling
- **Blockquotes** with colored left border
- **Tables** with dark header row and alternating row colors
- **Nested bullet and numbered lists** (up to 4 levels)
- **Hyperlinks** rendered as clickable underlined text
- **Horizontal rules**
- **Hard line breaks** (trailing two spaces)
- **Page numbers** in the footer
- **Letter or A4** paper size

## Requirements

```
pip install reportlab
```

## Usage

```bash
# Basic — outputs input.pdf
python md2pdf.py input.md

# Custom output filename
python md2pdf.py input.md -o report.pdf

# A4 paper size
python md2pdf.py input.md --a4

# Combine flags
python md2pdf.py input.md -o report.pdf --a4
```

## Output Preview

| Markdown Element | PDF Rendering |
|-----------------|---------------|
| `# H1` | Large bold title with thick underline |
| `## H2` | Bold with thin grey underline |
| `### H3` | Bold-italic, muted color |
| `` `code` `` | Red monospace on light background |
| ```` ```block``` ```` | Dark terminal-style background |
| `> blockquote` | Blue left border with light background |
| `[text](url)` | Blue underlined clickable link |
| Tables | Dark header, striped rows |

## File Structure

```
md2pdf.py   — main script
```

## Author

[zrnge](https://github.com/zrnge)

## License

MIT
