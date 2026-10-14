---
status: accepted
date: 2026-10-14
---

# 0012 — Plain static CSS and JS

## Status

Accepted.

## Decision

The web UI is styled by one hand-written stylesheet, `src/web/static/app.css`,
and driven by one small vanilla script, `src/web/static/app.js`, both served
by Flask's static folder and linked from `base.html` (the script with
`defer`).

- The stylesheet starts with design tokens on `:root` (colors, spacing,
  type, radius, shadow, content width) and a dark theme that overrides the
  same color tokens under `prefers-color-scheme: dark`. Components use
  tokens only: hex colors appear only in these two blocks.
- No CSS framework, no bundler, no npm.
- Templates hold no inline `style=` attribute, no `<script>` block and no
  inline `on*=` handler. Behaviour is attached through data attributes
  (`data-confirm`, `data-autosubmit`) handled by `app.js`; everything else
  is plain HTML forms.
- Text and badge colors meet WCAG AA (4.5:1) in both themes, checked by
  `tests/web/test_stylesheet.py`. The template rules are checked by
  `tests/web/test_pages.py`.

HTMX, named in [0003](0003-flask-jinja-htmx.md), is not loaded or used so
far: every interaction is a full-page form post.

Conventions: [UI conventions](../ui.md).

## Why

- Same principle as [0003](0003-flask-jinja-htmx.md): no build step, no
  second toolchain to maintain.
- A local single-user app needs few components; a framework would bring
  far more CSS than used, and override fights.
- One stylesheet and one script are easy to review in a diff; keeping
  styles and behaviour out of templates leaves templates as structure only.
- Tokens make the dark theme a single block and keep colors consistent.

## Alternative rejected

- A CSS framework (Pico, Tailwind): Pico's defaults would still need
  overriding, Tailwind needs a build step and puts styling back into the
  markup.
- Per-page inline scripts: duplicated, hard to test, and they mix
  behaviour into templates.
