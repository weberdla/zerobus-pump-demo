#!/usr/bin/env python3
"""Build print-ready PDFs of the demo guide (README) and the tag reference.

Building the guide also copies it to README.md in the repo root, where GitHub shows it.

Requires pandoc on PATH and:  pip install weasyprint beautifulsoup4 certifi
On macOS with Homebrew's pango, prefix the command with
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib so WeasyPrint can find it.

    python tools/build_pdf.py                   # builds every document below
    python tools/build_pdf.py tag-reference     # or just the ones you name
"""

import argparse
import datetime
import html
import os
import pathlib
import posixpath
import re
import subprocess
import urllib.parse

import certifi
from bs4 import BeautifulSoup
from weasyprint import HTML

# Some Python builds (e.g. python.org on macOS) ship without CA certificates,
# which silently breaks the Google Fonts import in pdf.css.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = pathlib.Path(__file__).resolve().parent / "pdf.css"

STEP_HEADING = re.compile(r"^(\d+)\. (.+)$")
# A Markdown link or image target that is a relative path: not an anchor, URL, or absolute path.
RELATIVE_MD_LINK = re.compile(r"(\]\()(?!#|[A-Za-z][A-Za-z0-9+.-]*:|/)([^)\s]+)")
LONG_BLOCK_LINES = 40  # longer code blocks may split across pages
LANG_LABELS = {"bash": "bash", "powershell": "PowerShell", "python": "Python", "sql": "SQL", "json": "JSON"}
BOX_DRAWING = set("─│┬┴┼└┘┐├┤")
EDITION = datetime.date.today().strftime("%B %Y")
# Relative links, such as one document's link to the other, point here in the PDFs. Left
# relative, WeasyPrint would turn them into file:// paths on the machine that built the PDF.
REPO_BLOB_URL = "https://github.com/weberdla/zerobus-pump-demo/blob/main"

# new_page: regex for top-level section ids that start on a new page; the rest flow on.
DOCUMENTS = {
    "README": {
        "input": "solution/README.md",
        "output": "solution/README.pdf",
        "copy_to": "README.md",  # a copy GitHub shows on the repo's front page
        "header": "Zerobus Ingest · Demo",
        "subtitle": "Deploy a Databricks Asset Bundle and run a live, self-stopping "
                    "demo: pump telemetry streaming through Zerobus Ingest into bronze, a continuously updated "
                    "silver table, a dashboard, and a plant-style operator screen that starts and stops the demo.",
        "flow": ["Service principal", "Deploy", "Start the app", "Run the demo", "Clean up"],
        "meta": [("Setup", "About 5 minutes"), ("Demo run", "15 minutes by default"),
                 ("Databricks CLI", "1.x (validated 1.20.0)"), ("Edition", EDITION)],
        "new_page": None,
        "toc": False,
    },
    "tag-reference": {
        "input": "solution/tag-reference.md",
        "output": "solution/tag-reference.pdf",
        "header": "Zerobus Ingest · Tag Reference",
        "subtitle": "The eight tags the simulated pump streams through Zerobus Ingest: what each one measures, "
                    "its unit, the values it can take, and its normal operating range; the alarm limits; and "
                    "the table structure and record format for sending readings to Zerobus.",
        "flow": ["Simulator", "Zerobus Ingest", "Bronze", "AUTO CDC", "Silver"],
        "meta": [("Equipment", "PUMP-101"), ("Site", "PLANT-A"), ("Tags", "8, every second"), ("Edition", EDITION)],
        "new_page": None,
        "toc": False,
    },
}


def render_markdown(path):
    return subprocess.run(
        ["pandoc", str(path), "-f", "gfm", "-t", "html5", "--wrap=none"],
        check=True, capture_output=True, text=True,
    ).stdout


