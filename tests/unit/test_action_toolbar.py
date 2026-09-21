"""The action toolbar's contract: rendered, translated, run, and obeyed.

The toolbar is a shared component, and the risk in a shared component is that
its boundary moves one page at a time until it knows what a "file" is and what
"export" does. So the boundary is pinned here instead:

* the component renders groups, buttons, icons, states and accessibility, and
  the no-selection state of a bulk action;
* the runtime (`static/js/modules/core/action-toolbar.js`) keeps the scope on
  screen as the reader selects, and knows nothing else - no action name, no
  endpoint, no listener;
* the page owns selection calculation, business logic, API calls and the
  outcome;
* the phrases are the catalogs', not the runtime's, so a bulk action's scope is
  said in the reader's language.

`Sources` and `Sides` are the reference pair: same component, different page
data, same runtime contract, different business behaviour. They are asserted
against the *served* pages, not against the templates, and the runtime is
driven through node against the bar the server really rendered.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import jinja2
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TEMPLATES = PROJECT_ROOT / "templates"
RUNTIME = PROJECT_ROOT / "static/js/modules/core/action-toolbar.js"
HARNESS = PROJECT_ROOT / "tests/js/action_toolbar_smoke.mjs"

#: A row must exist for "one binding per row" to mean anything: the pages are
#: empty on a fresh database, so the pair is seeded the way the product seeds
#: itself - through the API, not through the templates.
def _seed(admin_client):
    admin_client.post("/api/input/sources",
                      json={"name": "toolbar-reference-source", "job": "analyst",
                            "country": "NL"})
    admin_client.post("/api/input/sides", json={"name": "toolbar-reference-side"})


#: The reference pair: page, bar id, the words, and the bulk buttons.
REFERENCE_PAGES = (
    ("/sources", "sourcesActionBar", "sources", "source",
     ("bulkExportBtn", "bulkUpdateBtn"), "sources-list-page.js", "source-checkbox"),
    ("/sides", "sidesActionBar", "sides", "side",
     ("bulkExportBtn", "bulkUpdateBtn"), "sides-list-page.js", "side-checkbox"),
)

#: Phrases the runtime composes. They must exist, translated, in every
#: maintained catalog: a scope sentence that only exists in English is how a
#: bulk action ends up saying something the reader cannot read.
PHRASES = ("Select {noun} first", "{count} {noun} selected",
           "{count} of {total} {noun} selected")
MAINTAINED = ("ar", "he", "fa", "hr")


@pytest.fixture()
def render():
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True)
    environment.globals["_"] = lambda text: text

    def render_source(source: str) -> str:
        return environment.from_string(source).render()

    return render_source


def bar(render, noun="sources", singular="source", total=27):
    """The bar as `Sources`/`Sides` render it, with both bulk actions."""
    return render(
        "{% from 'components/action_toolbar.html' import action_toolbar,"
        " action_group, action_button, bulk_action_button, selection_summary %}"
        "{% call action_toolbar(id='sourcesActionBar', label=_('Actions')) %}"
        "{% call action_group(_('Selection:')) %}"
        "{{ action_button(_('Select All'), icon='bi-check-square', onclick='selectAll()') }}"
        "{{ action_button(_('Select None'), icon='bi-square', onclick='selectNone()') }}"
        "{% endcall %}"
        "{% call action_group(_('Bulk Actions:')) %}"
        f"{{{{ selection_summary({total}, _({noun!r}), _({singular!r})) }}}}"
        "{{ bulk_action_button(_('Export Selected'), icon='bi-download',"
        " onclick='bulkExport()', tone='outline-primary', id='bulkExportBtn',"
        f" noun=_({noun!r})) }}}}"
        "{{ bulk_action_button(_('Edit Selected'), icon='bi-pencil',"
        " onclick='bulkUpdate()', tone='outline-warning', id='bulkUpdateBtn',"
        f" noun=_({noun!r})) }}}}"
        "{% endcall %}{% endcall %}")


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
class TestTheComponentRendersTheContract:
    def test_the_bar_names_itself_and_says_what_it_is(self, render):
        out = bar(render)
        assert 'role="toolbar"' in out
        assert 'aria-label="Actions"' in out
        assert 'id="sourcesActionBar"' in out
        assert 'data-action-toolbar' in out

    def test_a_bulk_action_without_a_selection_is_disabled_and_says_why(self, render):
        out = bar(render)
        export = re.search(r"<button[^>]*id=\"bulkExportBtn\"[^>]*>", out, re.S).group(0)
        assert " disabled" in export
        assert 'aria-disabled="true"' in export
        assert "onclick" not in export, "a bulk action ran before a scope was known"
        assert 'aria-label="Export Selected: Select sources first"' in export

    def test_the_scope_is_a_live_region_carrying_the_words_the_runtime_needs(self, render):
        out = bar(render)
        summary = re.search(r"<span[^>]*data-selection-summary[^>]*>.*?</span>", out, re.S).group(0)
        assert 'role="status"' in summary
        assert 'aria-live="polite"' in summary
        assert 'data-noun="sources"' in summary
        assert 'data-noun-singular="source"' in summary
        assert 'data-total="27"' in summary
        assert "Select sources first" in summary
        # The phrases travel with the bar as data: the runtime fills them in
        # rather than composing English of its own.
        assert 'data-text-select-first="Select {noun} first"' in out
        assert 'data-text-selected="{count} {noun} selected"' in out
        assert 'data-text-all-selected="{count} of {total} {noun} selected"' in out

    def test_a_bulk_action_carries_its_classification_for_the_runtime(self, render):
        out = bar(render)
        for button in re.findall(r"<button[^>]*data-bulk-action[^>]*>", out, re.S):
            assert 'data-action-label="' in button
        assert out.count("data-bulk-action") == 2

    def test_a_page_action_is_not_a_bulk_action(self, render):
        """`Apply Filters` is a page action: never enabled or disabled by a count."""
        out = render(
            "{% from 'components/action_toolbar.html' import action_button %}"
            "{{ action_button(_('Apply Filters'), icon='bi-funnel', submit=True, tone='primary') }}"
            "{{ action_button(_('Reset'), icon='bi-arrow-counterclockwise', href='/reset') }}")
        assert 'type="submit"' in out
        assert 'href="/reset"' in out
        assert "data-bulk-action" not in out


class TestThePhrasesAreTheCatalogs:
    def test_every_phrase_the_toolbar_composes_is_translated_everywhere(self):
        """No English invented in the runtime, and none left behind either."""
        import re as _re

        missing = []
        for language in MAINTAINED:
            text = (PROJECT_ROOT / "translations" / language
                    / "LC_MESSAGES" / "messages.po").read_text(encoding="utf-8")
            for phrase in PHRASES + ("source", "side"):
                block = _re.search(
                    r'^msgid "' + _re.escape(phrase) + r'"\nmsgstr "(.*)"$',
                    text, _re.M)
                if block is None or not block.group(1).strip():
                    missing.append(f"{language}: {phrase}")
        assert not missing, f"the toolbar would fall back to English: {missing}"

    def test_the_toolbar_names_no_action_of_its_own(self):
        """Every action name in the component comes from the page's call."""
        source = RUNTIME.read_text(encoding="utf-8")
        for name in ("delete", "export", "edit", "upload", "archive"):
            assert f"'{name}" not in source.lower().replace("selected", ""), name


