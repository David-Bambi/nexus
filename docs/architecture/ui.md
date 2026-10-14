# UI conventions

How the web UI is built and how to extend it. Decision:
[0012](adr/0012-plain-static-css-and-js.md).

## Files

- `src/web/templates/base.html`: header (brand, nav, capture bar), skip
  link "Skip to content" to `<main class="container" id="content">`. The
  nav marks the current section with `aria-current="page"`, matched by
  path prefix.
- `src/web/templates/_components.html`: shared macros, imported as
  `{% import "_components.html" as ui %}`.
- `src/web/static/app.css`: the only stylesheet. Sections in order: design
  tokens, dark theme, reset, base typography, then components (app shell,
  forms and buttons, lists/badges/ref chips, dashboard, version page,
  detail pages and timeline, remaining pages, accessibility).
- `src/web/static/app.js`: the only script.

## Tokens

Defined on `:root`: colors (`--color-*`), spacing scale `--space-1` to
`--space-7` (rem), type scale (`--text-*`, `--font-*`, `--leading`),
`--radius*`, `--shadow`, `--content-width`. The dark theme overrides the
same color tokens under `prefers-color-scheme: dark`. Outside these two
blocks, never hard-code a color, size or spacing: use a token.

## Adding a component

1. Add a macro to `_components.html`, with a `{# #}` comment saying what it
   renders and what it expects.
2. Add its styles to the matching section of `app.css`, using tokens only.
3. Use it from pages via `ui.<macro>(...)`. Fragments that need the page's
   variables rather than arguments stay `_name.html` includes
   (`_clarify_form.html`, `_task_state_form.html`).

## Badges

`ui.badge(name)` renders `<span class="badge badge-<name lower>">` for a
task state, version status or project status. A state picks its color by
setting `--badge-color` (doing/in progress: accent; waiting: warning;
done/released/active: success; cancelled: danger; others: muted text). The
background is `color-mix` of that color at 12% with `--color-surface`, not
transparency, so contrast is the same on any background.

## Behaviour

No inline `style=`, no `<script>` block, no inline `on*=` handler in
templates (enforced by `tests/web/test_pages.py`). `app.js` handles:

- `c` outside a text field focuses the capture box; with Ctrl/Cmd/Alt it is
  left alone (Ctrl+C copies).
- `data-confirm="<value>"` on an input: its form's submit button (rendered
  `disabled`) is enabled only once that exact value is typed (delete
  project, delete version).
- `data-autosubmit` on a control: submits its form on change (DoD
  checkbox).
- `#dod-rows` in the new-version form: add/remove criterion rows (one is
  kept), Enter adds a row.

Pure presentation stays in CSS, e.g. the waiting reason field of the state
form is shown only when `WAITING` is selected, via `:has()`.

## Contrast

`tests/web/test_stylesheet.py` parses the tokens of both themes and checks
WCAG AA (at least 4.5:1) for text on its backgrounds and for each badge on
its tint. Run it after changing any color token.
