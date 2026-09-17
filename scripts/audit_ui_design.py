#!/usr/bin/env python3
"""Static UI design audit for INFORAXIS.

The script intentionally uses only the standard library so it can run in a
minimal checkout. It reports patterns that often reintroduce legacy design:
inline visual styles, JavaScript layout mutation, duplicated CSS ownership, and
broad page selectors.

Usage:
    python scripts/audit_ui_design.py
    python scripts/audit_ui_design.py --format text
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
CSS_ROOT = ROOT / "static" / "css"
JS_ROOT = ROOT / "static" / "js"

VENDOR_JS_NAMES = {
    "bootstrap.bundle.min.js",
    "chart.umd.js",
    "html2pdf.bundle.min.js",
    "jquery.min.js",
    "jspdf.umd.min.js",
}
VENDOR_CSS_NAMES = {"bootstrap.min.css"}

INLINE_STYLE_RE = re.compile(r"style\s*=\s*([\"'])(.*?)\1", re.S)
STYLE_BLOCK_RE = re.compile(r"<style\b", re.I)
HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
PX_RE = re.compile(r"(?<![\w-])-?\d+(?:\.\d+)?px\b")
IMPORTANT_RE = re.compile(r"!important")
STYLE_USAGE_PATTERNS = ("style=\"", "style='", "style.cssText", ".style.")
CLASS_TOKEN_RE = re.compile(r"^[A-Za-z_][\w-]*$")

BOOTSTRAP_CLASS_PREFIXES = (
    "btn", "text", "bg", "d", "m", "p", "py", "px", "pt", "pb", "ps", "pe", "mt", "mb", "ms", "me",
    "mx", "my", "col", "row", "container", "card", "modal", "form", "alert", "badge", "nav", "navbar",
    "dropdown", "input", "table", "spinner", "visually", "w", "h", "gap", "align", "justify", "flex",
    "border", "rounded", "shadow", "list", "small", "fw", "fs", "lh", "position", "top", "bottom",
    "start", "end", "translate", "opacity", "overflow", "sticky", "display", "pagination",
)

STATE_CLASS_NAMES = {
    "active", "show", "hidden", "collapsed", "disabled", "selected", "open", "loading", "loaded", "visible",
    "expanded", "success", "error", "warning", "danger", "info", "primary", "secondary", "light", "dark", "muted",
    "read", "unread", "unknown", "current", "idle", "processing", "running", "complete", "completed", "failed",
    "was-validated", "has-scroll",
}
ICON_FRAGMENT_NAMES = {
    "check-circle", "check-circle-fill", "info-circle", "info-circle-fill", "x-circle", "x-circle-fill",
    "dash-circle", "exclamation-circle", "exclamation-triangle", "hourglass-split",
}
GLOBAL_CSS_FILES = {
    "bootstrap.min.css",
    "styles.css",
    "message_system.css",
    "chart-export.css",
    "design-system.css",
    "responsive-fixes.css",
    "page-tips.css",
    "data-interface.css",
    "js-page-components.css",
}

BROAD_SELECTOR_RE = re.compile(
    r"^(\.card\b|\.card-|\.btn\b|\.btn-|\.modal\b|\.modal-|\.table\b|\.table-|"
    r"\.badge\b|\.badge-|\.page-header\b|\.page-title\b|\.section\b|\.section-header\b|"
    r"\.filter-|\.result-|\.results-|\.chart-|\.file-card\b|\.word-card\b|"
    r"\.category-card\b|\.empty-state\b|\.loading-state\b|\.form-control\b|\.alert\b)"
)

ALLOWED_INLINE_HINTS = (
    "display:",
    "width:",
    "background-color: {{",
    "background-color:{{",
)
VISUAL_INLINE_HINTS = (
    "border",
    "padding",
    "font",
    "box-shadow",
    "height:",
    "margin",
    "background:",
    "color:",
)


@dataclass(frozen=True)
class TemplateStyleCount:
    path: Path
    total: int
    dynamic_like: int
    visual_like: int


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def iter_templates() -> Iterable[Path]:
    yield from sorted(TEMPLATE_ROOT.rglob("*.html"))


def iter_css() -> Iterable[Path]:
    for path in sorted(CSS_ROOT.glob("*.css")):
        if path.name not in VENDOR_CSS_NAMES:
            yield path


def iter_js() -> Iterable[Path]:
    for path in sorted(JS_ROOT.rglob("*.js")):
        if path.name in VENDOR_JS_NAMES or path.name.endswith(".min.js"):
            continue
        yield path


def classify_inline_style(style: str) -> str:
    normalized = " ".join(style.strip().split())
    if re.fullmatch(r"background-color:\s*\{\{.*\}\};?", normalized):
        return "dynamic"
    if any(hint in style for hint in ALLOWED_INLINE_HINTS) and not any(
        hint in style for hint in VISUAL_INLINE_HINTS
    ):
        return "dynamic"
    return "visual"


def template_style_counts() -> list[TemplateStyleCount]:
    counts: list[TemplateStyleCount] = []
    for path in iter_templates():
        text = path.read_text(errors="ignore")
        matches = list(INLINE_STYLE_RE.finditer(text))
        if not matches:
            continue
        dynamic = 0
        visual = 0
        for match in matches:
            if classify_inline_style(match.group(2)) == "dynamic":
                dynamic += 1
            else:
                visual += 1
        counts.append(TemplateStyleCount(path, len(matches), dynamic, visual))
    return counts


def template_style_blocks() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in iter_templates():
        count = len(STYLE_BLOCK_RE.findall(path.read_text(errors="ignore")))
        if count:
            counts[rel(path)] = count
    return counts


def js_style_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in iter_js():
        text = path.read_text(errors="ignore")
        count = sum(text.count(pattern) for pattern in STYLE_USAGE_PATTERNS)
        if count:
            counts[rel(path)] = count
    return counts


def css_class_selectors() -> set[str]:
    classes: set[str] = set()
    for path in iter_css():
        text = re.sub(r"/\*.*?\*/", "", path.read_text(errors="ignore"), flags=re.S)
        classes.update(re.findall(r"\.([A-Za-z_][\w-]*)", text))
    return classes


def class_token_is_covered(token: str, styled_classes: set[str]) -> bool:
    if not token or token in styled_classes or token in STATE_CLASS_NAMES or token in ICON_FRAGMENT_NAMES:
        return True
    if token.startswith(("bi-", "fa-", "ri-", "ti-")):
        return True
    return any(token == prefix or token.startswith(prefix + "-") for prefix in BOOTSTRAP_CLASS_PREFIXES)


def extract_js_class_tokens(text: str) -> set[str]:
    tokens: set[str] = set()

    for match in re.finditer(r"(?:class(?:Name)?\s*=|class\s*=)\s*([`'\"])(.*?)\1", text, re.S):
        raw = match.group(2)
        for token in re.split(r"\s+", raw):
            cleaned = token.strip("{}$`'\"<>/.,;:()[]")
            if "-" in cleaned and CLASS_TOKEN_RE.fullmatch(cleaned):
                tokens.add(cleaned)

    for match in re.finditer(r"classList\.(?:add|remove|toggle|contains)\((.*?)\)", text, re.S):
        tokens.update(re.findall(r"[`'\"]([A-Za-z_][\w-]*-[\w-]*)[`'\"]", match.group(1)))

    for match in re.finditer(r"className\s*=\s*([`'\"])(.*?)\1", text, re.S):
        for token in re.split(r"\s+", match.group(2)):
            cleaned = token.strip("{}$`'\"<>/.,;:()[]")
            if "-" in cleaned and CLASS_TOKEN_RE.fullmatch(cleaned):
                tokens.add(cleaned)

    return tokens


def js_rendered_class_gaps() -> dict[str, list[str]]:
    styled_classes = css_class_selectors()
    gaps: dict[str, list[str]] = {}
    for path in sorted((JS_ROOT / "pages").glob("*.js")):
        if path.name in VENDOR_JS_NAMES or path.name.endswith(".min.js"):
            continue
        tokens = extract_js_class_tokens(path.read_text(errors="ignore"))
        missing = sorted(token for token in tokens if not class_token_is_covered(token, styled_classes))
        if missing:
            gaps[rel(path)] = missing
    return gaps


def template_js_page_style_gaps() -> dict[str, list[str]]:
    gaps: dict[str, list[str]] = {}
    css_ref_re = re.compile(r"css/([^'\"]+\.css)")
    js_page_re = re.compile(r"js/pages/([^'\"]+\.js)")
    for path in iter_templates():
        text = path.read_text(errors="ignore")
        page_scripts = js_page_re.findall(text)
        if not page_scripts or path.name == "base.html":
            continue
        local_css = [name for name in css_ref_re.findall(text) if name not in GLOBAL_CSS_FILES]
        if not local_css:
            gaps[rel(path)] = page_scripts
    return gaps


def css_metrics() -> dict[str, dict[str, int]]:
    metrics: dict[str, dict[str, int]] = {}
    for path in iter_css():
        text = path.read_text(errors="ignore")
        metrics[rel(path)] = {
            "lines": text.count("\n") + 1,
            "colors": len(HEX_COLOR_RE.findall(text)),
            "px": len(PX_RE.findall(text)),
            "important": len(IMPORTANT_RE.findall(text)),
            "sticky": text.count("position: sticky"),
            "fixed": text.count("position: fixed"),
            "overflow": text.count("overflow"),
        }
    return metrics


def extract_css_selectors(path: Path) -> list[tuple[int, str]]:
    text = re.sub(r"/\*.*?\*/", "", path.read_text(errors="ignore"), flags=re.S)
    selectors: list[tuple[int, str]] = []
    for match in re.finditer(r"([^{}@]+)\{", text):
        raw = match.group(1).strip()
        if not raw or raw.startswith(("from", "to", "0%", "100%")):
            continue
        line = text[: match.start()].count("\n") + 1
        for selector in raw.split(","):
            selector = " ".join(selector.strip().split())
            if selector:
                selectors.append((line, selector))
    return selectors


def duplicate_selectors() -> dict[str, set[str]]:
    selector_files: dict[str, set[str]] = defaultdict(set)
    for path in iter_css():
        for _line, selector in extract_css_selectors(path):
            selector_files[selector].add(rel(path))
    return {selector: files for selector, files in selector_files.items() if len(files) >= 2}


def broad_page_selectors() -> dict[str, list[tuple[int, str]]]:
    shared = {
        "styles.css",
        "data-interface.css",
        "design-system.css",
        "responsive-fixes.css",
        "auth-workspace.css",
        "js-page-components.css",
        "bootstrap.min.css",
    }
    result: dict[str, list[tuple[int, str]]] = {}
    for path in iter_css():
        if path.name in shared:
            continue
        hits = [(line, selector) for line, selector in extract_css_selectors(path) if BROAD_SELECTOR_RE.match(selector)]
        if hits:
            result[rel(path)] = hits
    return result


def print_markdown() -> None:
    template_counts = template_style_counts()
    style_blocks = template_style_blocks()
    js_counts = js_style_counts()
    metrics = css_metrics()
    duplicates = duplicate_selectors()
    broad = broad_page_selectors()
    js_class_gaps = js_rendered_class_gaps()
    js_template_gaps = template_js_page_style_gaps()

    print("# Static UI Design Audit Report")
    print()
    print("Generated by `scripts/audit_ui_design.py`.")
    print()
    print("## Summary")
    print()
    print(f"- Template inline style attributes: {sum(item.total for item in template_counts)}")
    print(f"- Template style blocks: {sum(style_blocks.values())}")
    print(f"- JS files with style usage: {len(js_counts)}")
    print(f"- JS style usage count: {sum(js_counts.values())}")
    print(f"- CSS files scanned: {len(metrics)}")
    print(f"- CSS `!important` declarations: {sum(m['important'] for m in metrics.values())}")
    print(f"- CSS hard-coded hex colors: {sum(m['colors'] for m in metrics.values())}")
    print(f"- Duplicate selectors across CSS files: {len(duplicates)}")
    print(f"- Page CSS files with broad reusable selectors: {len(broad)}")
    print(f"- JS-rendered class names without CSS coverage: {sum(len(items) for items in js_class_gaps.values())}")
    print(f"- Templates with page JavaScript but no page-local CSS: {len(js_template_gaps)}")
    print()

    print("## Template inline styles")
    print()
    print("| File | Total | Dynamic-like | Visual-like |")
    print("| --- | ---: | ---: | ---: |")
    for item in template_counts:
        print(f"| `{rel(item.path)}` | {item.total} | {item.dynamic_like} | {item.visual_like} |")
    print()

    print("## JavaScript style usage")
    print()
    print("| File | Count |")
    print("| --- | ---: |")
    for file, count in js_counts.most_common():
        print(f"| `{file}` | {count} |")
    print()

    print("## JavaScript-rendered class coverage")
    print()
    if js_class_gaps:
        print("These class names are emitted from `static/js/pages/*.js` but are not covered by a non-vendor CSS selector after filtering Bootstrap utility/state/icon classes.")
        print()
        for file, classes in sorted(js_class_gaps.items()):
            print(f"### `{file}`")
            for class_name in classes[:80]:
                print(f"- `.{class_name}`")
            if len(classes) > 80:
                print(f"- ... {len(classes) - 80} more")
            print()
    else:
        print("All detected page-script class names have CSS coverage.")
        print()

    print("## Page JavaScript stylesheet coverage")
    print()
    if js_template_gaps:
        print("These templates include a `static/js/pages/*` script but no page-local stylesheet beyond the global shell styles.")
        print()
        for file, scripts in sorted(js_template_gaps.items()):
            print(f"- `{file}` → {', '.join(f'`{script}`' for script in scripts)}")
        print()
    else:
        print("Every template that includes a page JavaScript module also includes page-local CSS or the shared JavaScript component stylesheet from `base.html`.")
        print()

    print("## CSS metrics")
    print()
    print("| File | Lines | Colors | px | !important | Sticky | Fixed | Overflow |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for file, m in metrics.items():
        print(
            f"| `{file}` | {m['lines']} | {m['colors']} | {m['px']} | "
            f"{m['important']} | {m['sticky']} | {m['fixed']} | {m['overflow']} |"
        )
    print()

    print("## Top duplicate selectors")
    print()
    for selector, files in sorted(duplicates.items(), key=lambda item: (-len(item[1]), item[0]))[:80]:
        print(f"- `{selector}` → {', '.join(f'`{file}`' for file in sorted(files))}")
    print()

    print("## Broad selectors in page CSS")
    print()
    for file, hits in sorted(broad.items()):
        print(f"### `{file}`")
        for line, selector in hits[:40]:
            print(f"- L{line}: `{selector}`")
        if len(hits) > 40:
            print(f"- ... {len(hits) - 40} more")
        print()


def print_text() -> None:
    print_markdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the static INFORAXIS UI design audit.")
    parser.add_argument("--format", choices=("markdown", "text"), default="markdown")
    parser.parse_args()
    print_text()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
