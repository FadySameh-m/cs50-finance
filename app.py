from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

app = Flask(__name__)

app.jinja_env.filters["usd"] = usd

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user_id = session["user_id"]

    rows = db.execute(
        """
        SELECT symbol, SUM(shares) AS total_shares
        FROM transactions
        WHERE user_id = ?
        GROUP BY symbol
        HAVING total_shares > 0
        """,
        user_id,
    )

    user = db.execute(
        "SELECT cash FROM users WHERE id = ?",
        user_id,
    )

    cash = user[0]["cash"]
    portfolio_value = 0

    portfolio = []

    for row in rows:
        stock = lookup(row["symbol"])

        if stock is None:
            continue

        total = row["total_shares"] * stock["price"]
        portfolio_value += total

        portfolio.append(
            {
                "symbol": row["symbol"],
                "name": stock["name"],
                "shares": row["total_shares"],
                "price": stock["price"],
                "total": total,
            }
        )

    grand_total = cash + portfolio_value

    return render_template(
        "index.html",
        portfolio=portfolio,
        cash=cash,
        grand_total=grand_total,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")

    symbol = request.form.get("symbol", "").strip().upper()
    shares = request.form.get("shares", "").strip()

    if not symbol:
        return apology("must provide symbol", 400)

    stock = lookup(symbol)

    if stock is None:
        return apology("invalid symbol", 400)

    try:
        shares = int(shares)
    except ValueError:
        return apology("shares must be a positive integer", 400)

    if shares <= 0:
        return apology("shares must be a positive integer", 400)

    total_cost = shares * stock["price"]
    user_id = session["user_id"]

    user = db.execute(
        "SELECT cash FROM users WHERE id = ?",
        user_id,
    )

    cash = user[0]["cash"]

    if total_cost > cash:
        return apology("insufficient funds", 400)

    db.execute(
        "UPDATE users SET cash = cash - ? WHERE id = ?",
        total_cost,
        user_id,
    )

    db.execute(
        """
        INSERT INTO transactions (user_id, symbol, shares, price)
        VALUES (?, ?, ?, ?)
        """,
        user_id,
        stock["symbol"],
        shares,
        stock["price"],
    )

    flash("Purchase successful")
    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user_id = session["user_id"]

    if request.method == "GET":
        symbols = db.execute(
            """
            SELECT symbol
            FROM transactions
            WHERE user_id = ?
            GROUP BY symbol
            HAVING SUM(shares) > 0
            ORDER BY symbol
            """,
            user_id,
        )

        return render_template(
            "sell.html",
            symbols=[row["symbol"] for row in symbols],
        )

    symbol = request.form.get("symbol", "").strip().upper()
    shares = request.form.get("shares", "").strip()

    if not symbol:
        return apology("must select a symbol", 400)

    try:
        shares = int(shares)
    except ValueError:
        return apology("shares must be a positive integer", 400)

    if shares <= 0:
        return apology("shares must be a positive integer", 400)

    owned = db.execute(
        """
        SELECT COALESCE(SUM(shares), 0) AS total
        FROM transactions
        WHERE user_id = ? AND symbol = ?
        """,
        user_id,
        symbol,
    )

    if shares > owned[0]["total"]:
        return apology("too many shares", 400)

    stock = lookup(symbol)

    if stock is None:
        return apology("invalid symbol", 400)

    total_value = shares * stock["price"]

    db.execute(
        "UPDATE users SET cash = cash + ? WHERE id = ?",
        total_value,
        user_id,
    )

    db.execute(
        """
        INSERT INTO transactions (user_id, symbol, shares, price)
        VALUES (?, ?, ?, ?)
        """,
        user_id,
        symbol,
        -shares,
        stock["price"],
    )

    flash("Sale successful")
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")

    symbol = request.form.get("symbol", "").strip().upper()

    if not symbol:
        return apology("must provide symbol", 400)

    stock = lookup(symbol)

    if stock is None:
        return apology("invalid symbol", 400)

    return render_template("quoted.html", stock=stock)


@app.route("/history")
@login_required
def history():
    transactions = db.execute(
        """
        SELECT symbol, shares, price, timestamp
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        """,
        session["user_id"],
    )

    return render_template(
        "history.html",
        transactions=transactions,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "")

    if not username:
        return apology("must provide username", 400)

    if not password:
        return apology("must provide password", 400)

    if not confirmation:
        return apology("must confirm password", 400)

    if password != confirmation:
        return apology("passwords do not match", 400)

    password_hash = generate_password_hash(password)

    try:
        user_id = db.execute(
            """
            INSERT INTO users (username, hash)
            VALUES (?, ?)
            """,
            username,
            password_hash,
        )
    except Exception:
        return apology("username already taken", 400)

    session.clear()
    session["user_id"] = user_id

    flash("Registration successful")
    return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()

    if request.method == "GET":
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username:
        return apology("must provide username", 403)

    if not password:
        return apology("must provide password", 403)

    rows = db.execute(
        "SELECT * FROM users WHERE username = ?",
        username,
    )

    if len(rows) != 1:
        return apology("invalid username and/or password", 403)

    if not check_password_hash(rows[0]["hash"], password):
        return apology("invalid username and/or password", 403)

    session["user_id"] = rows[0]["id"]

    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
