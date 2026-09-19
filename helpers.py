import requests

from flask import redirect, render_template, session
from functools import wraps


def apology(message, code=400):
    return render_template("apology.html", top=code, bottom=message), code


def login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")

        return function(*args, **kwargs)

    return decorated_function


def lookup(symbol):
    symbol = symbol.strip().upper()

    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + symbol,
            timeout=10,
        )

        response.raise_for_status()
        data = response.json()

        result = data["chart"]["result"]

        if not result:
            return None

        meta = result[0]["meta"]
        price = meta.get("regularMarketPrice")

        if price is None:
            return None

        return {
            "name": meta.get("shortName", symbol),
            "price": float(price),
            "symbol": meta.get("symbol", symbol),
        }

    except (requests.RequestException, KeyError, TypeError, IndexError):
        return None


def usd(value):
    return f"${value:,.2f}"
