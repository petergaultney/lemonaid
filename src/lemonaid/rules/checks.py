"""What every pattern must pass before `rules check --promote` writes the snapshot hooks read."""

import re
import typing as ty
from collections import abc
from re import _constants, _parser  # the stdlib has no public parse tree

from . import rule_text, search
from .patterns import Pattern

EXAMPLE_SECONDS = 0.5  # one pattern on one example
_REPEATS = (_constants.MAX_REPEAT, _constants.MIN_REPEAT, _constants.POSSESSIVE_REPEAT)


def _children(op: ty.Any, av: ty.Any) -> abc.Iterator[ty.Any]:
    """The subpatterns of one parsed node."""
    if op in _REPEATS:
        yield av[2]
    elif op == _constants.SUBPATTERN:
        yield av[3]
    elif op == _constants.BRANCH:
        yield from av[1]
    elif op in (_constants.ASSERT, _constants.ASSERT_NOT):
        yield av[1]
    elif op == _constants.ATOMIC_GROUP:
        yield av
    elif op == _constants.GROUPREF_EXISTS:
        yield from (branch for branch in av[1:] if branch is not None)


def _nested(items: abc.Iterable[ty.Any], repeated: bool) -> bool:
    """Whether a variable repeat sits inside a repeat that can run more than once.

    *repeated*: an enclosing repeat can. Python's `re` has no timeout, and this shape,
    such as `(\\w+\\s?)+`, is how a regex backtracks for hours on a long message.
    """
    for op, av in items:
        if op in _REPEATS:
            low, high, _ = av
            if repeated and high != low:
                return True

            if _nested(av[2], repeated or high > 1):
                return True

            continue

        if any(_nested(child, repeated) for child in _children(op, av)):
            return True

    return False


def regex_problem(regex: str) -> str:
    """Why *regex* can't go live, or "" when it can.

    A first filter: the hook and `rules replay` also stop any search at a time limit.
    """
    try:
        re.compile(regex)
    except re.error as error:
        return f"regex does not compile: {error}"

    if _nested(_parser.parse(regex), False):
        return "regex nests one quantifier inside another, which can hang on a long message"

    return ""


def _rule_problems(pattern: Pattern) -> abc.Iterator[str]:
    try:
        text = pattern.rule_file.read_text()
    except OSError as error:
        yield f"{pattern.id}: cannot read rule_file {pattern.rule_file}: {error.strerror}"
        return

    found = len(rule_text.starts(text, pattern.rule_starts))
    if found != 1:
        yield (
            f"{pattern.id}: {found} paragraphs or list items in {pattern.rule_file} start with "
            f"rule_starts {pattern.rule_starts!r}; it must be exactly 1"
        )


def _example_problem(pattern: Pattern, example: str, kind: str) -> str:
    try:
        found = search.search(pattern.regex, example, EXAMPLE_SECONDS)
    except search.TooSlow:
        return f"{pattern.id}: took over {EXAMPLE_SECONDS} s on its {kind} example {example!r}"

    if bool(found) != (kind == "match"):
        return f"{pattern.id}: {'does not match' if found is None else 'matches'} its {kind} example {example!r}"

    return ""


def _regex_problems(pattern: Pattern) -> abc.Iterator[str]:
    if problem := regex_problem(pattern.regex):
        yield f"{pattern.id}: {problem}"
        return

    for kind, examples in (("match", pattern.match), ("no_match", pattern.no_match)):
        yield from filter(None, (_example_problem(pattern, each, kind) for each in examples))


def problems(patterns: abc.Sequence[Pattern]) -> abc.Iterator[str]:
    """Every reason not to promote *patterns*; none means they may go live."""
    for pattern in patterns:
        if not pattern.match or not pattern.no_match:
            yield f"{pattern.id}: needs at least one match and one no_match example"
        if pattern.mode == "tell" and not pattern.say:
            yield f"{pattern.id}: a tell pattern needs say, the line telling a lemon what to do"
        yield from _regex_problems(pattern)
        yield from _rule_problems(pattern)
