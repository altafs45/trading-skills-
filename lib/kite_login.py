#!/usr/bin/env python3
"""Kite Connect daily login. Run this YOURSELF in a terminal once a day (tokens reset at 06:00 IST).
Do not run it through a chat, and never paste keys, secrets or tokens into a chat.

  python3 lib/kite_login.py            # opens the Kite login page; paste the redirect URL (or request_token) back here
  python3 lib/kite_login.py --status   # says whether today's token is saved (never shows it)

Needs your Kite Connect app's api_key and api_secret, from env (KITE_API_KEY, KITE_API_SECRET) or
~/.config/nse-day-trader/kite.json ({"api_key": "...", "api_secret": "..."}). The access token is saved to
that file (permissions 600 where the OS allows). The pack only reads quotes, instruments and candles with it.
"""

import argparse, getpass, os, re, sys, webbrowser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse_common as C  # noqa: E402


def request_token_from(text):
    """Accepts the bare request_token or the whole redirect URL."""
    m = re.search(r"request_token=([A-Za-z0-9]+)", text)
    tok = m.group(1) if m else text.strip()
    if not re.match(r"^[A-Za-z0-9]{8,64}$", tok):
        raise ValueError("that does not look like a request_token")
    return tok


def save(doc):
    d = os.path.dirname(C.CRED_FILE)
    os.makedirs(d, exist_ok=True)
    C.write_json(C.CRED_FILE, doc)
    try:
        os.chmod(C.CRED_FILE, 0o600)
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    f = C.read_json(C.CRED_FILE, {}) or {}
    if a.status:
        ok = C.kite_creds() is not None
        print("Kite: %s. Credentials file: %s" % ("logged in for today" if ok else "NOT logged in (or token expired at 06:00 IST)", C.CRED_FILE))
        return
    key = os.environ.get("KITE_API_KEY") or f.get("api_key")
    secret = os.environ.get("KITE_API_SECRET") or f.get("api_secret")
    if not key or not secret:
        sys.exit("Set KITE_API_KEY and KITE_API_SECRET (env), or api_key and api_secret in %s." % C.CRED_FILE)
    url = C.KITE_LOGIN % key
    opened = webbrowser.open(url)
    print("Log in to Kite in the browser%s." % ("" if opened else " (no browser opened: open your Kite Connect app's login URL yourself)"))
    print("After login Kite redirects to your app's redirect URL with ?request_token=... in it.")
    try:
        tok = request_token_from(getpass.getpass("Paste the redirect URL or request_token (hidden): "))
        access = C.kite_session(key, secret, tok)
    except (ValueError, C.SourceError) as e:
        sys.exit("Login failed: %s" % e)
    f.update(api_key=key, access_token=access, token_at=C.iso(C.now_ist()))  # the secret is stored only if it was already in the file
    save(f)
    print("Logged in. Token saved to %s (valid until 06:00 IST tomorrow)." % C.CRED_FILE)


if __name__ == "__main__":
    main()