# ---------------------------------------------------------------------------
# The runtime
# ---------------------------------------------------------------------------
class TestTheRuntimeStaysSmallAndInert:
    def test_it_exposes_one_method_and_that_method_takes_numbers_and_words(self):
        source = RUNTIME.read_text(encoding="utf-8")
        assert "window.ActionToolbar = { sync: sync }" in source
        assert "function sync(root, spec)" in source

    def test_it_performs_nothing_and_binds_nothing(self):
        """No network, no storage, no listeners, no endpoints, no actions."""
        source = RUNTIME.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        for forbidden in ("fetch(", "XMLHttpRequest", "addEventListener",
                          "localStorage", "sessionStorage", "/api/", "onclick="):
            assert forbidden not in code, (
                f"the toolbar runtime reached for {forbidden!r}: the boundary "
                "between presentation and business behaviour has moved")

    @pytest.mark.parametrize("module,bar_id", (("sources-list-page.js", "sourcesActionBar"),
                                               ("sides-list-page.js", "sidesActionBar")))
    def test_the_page_no_longer_decides_how_the_scope_looks(self, module, bar_id):
        source = (PROJECT_ROOT / "static/js/pages" / module).read_text(encoding="utf-8")
        assert f"ActionToolbar.sync('{bar_id}'" in source
        assert "bulkExportBtn.disabled" not in source
        assert "bulkUpdateBtn.disabled" not in source
        assert "document.addEventListener('change'" not in source, (
            "a second listener for the same change would update the toolbar "
            "twice per click")

    def test_the_shell_loads_the_runtime_the_way_it_loads_the_others(self):
        shell = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        assert "js/modules/core/action-toolbar.js" in shell


