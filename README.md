# Spendly

A lightweight personal expense tracker built with Flask and SQLite.

## Features

- User registration and login with hashed passwords
- Session-based authentication
- Expense tracking (in progress)

## Tech Stack

- **Backend:** Python 3.10+, Flask
- **Database:** SQLite
- **Frontend:** Vanilla JS, Jinja2 templates
- **Testing:** pytest, pytest-flask

## Getting Started

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the dev server (http://localhost:5001)
python app.py
```

## Project Structure

```
spendly/
├── app.py              # All routes
├── database/
│   └── db.py           # SQLite helpers
├── templates/
│   ├── base.html       # Shared layout
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   └── js/
└── requirements.txt
```

## Routes

| Route | Status |
|---|---|
| `GET /` | Landing page |
| `GET /register` | User registration |
| `POST /register` | Create account |
| `GET /login` | Login page |
| `POST /login` | Authenticate |
| `GET /logout` | Sign out |
| `GET /profile` | User profile _(coming soon)_ |
| `GET /expenses/add` | Add expense _(coming soon)_ |
| `GET /expenses/<id>/edit` | Edit expense _(coming soon)_ |
| `GET /expenses/<id>/delete` | Delete expense _(coming soon)_ |

## Test Credentials

| Email | Password |
|---|---|
| `demo_test@demo.com` | `demo_test` |

## Running the App

```bash
python app.py
```

- The server starts at **http://localhost:5001**
- Debug mode is on by default — the server reloads automatically on code changes
- The SQLite database is created automatically on first run (no migration step needed)
- To stop the server, press `Ctrl+C`

## Running Tests

```bash
pytest                        # all tests
pytest tests/test_foo.py      # specific file
pytest -k "test_name"         # specific test
pytest -s                     # with output visible
```
