"""The grove window's page, as one HTML string with its scripts inlined."""

import re
from importlib import resources

_INCLUDE = re.compile(r'<script src="([\w.-]+\.js)"></script>')


def html() -> str:
    static = resources.files(__package__).joinpath("static")
    page = static.joinpath("page.html").read_text()

    # pywebview loads the page from a string, which has nowhere to fetch a relative script from.
    return _INCLUDE.sub(lambda m: f"<script>\n{static.joinpath(m[1]).read_text()}</script>", page)
