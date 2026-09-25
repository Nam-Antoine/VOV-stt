"""OAuth for the Google repository: scope ``drive.file`` only, no service account.

On the owner's laptop, once (needs only ``pip install google-auth-oauthlib``)::

    python -m app.google_repo.auth --init --credentials ./credentials.json --out ./token.json

opens a browser, asks the owning Google account to approve, and writes ``token.json``.
Copy it to ``data/google/token.json`` on the VPS (``/data/google/token.json`` inside the
containers). Without a browser on the same machine, add ``--manual``: it prints the
link and asks for the address the browser lands on afterwards.

On the VPS::

    python -m app.google_repo.auth --check     # owning account + token expiry, no secrets

At run time :func:`get_credentials` loads the token and refreshes it. A revoked or
expired grant raises :class:`GoogleAuthError` once, with the fix in plain words; it is
never retried in a loop. No token, secret or code is ever logged or printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

REINIT = ("re-run `python -m app.google_repo.auth --init` on your laptop and copy the new "
          "token.json to data/google/ on the VPS")


class GoogleAuthError(RuntimeError):
    """The token is missing, unreadable, revoked or expired. Needs the owner, not a retry."""


def write_atomic(path: Path, body: str) -> None:
    """Write ``body`` to ``path`` via a temp file + rename, mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def get_credentials(token_path: Path | None = None):
    """Loaded, refreshed credentials for the owning account.

    Writes the token back (atomically) when Google rotated the refresh token.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if token_path is None:
        from ..config import settings

        token_path = settings.google_token_path
    if not token_path.exists():
        raise GoogleAuthError(f"no Google token at {token_path}: {REINIT}")
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except (ValueError, json.JSONDecodeError) as exc:
        raise GoogleAuthError(
            f"Google token at {token_path} is unreadable ({type(exc).__name__}): {REINIT}"
        ) from None
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise GoogleAuthError(f"Google token has no refresh token: {REINIT}")
    before = creds.refresh_token
    try:
        creds.refresh(Request())
    except RefreshError as exc:
        reason = "revoked or expired" if "invalid_grant" in str(exc) else "refused"
        raise GoogleAuthError(f"Google sign-in was {reason}: {REINIT}") from None
    if creds.refresh_token and creds.refresh_token != before:
        write_atomic(token_path, creds.to_json())
    return creds


def init(credentials: Path, out: Path, *, manual: bool = False) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not credentials.exists():
        sys.exit(f"no OAuth client file at {credentials} (the Desktop-app JSON)")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials), SCOPES)
    if manual:
        # Loopback redirect over plain http is what Google's desktop clients use.
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
        flow.redirect_uri = "http://localhost:8765/"
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        print("Open this link, sign in with the account that will own the repository, "
              "and approve:\n\n" + url + "\n")
        print("The browser then lands on a http://localhost:8765/?… page that does not "
              "load. That is expected.")
        answer = input("Paste that whole address here: ").strip()
        flow.fetch_token(authorization_response=answer)
        creds = flow.credentials
    else:
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    write_atomic(out, creds.to_json())
    print(f"\nSaved {out.resolve()}")
    print("Next: copy it to the VPS as data/google/token.json "
          "(/data/google/token.json in the containers), for example\n"
          f"  scp {out} <vps>:/ternary/vov-stt/data/google/token.json")


def check() -> int:
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
    except GoogleAuthError as exc:
        print(f"Google auth: {exc}")
        return 1
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    user = drive.about().get(fields="user(emailAddress,displayName)").execute()["user"]
    print(f"Google account: {user.get('emailAddress')} ({user.get('displayName')})")
    expiry = creds.expiry.isoformat() + "Z" if creds.expiry else "unknown"
    print(f"Access token valid until {expiry} (refreshed automatically)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true", help="sign in once, write token.json")
    mode.add_argument("--check", action="store_true", help="show the owning account")
    ap.add_argument("--credentials", type=Path, default=Path("credentials.json"))
    ap.add_argument("--out", type=Path, default=Path("token.json"))
    ap.add_argument("--manual", action="store_true",
                    help="with --init: no local browser; paste the redirect address")
    args = ap.parse_args(argv)
    if args.init:
        init(args.credentials, args.out, manual=args.manual)
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
