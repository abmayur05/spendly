# Copilot Instructions

## Project Overview

An educational Flask expense tracker built step-by-step (Steps 1–9). The app uses raw SQLite (no ORM), Jinja2 templates, session-based auth, and vanilla JS. Each step adds a feature; placeholder routes are already stubbed in `app.py` with comments marking which step implements them.

## Commands

```bash
# Run the app (http://localhost:5001)
python app.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_auth.py

# Run a single test by name
pytest tests/test_auth.py::test_login_valid_user
```

> Activate `venv` first: `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Unix).

## Architecture

- **`app.py`** — all routes in one flat file (no blueprints). Routes are RESTful: `GET/POST /expenses/<id>/edit`, etc. Form submissions POST to the same route that renders the form; on success, redirect.
- **`database/db.py`** — SQLite helpers: `get_db()` (returns a connection with `row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`), `init_db()` (CREATE TABLE IF NOT EXISTS), `seed_db()`.
- **`templates/`** — all templates extend `base.html` via `{% extends "base.html" %}`. Blocks used: `title`, `content`, `scripts`.
- **`static/css/style.css`** — design system via CSS custom properties; do not add inline styles.

## Database Conventions

- Two tables: `users` (id, name, email, password_hash) and `expenses` (id, user_id, amount, category, date, description). Foreign key: `expenses.user_id → users.id`.
- Always use `get_db()` inside routes; never open a raw `sqlite3.connect()` in `app.py`.
- Access rows as dicts via `row_factory = sqlite3.Row`.

## Template Conventions

- Display server-side errors with `{% if error %}<div class="auth-error">{{ error }}</div>{% endif %}`.
- Generate all URLs with `{{ url_for('route_name') }}`; never hardcode paths.
- Page-specific JS goes in `{% block scripts %}{% endblock %}`.

## CSS Conventions

Use the defined CSS custom properties and component classes — do not introduce new color values or utility classes.

**Key variables:** `--ink`, `--accent` (green), `--accent-2` (orange), `--danger`, `--paper`, `--border`.

**Button classes:** `.btn-primary` (solid), `.btn-ghost` (outlined), `.btn-submit` (full-width form button).

**Form classes:** `.form-group`, `.form-label`, `.form-input`.

**Legal/prose page classes:** `.legal-section`, `.legal-container`, `.legal-header`, `.legal-card`. Use these for Terms, Privacy Policy, and similar document pages instead of auth classes.

**Breakpoints:** `@media (max-width: 900px)` and `@media (max-width: 600px)`.

## Authentication Pattern

- Session-based using Flask's built-in `session` dict. Store `user_id` on login.
- Protected routes check `if 'user_id' not in session` and redirect to `/login`.
- Passwords hashed with `werkzeug.security` (`generate_password_hash` / `check_password_hash`).
- Flow: `POST /register` → redirect to `/login` → `POST /login` → redirect to `/profile`.

## Form Processing Pattern

```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # validate → render form with error, or redirect on success
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')
```
