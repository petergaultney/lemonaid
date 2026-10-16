"""Keep delivery and competing launches outside the brief stop/start interval."""

import functools
import inspect

from . import state


def exclusive(argument):
    def decorate(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        def call(*args, **kwargs):
            channel = signature.bind(*args, **kwargs).arguments[argument]
            with state.barrier(channel, exclusive=True):
                if state.blocked(channel):
                    raise ValueError("A restart is in progress")
                return function(*args, **kwargs)

        return call

    return decorate


def deliver(channel, output):
    def call(message):
        with state.admission(channel) as allowed:
            if not allowed:
                raise ValueError("Restart holds delivery; changes remain pending")
            output(message)

    return call
