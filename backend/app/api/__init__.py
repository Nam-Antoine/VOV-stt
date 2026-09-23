"""API routers (PLAN §9). All mounted under ``/api`` by :mod:`app.main`.

T1 status: every router below declares its real routes and response models so the
OpenAPI page at ``/api/docs`` is a usable contract, but the handlers raise
``501 Not Implemented``. They get bodies in T3, after the pilot gate.
"""

from fastapi import HTTPException, status


def not_implemented(what: str) -> HTTPException:
    """Consistent 501 for the T3 stubs — never a silent empty result."""
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"{what} lands in T3 (PLAN §11); the pilot gate T2 must pass first.",
    )
