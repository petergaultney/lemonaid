"""The review-comments language server, `lemonaid lsp`, and how lemons reach it.

`server` needs the `lsp` extra (pygls and lsprotocol); `registry` and `cli` use only the
standard library, so lemonaid's other commands import them without the extra.
"""
