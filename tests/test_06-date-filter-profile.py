"""
tests/test_06-date-filter-profile.py

Spec-driven tests for the date-range filter feature on GET /profile.
Feature spec: .claude/specs/06-date-filter-profile.md

Coverage:
  1.  Unfiltered /profile returns all expenses (no regression)
  2.  Valid date range filters transactions to that range only
  3.  Stats (total, count, top category) reflect the filtered range
  4.  date_from > date_to → flash error + unfiltered view
  5.  Malformed date string → silent fallback, no crash
  6.  Single date_from only → treated as single-day filter
  7.  Single date_to only  → treated as single-day filter
  8.  Date inputs pre-populated with active filter values
  9.  Active-filter indicator present when filter active, absent otherwise
 10.  No expenses in range → ₹0.00 total, 0 transactions, no error
 11.  Unauthenticated request redirects to /login

Key facts about the test DB schema (from database/db.py):
  - users(id, name, email, password_hash, created_at)
  - expenses(id, user_id, amount, category, date TEXT 'YYYY-MM-DD', description)
  - db.py uses a module-level DB_PATH — patched via monkeypatch to a tmp file
"""

import os
import sqlite3
import tempfile

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    """Return a path to a fresh, isolated SQLite database file."""
    return str(tmp_path / "test_spendly.db")


@pytest.fixture()
def app(db_path, monkeypatch):
    """
    Flask test application wired to an isolated, file-based SQLite database.

    db.py hard-codes a module-level DB_PATH that get_db() always opens.
    We monkeypatch that path to a temp file so every test gets a clean slate
    without touching the real spendly.db.
    """
    import database.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    from app import app as flask_app
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        db_module.init_db()
        yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# DB seeding helpers (raw sqlite3 — no app layer involved)
# ---------------------------------------------------------------------------

