"""Validated, bounded pagination shared by manager read endpoints."""
import re

from flask import request

from common import ApiError


def page_args(default_size=25):
    def number(name, default, maximum):
        raw = request.args.get(name, str(default))
        if not re.fullmatch(r"[0-9]{1,9}", raw):
            raise ApiError(f"{name} must be a positive whole number")
        value = int(raw)
        if value < 1 or value > maximum:
            raise ApiError(f"{name} must be between 1 and {maximum}")
        return value
    return number("page", 1, 999999999), number("per_page", default_size, 100)


def pagination(total, page, size):
    pages = max(1, (total + size - 1) // size)
    return {"page": min(page, pages), "per_page": size,
            "total": total, "total_pages": pages}
