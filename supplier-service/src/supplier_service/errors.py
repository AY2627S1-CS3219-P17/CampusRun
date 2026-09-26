# AI Assistance Disclosure:
# Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
# Scope: AI-generated error response format for validation and field errors.
# Author review: <to be completed by author>

"""Error responses in one shape the web client can show directly (F15.2.1, N6.2.2):

    {"detail": "What went wrong, in plain words."}
    {"detail": "...", "errors": {"startTime": "Enter a time like 09:00."}}   # 422 only
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

VALIDATION_SUMMARY = "Some details need fixing."
FORM = "form"  # key for errors that are about the request as a whole, not one field


class FieldError(Exception):
    """A validation failure found in endpoint code, reported like a schema error."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message


def _message(error: dict) -> str:
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if tuple(error.get("loc", ()))[:1] == ("path",):
        return "This id is not valid."
    if kind == "missing":
        return "This field is required."
    if kind == "string_too_short" and ctx.get("min_length") == 1:
        return "This field is required."
    if kind == "string_too_long":
        return f"Use at most {ctx.get('max_length')} characters."
    if kind == "enum":
        return "Choose one of the listed options."
    if kind in ("float_parsing", "float_type", "int_parsing", "int_type"):
        return "Enter a number."
    if kind.startswith("time"):
        return "Enter a time like 09:00."
    if kind.startswith("url"):
        return "Enter a full link starting with https://."
    if kind == "extra_forbidden":
        return "This field is not recognised."
    if kind in ("bool_parsing", "bool_type"):
        return "Use true or false."
    if kind == "json_invalid":
        return "The request body is not valid JSON."
    return error.get("msg", "This value is not valid.").removeprefix("Value error, ")


def _field(loc: tuple) -> str:
    parts = [p for p in loc if p not in ("body", "query", "path", "header")]
    return str(parts[0]) if parts and isinstance(parts[0], str) else FORM


def _response(errors: dict[str, str]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": VALIDATION_SUMMARY, "errors": errors})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_: Request, exc: RequestValidationError):
        errors: dict[str, str] = {}
        for error in exc.errors():
            errors.setdefault(_field(tuple(error.get("loc", ()))), _message(error))
        return _response(errors)

    @app.exception_handler(FieldError)
    async def on_field_error(_: Request, exc: FieldError):
        return _response({exc.field: exc.message})
