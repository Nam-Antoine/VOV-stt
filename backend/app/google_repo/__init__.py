"""Google Sheet + Docs repository of the transcripts (GOOGLE_REPO_PLAN.md).

Generated from the database, never read back. Off unless ``GOOGLE_REPO_ENABLED=true``.
Nothing in this package deletes anything in Google Drive.

Kept import-light on purpose: ``python -m app.google_repo.auth --init`` must run on a
laptop with only ``google-auth-oauthlib`` installed.
"""