def cover_html(doc, kicker, title):
    flow = '<li class="arrow">→</li>'.join(f"<li>{html.escape(step)}</li>" for step in doc["flow"])
    cells = "".join(
        f'<td><span class="label">{label}</span><span class="value">{html.escape(value)}</span></td>'
        for label, value in doc["meta"]
    )
    return f"""
<section class="cover">
  <p class="cover-kicker">{html.escape(kicker)}</p>
  <h1 class="cover-title">{html.escape(title)}</h1>
  <p class="cover-sub">{html.escape(doc["subtitle"])}</p>
  <ul class="cover-flow">{flow}</ul>
  <div class="cover-meta"><table><tr>{cells}</tr></table></div>
</section>"""


def flow_diagram(text):
    """Turn the README's ASCII box diagram into an HTML flow diagram."""
    steps, box, label = [], None, None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("┌"):
            box = {"lines": [], "notes": [], "label": label}
            label = None
        elif stripped.startswith("└"):
            steps.append(box)
            box = None
        elif box is not None and stripped.count("│") >= 2:
            _, inner, note = line.split("│", 2)
            box["lines"].append(inner.strip())
            if note.strip():
                box["notes"].append(note.strip())
        elif box is None and stripped.startswith("│"):
            label = stripped.lstrip("│").strip() or None

    parts = []
    for i, step in enumerate(steps):
        if i:
            parts.append(f'<div class="flow-arrow">{html.escape(step["label"] or "")}</div>')
        title, *details = step["lines"]
        tier = title.split()[0].lower()  # bronze / silver / zerobus boxes get their own accent color
        detail = "".join(f'<div class="flow-detail">{html.escape(d)}</div>' for d in details)
        notes = "<br>".join(html.escape(n) for n in step["notes"])
        parts.append(
            f'<div class="flow-step"><div class="flow-box {tier}"><div class="flow-title">{html.escape(title)}</div>'
            f'{detail}</div><div class="flow-note">{notes}</div></div>'
        )
    return BeautifulSoup(f'<div class="flow">{"".join(parts)}</div>', "html.parser")


def transform(soup, doc):
    """Reshape pandoc's HTML for print. Returns (kicker, title)."""
    h1 = soup.find("h1")
    kicker, _, title = h1.get_text().partition(": ")
    title = title[:1].upper() + title[1:]
    new_page = re.compile(doc["new_page"]) if doc["new_page"] else None
    overview = soup.new_tag("h2", id="overview")
    overview.string = "Overview"
    h1.replace_with(overview)

    for h2 in soup.find_all("h2"):
        text = h2.get_text()
        h2["data-title"] = text
        if new_page and new_page.match(h2.get("id", "")):
            h2["class"] = h2.get("class", []) + ["new-page"]
        step = STEP_HEADING.match(text)
        if step:
            h2.clear()
            eyebrow = soup.new_tag("span", attrs={"class": "eyebrow"})
            eyebrow.string = f"Step {step.group(1)}"
            h2.append(eyebrow)
            h2.append(step.group(2))

    source_dir = posixpath.dirname(doc["input"])
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or urllib.parse.urlsplit(href).scheme:
            continue
        path, _, fragment = href.partition("#")
        target = posixpath.normpath(posixpath.join(source_dir, path))
        if target == doc["input"] and fragment:
            a["href"] = f"#{fragment}"
        else:
            a["href"] = f"{REPO_BLOB_URL}/{target}" + (f"#{fragment}" if fragment else "")

    # Pandoc adds an empty per-line anchor to every highlighted code line.
    for anchor in soup.select('pre code span[id] > a[href^="#cb"]'):
        anchor.decompose()

    for pre in soup.find_all("pre"):
        text = pre.get_text()
        classes = [c for c in pre.get("class", []) if c != "sourceCode"]
        if "┌" in text:
            pre.replace_with(flow_diagram(text))
            continue
        if BOX_DRAWING & set(text):
            pre["class"] = pre.get("class", []) + ["boxdraw"]  # keep box-drawing lines in one font
        if classes and classes[0] in LANG_LABELS:
            pre["data-lang"] = LANG_LABELS[classes[0]]
        if text.count("\n") > LONG_BLOCK_LINES:
            pre["class"] = pre.get("class", []) + ["long"]
        # Highlighted blocks have one span per source line. Make each line a block with
        # a hanging indent, so a wrapped line continues indented under its own start.
        code = pre.find("code")
        lines = code.find_all("span", id=True, recursive=False) if code else []
        if lines:
            for node in list(code.children):
                if isinstance(node, str) and not node.strip():
                    node.extract()
            for line in lines:
                content = line.get_text()
                indent = len(content) - len(content.lstrip(" ")) + 4
                line["class"] = ["line"]
                line["style"] = f"padding-left: {indent}ch; text-indent: -{indent}ch"

    # Keep lead-in lines ("Step 3: ...", "Cell 6:", "Expected output:") with what follows.
    for p in soup.find_all("p"):
        following = p.find_next_sibling()
        if following is not None and (
            following.name in ("pre", "table", "ul", "ol") or "sourceCode" in following.get("class", [])
        ):
            p["class"] = p.get("class", []) + ["lead-in"]
        elif p.strong and p.get_text().startswith("Step "):
            p["class"] = p.get("class", []) + ["lead-in"]

    for quote in soup.find_all("blockquote"):
        strong = quote.find("strong")
        if "✅" in quote.get_text() and strong and strong.get_text().startswith("Checkpoint"):
            quote["class"] = ["checkpoint"]
            badge = soup.new_tag("span", attrs={"class": "badge"})
            badge.string = "Checkpoint"
            strong.replace_with(badge)
            for node in quote.find_all(string=re.compile("✅")):
                node.replace_with(node.replace("✅", "").lstrip())

    return kicker, title


