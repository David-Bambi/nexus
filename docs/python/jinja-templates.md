# Jinja2 templates in Nexus

Jinja2 is Flask's default template engine: HTML files with a small
templating language mixed in, rendered server-side into plain HTML
strings. Routes in `src/web/routes_pages.py` never build HTML by hand —
they call `render_template()` and let a `.html` file under
`src/web/templates/` do it.

## `render_template()`

`Flask(__name__, template_folder="web/templates", ...)` in `src/app.py`
(line 29) tells Flask where to look. `render_template(name, **kwargs)`
finds `name` under that folder, fills in the variables passed as keyword
arguments, and returns the resulting HTML string:

```python
# src/web/routes_pages.py
return render_template("projects.html", projects=projects.list(session), error=error)
return render_template("project.html", project=project)
```

`projects.html` gets a `projects` variable and an `error` variable in
scope; `project.html` gets a `project` variable. Nothing else from the
Python side is visible inside the template unless it's passed in this
way.

## Variable interpolation: `{{ }}`

`{{ expr }}` evaluates `expr` and inserts the result as text. It supports
attribute access, dict/index lookups, and function calls, with the same
semantics as Python:

```jinja
{{ project.name }}
```

(`src/web/templates/project.html`, line 8) — `project` is the SQLAlchemy
model instance passed in from the route; `.name` reads its `name`
column, same as it would in Python.

## Control flow: `{% %}`

`{% %}` tags run logic but don't themselves render anything — only the
`{{ }}` expressions and plain HTML inside them do.

**Loop**, from `projects.html`:

```jinja
{% for project in projects %}
    <li>...</li>
{% else %}
    <li>No projects yet.</li>
{% endfor %}
```

`{% else %}` here belongs to the `for`, not to an `if` — it runs only
when the loop body executed zero times (`projects` is empty). No
separate "is the list empty" check is needed.

**Conditional**, from `project.html`:

```jinja
{% if project.description %}
<p>{{ project.description }}</p>
{% endif %}
```

Renders the paragraph only if `project.description` is truthy — skips it
for `None` or an empty string.

## Template inheritance: `{% extends %}` / `{% block %}`

`base.html` is the shared page skeleton. It declares named holes with
`{% block %}`:

```jinja
<!-- src/web/templates/base.html -->
<title>{% block title %}Nexus{% endblock %}</title>
...
{% block content %}{% endblock %}
```

A child template opens with `{% extends "base.html" %}` and fills those
same-named blocks in; everything outside a `{% block %}` in the child is
ignored, everything inside `base.html` but outside its blocks (the
`<head>`, `<body>` tags) comes along unchanged:

```jinja
<!-- src/web/templates/projects.html -->
{% extends "base.html" %}
{% block title %}Projects — Nexus{% endblock %}
{% block content %}
<h1>Projects</h1>
...
{% endblock %}
```

Both `projects.html` and `project.html` extend `base.html` this way,
each overriding `title` and `content` with its own markup.

## `url_for()`

`url_for(endpoint, **kwargs)` generates a URL from a route's
blueprint-qualified function name instead of a hardcoded path string.
Real call sites, both in `projects.html`:

```jinja
<a href="{{ url_for('pages.project_detail', key=project.key) }}">{{ project.name }}</a>
...
<form method="post" action="{{ url_for('pages.projects_list') }}">
```

`'pages.project_detail'` and `'pages.projects_list'` refer to the
`bp = Blueprint("pages", ...)` view functions of the same name in
`src/web/routes_pages.py`; `key=project.key` fills the `<key>` part of
`@bp.route("/projects/<key>")`. If that route's path ever changes, every
template calling `url_for()` for it updates automatically — no path
string to find and fix by hand.

## Auto-escaping

`{{ }}` output is HTML-escaped by default for `.html` templates: `<`
becomes `&lt;`, `&` becomes `&amp;`, etc. So a project `name` or
`description` containing `<script>` or stray markup renders as inert
text in `{{ project.name }}` rather than being injected into the page —
this is on by default, nothing in this project's templates turns it off.
