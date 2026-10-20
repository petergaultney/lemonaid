"""Log Textual failures before its fatal-error handler exits the application."""

import typing as ty

from textual.app import App
from textual.worker import WorkerFailed

from ... import errors

_Result = ty.TypeVar("_Result")


class CrashLoggedApp(App[_Result]):
    def _handle_exception(self, error: Exception) -> None:
        errors.record(
            error.error if isinstance(error, WorkerFailed) else error, type(self).__name__
        )
        super()._handle_exception(error)
