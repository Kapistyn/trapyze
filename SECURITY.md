# Security

traPYze keeps keys and passwords for your tools, so security problems matter.

## Reporting

Please **don't** open a public issue for a security problem. Use GitHub's
private reporting instead: the repository's **Security** tab, then
**Report a vulnerability** (https://github.com/kapistyn/trapyze/security/advisories/new).
You'll get an answer within a week.

## How traPYze protects your secrets

- The vault is encrypted with AES-GCM using a key derived from your PIN; on
  Windows the file is also protected by your Windows account (DPAPI).
- Secrets reach a tool only as environment variables, only for tools you
  allowed, and are masked in progress, logs and history. They are never put on
  a command line.
- Sharing a tool and Ask AI check for vault values and key-like text first.
- The window only listens on 127.0.0.1, and every address carries a fresh key.
- Updates come only from this repository's releases, over HTTPS, and are compared
  with the release's published checksums before they are installed.
- A tool that was imported or written by an AI shows what it can do and waits for
  your OK before its first run.

## Running other people's tools

A tool is a Python program and can do anything you can do. Only run tools from
people you trust, and look at the health check before the first run.
