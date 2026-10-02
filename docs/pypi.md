# 🍋🥤 lemonaid

Monitor progress of and switch between lemons (go on... say 'LLMs' three times fast)
running in the terminal.

<img width="900" alt="The lemonaid inbox as a left sidebar, a card per session, beside a Claude Code session" src="https://raw.githubusercontent.com/petergaultney/lemonaid/main/docs/images/inbox-left.png" />

Hooks in Claude Code, Codex CLI, OpenCode and OpenClaw write a notification
whenever a session stops or needs input. The `lma` inbox shows those sessions,
what each is doing, and jumps you to its tmux pane or WezTerm tab. Archived
sessions stay searchable and resumable.

## Install

```bash
uv tool install lemonaid-inbox
```

The package is `lemonaid-inbox`, because `lemonaid` on PyPI is an unrelated
project. The commands are still `lemonaid` and `lma`.

An install made before the rename is a uv tool named `lemonaid`. Remove it
once with `uv tool uninstall lemonaid` before installing `lemonaid-inbox`.

## Documentation

The full README, with setup for each harness and terminal, is on
[GitHub](https://github.com/petergaultney/lemonaid#readme).

- [Docs](https://github.com/petergaultney/lemonaid/tree/main/docs)
- [Changelog](https://github.com/petergaultney/lemonaid/blob/main/CHANGES.md)
- [Issues](https://github.com/petergaultney/lemonaid/issues)