def toc_html(soup):
    items = []
    for heading in soup.find_all(["h2", "h3"]):
        if not heading.get("id"):
            continue
        label = heading.get("data-title") or heading.get_text()
        items.append(f'<li class="l{heading.name[1]}"><a href="#{heading["id"]}">{html.escape(label)}</a></li>')
    return f'<nav class="toc"><h2>Contents</h2><ul>{"".join(items)}</ul></nav>'


def build(doc):
    soup = BeautifulSoup(render_markdown(ROOT / doc["input"]), "html.parser")
    kicker, title = transform(soup, doc)
    toc = toc_html(soup) if doc["toc"] else ""
    document = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title></head>
<body data-header="{html.escape(doc["header"])}">{cover_html(doc, kicker, title)}{toc}<main>{soup}</main></body></html>"""

    output = ROOT / doc["output"]
    # Resolve relative image paths from the markdown file's own folder.
    HTML(string=document, base_url=str((ROOT / doc["input"]).parent)).write_pdf(output, stylesheets=[str(CSS)])
    print(output)
    if doc.get("copy_to"):
        write_copy(doc)


def write_copy(doc):
    """Copy the Markdown to doc["copy_to"], rewriting its relative links to work from there."""
    source, copy = doc["input"], doc["copy_to"]
    prefix = posixpath.relpath(posixpath.dirname(source), posixpath.dirname(copy) or ".")
    text = RELATIVE_MD_LINK.sub(
        lambda m: m.group(1) + posixpath.normpath(posixpath.join(prefix, m.group(2))),
        (ROOT / source).read_text(),
    )
    note = (f"<!-- Copy of {source}, written by tools/build_pdf.py with its relative links "
            f"adjusted. Edit {source}, not this file. -->\n\n")
    (ROOT / copy).write_text(note + text)
    print(ROOT / copy)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("documents", nargs="*", metavar="DOCUMENT",
                        help=f"documents to build: {', '.join(DOCUMENTS)} (default: all)")
    names = parser.parse_args().documents or list(DOCUMENTS)
    unknown = sorted(set(names) - set(DOCUMENTS))
    if unknown:
        parser.error(f"unknown document(s): {', '.join(unknown)}")
    for name in names:
        build(DOCUMENTS[name])


if __name__ == "__main__":
    main()
