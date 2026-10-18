from __future__ import annotations

from fastapi import HTTPException, status


def bad_request(msg: str, code: str = "bad_request") -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": code, "error": msg})


def not_found(msg: str = "not found") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "error": msg})


def conflict(msg: str, code: str = "conflict", **extra: object) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code, "error": msg, **extra})
