import datetime
import sqlite3

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_category_totals,
    get_expense_stats,
    get_expenses_by_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
)

app = Flask(__name__)
app.secret_key = "dev-secret-change-me"


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html")

        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")
            return render_template("register.html")

        flash("Account created! Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("All fields are required.", "error")
            return render_template("login.html")

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        abort(404)

    # ---- USER INFO SECTION ------------------------------------------------
    raw_name = user["name"]
    words = raw_name.split()
    initials = "".join(w[0].upper() for w in words)[:2]
    member_since = datetime.datetime.strptime(user["created_at"][:10], "%Y-%m-%d").strftime("%d %B %Y")
    user_info = {
        "name": raw_name,
        "email": user["email"],
        "member_since": member_since,
        "initials": initials,
    }
    # ---- END USER INFO SECTION --------------------------------------------

    # ---- CATEGORY DATA (shared by stats + breakdown) ----------------------
    category_rows = get_category_totals(user_id)
    # ---- END CATEGORY DATA ------------------------------------------------

    # ---- TRANSACTIONS SECTION ---------------------------------------------
    expense_rows = get_expenses_by_user(user_id)
    transactions = [
        {
            "date": datetime.datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": row["description"] or "",
            "category": row["category"],
            "amount": f"₹{row['amount']:,.2f}",
        }
        for row in expense_rows
    ]
    # ---- END TRANSACTIONS SECTION -----------------------------------------

    # ---- STATS SECTION ----------------------------------------------------
    expense_stats = get_expense_stats(user_id)
    top_category = category_rows[0]["category"] if category_rows else "—"
    stats = {
        "total_spent": f"₹{expense_stats['total']:,.2f}",
        "transaction_count": expense_stats["count"],
        "top_category": top_category,
    }
    # ---- END STATS SECTION ------------------------------------------------

    # ---- CATEGORIES SECTION -----------------------------------------------
    grand_total = sum(row["total"] for row in category_rows)
    categories = [
        {
            "name": row["category"],
            "amount": f"₹{row['total']:,.2f}",
            "pct": round((row["total"] / grand_total) * 100) if grand_total else 0,
        }
        for row in category_rows
    ]
    # ---- END CATEGORIES SECTION -------------------------------------------

    return render_template(
        "profile.html",
        user_info=user_info,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
