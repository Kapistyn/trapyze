# Helping with traPYze

Thanks for wanting to help. traPYze is for people who use Python tools without
being programmers, so the main rule for everything is: **plain words, no
surprises, nothing lost.**

## Ways to help

- **Report a problem**: open an issue with what you did, what you expected and
  what happened. The run's log (Outputs, the run, Show the log) helps a lot;
  check it for anything private first.
- **Suggest an idea**: open an issue and describe the situation it helps with.
- **Share a tool**: make it traPYze-ready, put it in a public GitHub repository
  and add the topic `trapyze-tool`. The coming traPYze store will find it.
- **Change the code**: see below.

## Working on the code

```
git clone https://github.com/kapistyn/trapyze
cd trapyze
uv run --with pytest python -m pytest -q     # all tests, no internet needed
uv run trapyze open                          # try your change
```

- Python 3.11 or newer; the core needs only the standard library and
  `cryptography`. The window (`[desktop]`) is optional.
- The web page is plain HTML, CSS and JavaScript in `src/trapyze/web/static`,
  without a build step.
- Add a test for what you change. Tests must not need the internet.
- Write messages for people: say what happened and what to do, without
  jargon. "The vault is locked. Unlock it with your PIN." rather than
  "VaultLockedError".
- Never let a secret reach a file, a log or a command line.

## Making a release

1. Put the new version in `pyproject.toml` and `src/trapyze/__init__.py`.
2. Add a section for it at the top of `CHANGELOG.md`.
3. Commit, then tag and push: `git tag v0.13.0 && git push origin v0.13.0`.

The release workflow tests, builds the wheel and traPYze-Setup.exe, and
publishes them with the install scripts. Every traPYze out there then offers
the update by itself.
