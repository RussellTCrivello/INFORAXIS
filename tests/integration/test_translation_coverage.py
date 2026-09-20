"""Translation completeness for the single ingestion interface.

The interface this branch ships - ``/operations/input`` and the components it
uses - is available in every language the application offers (English, Arabic,
Hebrew, Persian) and is maintained in the dormant Croatian catalog too. This
module pins that, at three levels:

1. **Server strings.** Every ``_('...')`` in the interface's templates exists in
   every catalog with a real translation, and no catalog has an empty or fuzzy
   entry at all - a partially translated catalog is how a page ends up half in
   English.
2. **Client strings.** Every string the page's own JavaScript asks ``window.t``
   for exists in every locale pack. The runtime merges the page translations,
   the pack and the server catalog, and the server catalog wins; where a string
   exists in both, the two must agree or the user sees one of them at random.
3. **The rendered page.** Requesting the page in Arabic, Hebrew and Persian
   serves translated text (not the English source), with the right ``lang`` and
   ``dir`` attributes, and the sidebar offers exactly one way into ingestion -
   the duplicate "Upload Files" shortcut is gone.

The lists of strings are derived from the sources rather than hard-coded, so a
string added to the page without a translation fails here instead of shipping
in English.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.integration

TRANSLATIONS_DIR = PROJECT_ROOT / "translations"
PACKS_DIR = PROJECT_ROOT / "static" / "js" / "i18n" / "locales"

#: Offered by SUPPORTED_LANGUAGES (see settings/languages.py).
OFFERED = ("en", "ar", "he", "fa")
#: Kept in sync with the offered ones but not selectable (documented in
#: tests/integration/test_analyst_i18n.py::test_hr_catalog_is_maintained_but_not_exposed).
MAINTAINED = ("ar", "he", "fa", "hr")

#: The interface's own templates: every server-rendered string on these pages.
INTERFACE_TEMPLATES = (
    "templates/base.html",
    "templates/Operations/input.html",
    "templates/Operations/jobs.html",
    "templates/Operations/import_center.html",
    "templates/components/file_nav.html",
    "templates/components/operations_widget.html",
)

#: The page modules whose strings reach the user through window.t().
INTERFACE_SCRIPTS = (
    "static/js/pages/ingestion-studio-page.js",
    "static/js/pages/full-content-page.js",
)

GETTEXT_CALL = re.compile(r"""_\(\s*(['"])((?:\\.|(?!\1).)*)\1""", re.S)
JS_CALL = re.compile(r"""(?<![\w.])(?:msg|t|translate|window\.t|I18N\.t)\(\s*(['"])((?:\\.|(?!\1).)*)\1""")
SKIP_KEY = re.compile(r"^([/#]|http|data-|bi-|\d+$)")


def _template_msgids() -> list[str]:
    """Every ``_('...')`` string in the interface templates."""
    found: list[str] = []
    for relative in INTERFACE_TEMPLATES:
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for _quote, raw in GETTEXT_CALL.findall(text):
            msgid = raw.replace("\\'", "'").replace('\\"', '"')
            if msgid and msgid not in found:
                found.append(msgid)
    return found


def _script_keys() -> dict[str, str]:
    """Every string the interface scripts pass to the translator."""
    found: dict[str, str] = {}
    for relative in INTERFACE_SCRIPTS:
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for _quote, raw in JS_CALL.findall(text):
            key = raw.replace("\\'", "'").replace('\\"', '"')
            if len(key) >= 3 and not SKIP_KEY.search(key):
                found.setdefault(key, relative)
    return found


def _catalog(lang: str):
    from babel.messages.pofile import read_po

    with open(TRANSLATIONS_DIR / lang / "LC_MESSAGES" / "messages.po", "rb") as handle:
        return read_po(handle, locale=lang)


def _mo_catalog(lang: str):
    from babel.messages.mofile import read_mo

    with open(TRANSLATIONS_DIR / lang / "LC_MESSAGES" / "messages.mo", "rb") as handle:
        return read_mo(handle)


def _pack(lang: str) -> dict[str, str]:
    text = (PACKS_DIR / f"{lang}.js").read_text(encoding="utf-8")
    match = re.search(r"window\.I18N_UI_PACKS\[['\"]\w+['\"]\]\s*=\s*", text)
    assert match, f"{lang}.js does not register an I18N pack"
    body = text[match.end():].strip()
    return json.loads(body[: body.rindex("}") + 1])


# ---------------------------------------------------------------------------
# 1. Server strings
# ---------------------------------------------------------------------------

def test_the_interface_templates_have_strings_to_check():
    """Guard: the checks below are worthless if the extraction finds nothing."""
    assert len(_template_msgids()) > 60
    assert len(_script_keys()) > 60


#: Strings that are deliberately not translated: acronyms, format names and
#: literal values. A msgid with no lowercase letter is one of those by
#: construction (OCR, SHA-256, a bare status code), and this lifts it out of
#: the "must differ from the source" rule below.
_LITERAL_ALLOWED = ("OCR", "Status", "admin", "403", "SHA-256")


def _is_literal(msgid: str) -> bool:
    return msgid in _LITERAL_ALLOWED or not any(ch.islower() for ch in msgid)


@pytest.mark.parametrize("lang", MAINTAINED)
def test_every_interface_string_is_translated(lang):
    catalog = _catalog(lang)
    missing, untranslated = [], []
    for msgid in _template_msgids():
        message = catalog.get(msgid)
        if message is None:
            missing.append(msgid)
        elif not message.string or message.fuzzy:
            untranslated.append(msgid)
        elif message.string == msgid and not _is_literal(msgid):
            untranslated.append(msgid)
    assert not missing, f"[{lang}] interface strings absent from the catalog: {missing[:6]}"
    assert not untranslated, f"[{lang}] interface strings not translated: {untranslated[:6]}"


@pytest.mark.parametrize("lang", MAINTAINED)
def test_no_catalog_entry_is_empty_or_fuzzy(lang):
    """A catalog with gaps is a page that silently falls back to English."""
    catalog = _catalog(lang)
    bad = []
    for message in catalog:
        if not message.id:
            continue  # the header entry
        if not message.string or message.fuzzy:
            bad.append(message.id)
    assert not bad, f"[{lang}] {len(bad)} untranslated/fuzzy entries, e.g. {bad[:6]}"


@pytest.mark.parametrize("lang", MAINTAINED)
def test_the_compiled_catalog_carries_the_interface_strings(lang):
    """The .mo is what gettext actually loads: a stale .mo defeats the .po."""
    from babel.messages.pofile import read_po

    mo = _mo_catalog(lang)
    with open(TRANSLATIONS_DIR / lang / "LC_MESSAGES" / "messages.po", "rb") as handle:
        po = read_po(handle, locale=lang)
    missing = [msgid for msgid in _template_msgids()
               if mo.get(msgid) is None and po.get(msgid) is not None]
    assert not missing, f"[{lang}] .mo needs recompiling: {missing[:6]}"


def test_placeholder_layout_survives_translation():
    """A translation that drops ``{n}`` or ``%(name)s`` prints a broken line."""
    placeholder = re.compile(r"\{\w+\}|%\(\w+\)s")
    problems = []
    for lang in MAINTAINED:
        catalog = _catalog(lang)
        for msgid in _template_msgids():
            message = catalog.get(msgid)
            if message is None or not message.string:
                continue
            want = set(placeholder.findall(msgid))
            got = set(placeholder.findall(message.string))
            if want != got:
                problems.append(f"[{lang}] {msgid!r} -> {message.string!r} (placeholders differ)")
    assert not problems, problems[:5]


# ---------------------------------------------------------------------------
# 2. Client strings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", OFFERED[1:])
def test_every_string_the_page_script_asks_for_is_in_the_pack(lang):
    pack = _pack(lang)
    keys = _script_keys()
    missing = sorted(key for key in keys if not pack.get(key))
    assert not missing, (
        f"[{lang}] {len(missing)} client strings would stay English: "
        f"{[(k, keys[k]) for k in missing[:6]]}")


@pytest.mark.parametrize("lang", OFFERED)
def test_pack_and_catalog_agree_where_both_have_a_string(lang):
    """The runtime merges the pack and then the server catalog, which wins.

    Two different translations of the same string mean the user sees the
    catalog's text and the pack's text is dead weight - or worse, the two
    disagree between a server-rendered page and a JS-rendered update of it.
    """
    pack = _pack(lang)
    catalog = _catalog(lang)
    conflicts = []
    for key, value in pack.items():
        message = catalog.get(key)
        if message is not None and message.string and message.string != value:
            conflicts.append((key, value, message.string))
    assert not conflicts, f"[{lang}] pack/catalog disagreements: {conflicts[:5]}"


def test_the_packs_offer_the_same_languages_as_the_application():
    """A language the switcher offers must have a pack to switch to."""
    from settings.languages import SUPPORTED_LANGUAGES

    for lang in SUPPORTED_LANGUAGES:
        assert (PACKS_DIR / f"{lang}.js").exists(), f"no locale pack for {lang}"


# ---------------------------------------------------------------------------
# 3. The rendered page
# ---------------------------------------------------------------------------

def _set_language(client, lang):
    resp = client.get(f"/set_language/{lang}")
    assert resp.status_code in (200, 302)


@pytest.fixture(autouse=True)
def _restore_english(admin_client):
    """``/set_language`` persists ``system.language`` system-wide."""
    yield
    admin_client.get("/set_language/en")


@pytest.mark.parametrize("lang", ("ar", "he", "fa"))
def test_the_ingestion_page_renders_in_the_selected_language(admin_client, lang):
    _set_language(admin_client, lang)
    html = admin_client.get("/operations/input").get_data(as_text=True)

    assert f'<html lang="{lang}"' in html
    if lang in ("ar", "he", "fa"):
        assert 'dir="rtl"' in html

    catalog = _catalog(lang)
    # A handful of the page's own strings must appear translated, and the
    # English source must not be on the page at all.
    for english in ("Choose what to ingest", "Input mode", "Preflight, then start"):
        translated = catalog.get(english).string
        assert translated in html, f"[{lang}] {english!r} not rendered as {translated!r}"
        assert english not in html, f"[{lang}] English source {english!r} still rendered"


@pytest.mark.parametrize("lang", ("ar", "he", "fa"))
def test_the_sidebar_offers_one_way_into_ingestion(admin_client, lang):
    """The duplicate shortcut is gone, in every language."""
    _set_language(admin_client, lang)
    html = admin_client.get("/operations/input").get_data(as_text=True)

    ingestion_links = re.findall(r'data-endpoint="operations_input_page"', html)
    assert len(ingestion_links) == 1, (
        f"the sidebar has {len(ingestion_links)} ingestion shortcuts; "
        "the retired upload page's shortcut must not come back")
    assert "bi-cloud-upload" not in html.split('class="sidebar-nav"', 1)[1].split("</ul>", 1)[0], (
        "the retired 'Upload Files' sidebar entry is back")