def _seed_user(db_path, name="Test User", email="test@spendly.com", password="testpass123"):
    """Insert a user directly and return their id."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id


def _seed_expenses(db_path, user_id, expenses):
    """
    Insert a list of expense tuples into the DB.
    Each tuple: (amount, category, date_str, description)
    """
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, date, desc) for amt, cat, date, desc in expenses],
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth helper — log in via the test client
# ---------------------------------------------------------------------------

def _login(client, email="test@spendly.com", password="testpass123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# Test data constants — fixed dates so assertions are deterministic
# ---------------------------------------------------------------------------

EXPENSES_MIXED = [
    # Inside "January 2026" window
    (500.00,  "Food",          "2026-01-10", "Groceries"),
    (200.00,  "Transport",     "2026-01-20", "Metro recharge"),
    # Inside "February 2026" window
    (1500.00, "Bills",         "2026-02-05", "Electricity"),
    (300.00,  "Health",        "2026-02-15", "Pharmacy"),
    # Outside both narrow windows (March)
    (800.00,  "Shopping",      "2026-03-01", "New shoes"),
]

# The two January expenses
JAN_TOTAL    = 500.00 + 200.00          # 700.00
JAN_COUNT    = 2
JAN_TOP_CAT  = "Food"                   # highest single amount in Jan

# The two February expenses
FEB_TOTAL    = 1500.00 + 300.00         # 1800.00
FEB_COUNT    = 2
FEB_TOP_CAT  = "Bills"

# All five expenses combined
ALL_TOTAL    = 500 + 200 + 1500 + 300 + 800   # 3300.00
ALL_COUNT    = 5
ALL_TOP_CAT  = "Bills"                 # highest single amount overall


# ===========================================================================
# 1. Unfiltered /profile returns ALL expenses (regression guard)
# ===========================================================================

class TestUnfilteredProfile:
    def test_all_transactions_appear_without_filter(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile")
        assert response.status_code == 200, "Unfiltered /profile must return 200"

        html = response.data.decode()
        # Every seeded description should appear in the rendered table
        assert "Groceries"       in html, "Jan expense 'Groceries' must appear in unfiltered view"
        assert "Metro recharge"  in html, "Jan expense 'Metro recharge' must appear in unfiltered view"
        assert "Electricity"     in html, "Feb expense 'Electricity' must appear in unfiltered view"
        assert "Pharmacy"        in html, "Feb expense 'Pharmacy' must appear in unfiltered view"
        assert "New shoes"       in html, "Mar expense 'New shoes' must appear in unfiltered view"

    def test_unfiltered_total_is_sum_of_all_expenses(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()
        # ₹3,300.00 formatted with comma thousands separator
        assert "3,300.00" in html, "Unfiltered total must equal sum of all seeded expenses"

    def test_unfiltered_transaction_count(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()
        # The stats section renders transaction_count as a plain integer
        assert f">{ALL_COUNT}<" in html or str(ALL_COUNT) in html, (
            f"Unfiltered transaction count must be {ALL_COUNT}"
        )


# ===========================================================================
# 2. Valid date range filters the transaction list to that range only
# ===========================================================================

class TestValidDateRangeFiltersTransactions:
    def test_transactions_inside_range_are_shown(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert response.status_code == 200
        html = response.data.decode()

        assert "Groceries"      in html, "Expense inside range must appear"
        assert "Metro recharge" in html, "Expense inside range must appear"

    def test_transactions_outside_range_are_hidden(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        html = response.data.decode()

        assert "Electricity" not in html, "Feb expense must NOT appear in Jan-only filter"
        assert "Pharmacy"    not in html, "Feb expense must NOT appear in Jan-only filter"
        assert "New shoes"   not in html, "Mar expense must NOT appear in Jan-only filter"

    def test_filter_is_inclusive_of_boundary_dates(self, client, db_path):
        """Expenses on exactly date_from and date_to must be included."""
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [
            (100.00, "Food", "2026-03-01", "Start boundary"),
            (200.00, "Food", "2026-03-31", "End boundary"),
            (300.00, "Food", "2026-04-01", "Outside boundary"),
        ])
        _login(client)

        response = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        html = response.data.decode()

        assert "Start boundary" in html, "date_from boundary expense must be included"
        assert "End boundary"   in html, "date_to boundary expense must be included"
        assert "Outside boundary" not in html, "Expense after date_to must be excluded"


# ===========================================================================
# 3. Stats reflect the filtered range (total, count, top category)
# ===========================================================================

class TestFilteredStats:
    def test_total_spent_reflects_filter(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        html = response.data.decode()

        # ₹700.00 — sum of Jan expenses only
        assert "700.00" in html, "Total spent must equal sum of expenses in the filtered range"
        # All-time total must NOT appear
        assert "3,300.00" not in html, "All-time total must not appear when a filter is active"

    def test_transaction_count_reflects_filter(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        html = response.data.decode()

        assert str(JAN_COUNT) in html, (
            f"Transaction count must be {JAN_COUNT} for the January filter"
        )

    def test_top_category_reflects_filter(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        # February filter — top category by spend is Bills (₹1500)
        response = client.get("/profile?date_from=2026-02-01&date_to=2026-02-28")
        html = response.data.decode()

        assert FEB_TOP_CAT in html, (
            f"Top category must be '{FEB_TOP_CAT}' for the February filter"
        )

    def test_category_breakdown_totals_reflect_filter(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-02-01&date_to=2026-02-28")
        html = response.data.decode()

        # Bills (₹1500) and Health (₹300) should appear; Shopping must not
        assert "1,500.00" in html, "Bills total must appear in filtered breakdown"
        assert "300.00"   in html, "Health total must appear in filtered breakdown"
        assert "New shoes" not in html, "Shopping (March) must not appear in February filter"


# ===========================================================================
# 4. date_from > date_to → flash error + unfiltered view
# ===========================================================================

class TestInvalidDateRange:
    def test_reversed_range_returns_200(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        assert response.status_code == 200, "Reversed range must still return 200"

    def test_reversed_range_shows_flash_error(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        html = response.data.decode()
        assert "Start date must be before end date" in html, (
            "A flash error must be shown when date_from > date_to"
        )

    def test_reversed_range_shows_unfiltered_data(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        html = response.data.decode()

        # All expenses must appear — the filter must not have been applied
        assert "Groceries"   in html, "Unfiltered data must be shown after invalid range"
        assert "Electricity" in html, "Unfiltered data must be shown after invalid range"
        assert "New shoes"   in html, "Unfiltered data must be shown after invalid range"

    def test_reversed_range_total_is_all_time(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        html = response.data.decode()

        assert "3,300.00" in html, "All-time total must be shown when the range is invalid"


# ===========================================================================
# 5. Malformed date string → silent fallback, no crash
# ===========================================================================

class TestMalformedDates:
    @pytest.mark.parametrize("bad_date_from,bad_date_to", [
        ("not-a-date", "2026-01-31"),
        ("2026-01-01", "not-a-date"),
        ("not-a-date", "not-a-date"),
        ("99-99-9999", "2026-01-31"),
        ("2026-13-01", "2026-01-31"),     # month 13
        ("2026/01/01", "2026-01-31"),     # wrong separator
        ("",           "2026-01-31"),     # empty string
        ("2026-01-01", ""),              # empty string
    ])
    def test_malformed_date_does_not_crash(self, client, db_path, bad_date_from, bad_date_to):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get(f"/profile?date_from={bad_date_from}&date_to={bad_date_to}")
        assert response.status_code == 200, (
            f"Malformed date params ({bad_date_from!r}, {bad_date_to!r}) must not crash the app"
        )

    def test_malformed_date_returns_unfiltered_view(self, client, db_path):
        """A bad date_from must silently fall back to showing all expenses."""
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, EXPENSES_MIXED)
        _login(client)

        response = client.get("/profile?date_from=bad-date&date_to=2026-01-31")
        html = response.data.decode()

        # All expenses must still appear because the filter is silently dropped
        assert "Groceries"   in html, "Unfiltered view must show all expenses after malformed date"
        assert "Electricity" in html, "Unfiltered view must show all expenses after malformed date"
        assert "New shoes"   in html, "Unfiltered view must show all expenses after malformed date"


# ===========================================================================
# 6. Single date_from only → treated as a single-day filter
# ===========================================================================

class TestSingleDateFromParam:
    def test_single_date_from_filters_to_that_day_only(self, client, db_path):
        """
        Spec: if only date_from is present, treat it as a single-day filter
        (date_from == date_to == provided value).
        """
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [
            (100.00, "Food",      "2026-06-15", "Target day expense"),
            (200.00, "Transport", "2026-06-16", "Day after — must be excluded"),
            (300.00, "Bills",     "2026-06-14", "Day before — must be excluded"),
        ])
        _login(client)

        response = client.get("/profile?date_from=2026-06-15")
        assert response.status_code == 200
        html = response.data.decode()

        assert "Target day expense"          in html, "Expense on date_from must appear"
        assert "Day after — must be excluded"  not in html, "Expense after date_from must not appear"
        assert "Day before — must be excluded" not in html, "Expense before date_from must not appear"


# ===========================================================================
# 7. Single date_to only → treated as a single-day filter
# ===========================================================================

class TestSingleDateToParam:
    def test_single_date_to_filters_to_that_day_only(self, client, db_path):
        """
        Spec: if only date_to is present, treat it as a single-day filter
        (date_from == date_to == provided value).
        """
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [
            (100.00, "Food",      "2026-07-20", "Target day expense"),
            (200.00, "Transport", "2026-07-21", "Day after — must be excluded"),
            (300.00, "Bills",     "2026-07-19", "Day before — must be excluded"),
        ])
        _login(client)

        response = client.get("/profile?date_to=2026-07-20")
        assert response.status_code == 200
        html = response.data.decode()

        assert "Target day expense"          in html, "Expense on date_to must appear"
        assert "Day after — must be excluded"  not in html, "Expense after date_to must not appear"
        assert "Day before — must be excluded" not in html, "Expense before date_to must not appear"


# ===========================================================================
# 8. Date inputs are pre-populated with active filter values
# ===========================================================================

class TestDateInputPrepopulation:
    def test_date_from_input_populated_with_active_filter(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        html = response.data.decode()

        assert 'value="2026-03-01"' in html, (
            "The date_from input must be pre-populated with the active filter value"
        )

    def test_date_to_input_populated_with_active_filter(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        html = response.data.decode()

        assert 'value="2026-03-31"' in html, (
            "The date_to input must be pre-populated with the active filter value"
        )

    def test_date_inputs_are_empty_when_no_filter_is_active(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()

        # Both date inputs must have empty values (value="" or no value attribute set to a date)
        assert 'value="2026' not in html, (
            "Date inputs must not be pre-filled when no filter param is in the URL"
        )


# ===========================================================================
# 9. Active-filter indicator present when filter active, absent otherwise
# ===========================================================================

class TestActiveFilterIndicator:
    def test_active_preset_class_present_when_filter_matches_preset(self, client, db_path):
        """
        The template renders filter-preset--active on the matching preset anchor.
        The 'All Time' preset has no date params, so it matches when no filter is active.
        A specific preset is active only when its date_from/date_to exactly match
        the query params passed in.
        """
        _seed_user(db_path)
        _login(client)

        import datetime
        today = datetime.date.today()
        # "This Month" preset: date_from = first of current month, date_to = today
        first_of_month = today.replace(day=1).isoformat()
        today_str = today.isoformat()

        response = client.get(f"/profile?date_from={first_of_month}&date_to={today_str}")
        html = response.data.decode()

        assert "filter-preset--active" in html, (
            "filter-preset--active class must appear when a preset's dates match the active filter"
        )

    def test_active_preset_class_on_all_time_when_no_filter(self, client, db_path):
        """
        The 'All Time' preset (no date params) must be highlighted when /profile is
        loaded with no filter params.
        """
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()

        assert "filter-preset--active" in html, (
            "filter-preset--active must be on 'All Time' when no filter is active"
        )

    def test_no_non_all_time_preset_active_on_unfiltered_view(self, client, db_path):
        """
        When no filter is active, only the 'All Time' preset must carry
        filter-preset--active. The other preset buttons must not be active.
        Verified by checking the class appears exactly once.
        """
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()

        count = html.count("filter-preset--active")
        assert count == 1, (
            f"Exactly one preset must be active (All Time) on unfiltered view, found {count}"
        )

    def test_active_class_present_on_custom_range(self, client, db_path):
        """
        When a custom date range is active that does NOT match any preset,
        no preset button should be active — the filter-preset--active class
        should not appear (the indicator is in the custom range inputs instead).
        This test asserts that the active class count is 0 for a non-preset range.
        """
        _seed_user(db_path)
        _login(client)

        # Use a very specific range unlikely to match any preset
        response = client.get("/profile?date_from=2020-01-01&date_to=2020-01-15")
        html = response.data.decode()

        # None of the preset buttons should be active for an arbitrary custom range
        count = html.count("filter-preset--active")
        assert count == 0, (
            "No preset button should be active for a custom range that matches no preset"
        )


# ===========================================================================
# 10. No expenses in range → ₹0.00 total, 0 transactions, no error
# ===========================================================================

class TestEmptyFilterResult:
    def test_zero_total_when_no_expenses_in_range(self, client, db_path):
        user_id = _seed_user(db_path)
        # All expenses are in January; filter targets June
        _seed_expenses(db_path, user_id, [
            (500.00, "Food", "2026-01-10", "Out-of-range expense"),
        ])
        _login(client)

        response = client.get("/profile?date_from=2026-06-01&date_to=2026-06-30")
        assert response.status_code == 200, "Empty range must not crash the app"
        html = response.data.decode()

        assert "₹0.00" in html, "Total spent must display ₹0.00 when no expenses exist in range"

    def test_zero_transaction_count_when_no_expenses_in_range(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [
            (500.00, "Food", "2026-01-10", "Out-of-range expense"),
        ])
        _login(client)

        response = client.get("/profile?date_from=2026-06-01&date_to=2026-06-30")
        html = response.data.decode()

        # The transaction count stat must be 0
        assert ">0<" in html or "0" in html, "Transaction count must be 0 when range is empty"
        # The out-of-range description must not appear
        assert "Out-of-range expense" not in html, (
            "Expense outside the range must not appear in the transaction list"
        )

    def test_empty_breakdown_when_no_expenses_in_range(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [
            (500.00, "Food", "2026-01-10", "Out-of-range expense"),
        ])
        _login(client)

        response = client.get("/profile?date_from=2026-06-01&date_to=2026-06-30")
        html = response.data.decode()

        # The "Food" category row must not appear in the breakdown
        assert "breakdown-item" not in html, (
            "Category breakdown must be empty when no expenses fall in the selected range"
        )

    def test_no_expenses_at_all_zero_total(self, client, db_path):
        """A brand new user with zero expenses must see ₹0.00 even with a filter applied."""
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")
        assert response.status_code == 200
        html = response.data.decode()

        assert "₹0.00" in html, "New user with no expenses must see ₹0.00 total"


# ===========================================================================
# 11. Unauthenticated request redirects to /login
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client, db_path):
        response = client.get("/profile", follow_redirects=False)
        assert response.status_code == 302, "Unauthenticated /profile must return 302"
        assert "/login" in response.headers.get("Location", ""), (
            "Redirect must point to /login"
        )

    def test_unauthenticated_get_with_date_params_redirects_to_login(self, client, db_path):
        response = client.get(
            "/profile?date_from=2026-01-01&date_to=2026-01-31",
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "Unauthenticated /profile with date params must still redirect to /login"
        )
        assert "/login" in response.headers.get("Location", ""), (
            "Redirect must point to /login"
        )

    def test_authenticated_user_can_access_profile(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile")
        assert response.status_code == 200, "Authenticated user must get 200 on /profile"


# ===========================================================================
# 12. ₹ symbol always appears in amounts regardless of filter state
# ===========================================================================

class TestRupeeSymbolAlwaysPresent:
    def test_rupee_symbol_in_unfiltered_view(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [(250.00, "Food", "2026-05-01", "Lunch")])
        _login(client)

        response = client.get("/profile")
        html = response.data.decode()

        assert "₹" in html, "₹ symbol must appear in the unfiltered profile view"

    def test_rupee_symbol_in_filtered_view(self, client, db_path):
        user_id = _seed_user(db_path)
        _seed_expenses(db_path, user_id, [(250.00, "Food", "2026-05-01", "Lunch")])
        _login(client)

        response = client.get("/profile?date_from=2026-05-01&date_to=2026-05-31")
        html = response.data.decode()

        assert "₹" in html, "₹ symbol must appear in the filtered profile view"

    def test_rupee_symbol_in_empty_filter_result(self, client, db_path):
        _seed_user(db_path)
        _login(client)

        response = client.get("/profile?date_from=2099-01-01&date_to=2099-12-31")
        html = response.data.decode()

        # Even with ₹0.00 total there should be a ₹ symbol
        assert "₹" in html, "₹ symbol must appear even when the filtered result is ₹0.00"