# ---------------------------------------------------------------------------
# The runtime against the bar the server rendered
# ---------------------------------------------------------------------------
class TestTheRuntimeObeysTheRenderedBar:
    def test_the_runtime_turns_the_served_bar_into_the_contract(self, render, tmp_path):
        """Node runs the shipped module against the shipped markup."""
        node = shutil.which("node")
        if node is None:
            pytest.skip("node is not installed")

        html = bar(render)
        opening = re.search(r'<div class="action-bar[^>]*>', html, re.S).group(0)
        attributes = dict(re.findall(r'(data-[\w-]+)="([^"]*)"', opening))
        labels = {}
        for button in re.findall(r"<button[^>]*data-bulk-action[^>]*>", html, re.S):
            label = re.search(r'data-action-label="([^"]*)"', button)
            name = re.search(r'aria-label="([^"]*)"', button)
            if label and name:
                labels[label.group(1)] = name.group(1)
        fixture = tmp_path / "bar.json"
        fixture.write_text(json.dumps({"attributes": attributes,
                                       "bulk_labels": labels}), encoding="utf-8")

        proc = subprocess.run(
            [node, str(HARNESS), f"--bar-json={fixture}"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "checks passed" in proc.stdout
        assert "FAIL" not in proc.stdout, proc.stdout


# ---------------------------------------------------------------------------
# The reference pair, as served
# ---------------------------------------------------------------------------
class TestSourcesAndSidesAreTheReferenceImplementation:
    @pytest.mark.parametrize("url,bar_id,noun,singular,bulk_ids,module,checkbox",
                             REFERENCE_PAGES)
    def test_the_served_page_renders_the_no_selection_state(
            self, app, admin_client, url, bar_id, noun, singular, bulk_ids, module, checkbox):
        resp = admin_client.get(url)
        assert resp.status_code == 200, url
        html = resp.get_data(as_text=True)

        assert f'id="{bar_id}"' in html
        assert 'role="toolbar"' in html
        summary = re.search(r"<span[^>]*data-selection-summary[^>]*>.*?</span>", html, re.S)
        assert summary, f"{url} renders a bar with no scope element"
        assert f'data-noun="{noun}"' in summary.group(0)
        assert f'data-noun-singular="{singular}"' in summary.group(0)
        assert 'role="status"' in summary.group(0)

        for button_id in bulk_ids:
            button = re.search(rf'<button[^>]*id="{button_id}"[^>]*>', html, re.S)
            assert button, f"{url} has no {button_id}"
            markup = button.group(0)
            assert " disabled" in markup, f"{url}: {button_id} was startable with nothing selected"
            assert "aria-disabled=\"true\"" in markup
            assert "onclick" not in markup, f"{url}: {button_id} ran without a scope"
            assert f"Select {noun} first" in markup, (
                f"{url}: {button_id} does not say why it cannot be used")

    @pytest.mark.parametrize("url,bar_id,noun,singular,bulk_ids,module,checkbox",
                             REFERENCE_PAGES)
    def test_one_binding_per_row_and_none_beside_it(
            self, app, admin_client, url, bar_id, noun, singular, bulk_ids, module, checkbox):
        """The row's own handler is the only path that updates the toolbar."""
        _seed(admin_client)
        html = admin_client.get(url).get_data(as_text=True)
        changes = html.count('onchange="updateBulkButtons()"')
        rows = len(re.findall(rf'class="[^"]*{re.escape(checkbox)}', html))
        assert rows > 0, f"{url} renders no rows to select"
        assert changes == rows, (
            f"{url}: {rows} rows but {changes} change handlers - a row would not "
            "reach the toolbar, or would reach it twice")

        page = (PROJECT_ROOT / "static/js/pages" / module).read_text(encoding="utf-8")
        assert "document.addEventListener('change'" not in page

        shell = admin_client.get(url).get_data(as_text=True)
        assert "js/modules/core/action-toolbar.js" in shell, (
            "the page renders a bar but the shell does not load its runtime")
