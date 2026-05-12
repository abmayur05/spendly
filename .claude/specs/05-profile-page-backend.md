# Spec: Profile Page Backend Connection

## Overview
This feature replaces all hardcoded data in the `/profile` route with real database queries. Step 4 built the complete profile UI using static Python dicts; Step 5 wires that UI to the `users` and `expenses` tables so every logged-in user sees their own name, email, member-since date, transaction history, per-category totals, and summary stats. No new pages or visual changes are required — this step is purely a backend connection.

## Depends on
- Step 01: Database setup (`users` and `expenses` tables must exist)
- Step 02: Registration (real user rows must be creatable)
- Step 03: Login and Logout (session must store `user_id`; `/profile` must be a protected route)
- Step 04: Profile page UI (template must exist and accept the same context variable shapes)

## Routes
- `GET /profile` — render profile page with live DB data — logged-in only (redirect to `/login` if not authenticated)

No new routes.

## Database changes
No schema changes. The existing `users` and `expenses` tables are sufficient.

## Templates
- **No changes required.** `templates/profile.html` already accepts `user_info`, `stats`, `transactions`, and `categories` context variables with the same shapes used in Step 4. The template is data-agnostic.

## Files to change
- `app.py` — update the `profile()` view to call the new DB helpers instead of using hardcoded dicts
- `database/db.py` — add four new helper functions (see Rules for implementation)

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation

### New DB helpers to add to `database/db.py`

1. **`get_user_by_id(user_id)`**
   - `SELECT id, name, email, created_at FROM users WHERE id = ?`
   - Returns a single `sqlite3.Row` or `None`
   - Used by the profile route to populate `user_info`

2. **`get_expenses_by_user(user_id)`**
   - `SELECT id, amount, category, date, description FROM expenses WHERE user_id = ? ORDER BY date DESC`
   - Returns a list of `sqlite3.Row` objects (all-time, no pagination yet)
   - Used to build the `transactions` list

3. **`get_category_totals(user_id)`**
   - Aggregate query: `SELECT category, SUM(amount) as total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total DESC`
   - Returns rows with `category` and `total` columns
   - Used to build the `categories` list (percentages are computed in the route from these totals)

4. **`get_expense_stats(user_id)`**
   - Single-query aggregation: `SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total FROM expenses WHERE user_id = ?`
   - Returns one row with `count` and `total`
   - Used to populate `stats["total_spent"]` and `stats["transaction_count"]`

### Route update rules
- Call `get_user_by_id(session["user_id"])`; if `None`, call `abort(404)`
- Format `user_info["member_since"]` from `created_at` using `datetime.strptime` + `strftime("%d %B %Y")`
- Derive `user_info["initials"]` from the first letter of each word in `name` (max 2 letters, uppercase)
- Format `stats["total_spent"]` as `"₹{total:,.2f}"` — use INR, not USD
- Derive `stats["top_category"]` from the first row of `get_category_totals()` (highest total); use `"—"` if no expenses
- Build `categories` list as `[{"name": cat, "amount": "₹{total:,.2f}", "pct": int(total / grand_total * 100)}]`; `pct` should sum to ~100 (rounding is fine)
- Build `transactions` list as `[{"date": ..., "description": ..., "category": ..., "amount": "₹{amount:,.2f}"}]`; format `date` as `"%d %b %Y"` (e.g. `"08 Apr 2026"`)
- All DB logic must stay in `database/db.py` — no raw SQL in `app.py`
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

## Definition of done
- [ ] Visiting `/profile` while logged in returns HTTP 200 and shows the logged-in user's real name and email
- [ ] `user_info["member_since"]` matches the account's actual `created_at` date, not a hardcoded string
- [ ] `stats["transaction_count"]` reflects the real number of expense rows for that user in the DB
- [ ] `stats["total_spent"]` reflects the real sum of all expenses for that user, formatted in INR
- [ ] `stats["top_category"]` is the category with the highest total spend for that user
- [ ] The transaction history table lists the user's actual expenses, ordered newest-first
- [ ] The category breakdown section lists real per-category totals and percentages
- [ ] A brand-new user (no expenses) sees `"₹0.00"` total, `0` transactions, and `"—"` as top category
- [ ] A user with expenses sees correct data distinct from the hardcoded demo data
- [ ] No hardcoded user data or expense rows remain in `app.py`
- [ ] All four new DB helpers are in `database/db.py` using parameterised queries
- [ ] `get_user_by_id` is imported in `app.py` and the old `get_user_by_email` import is retained (still used by login)
