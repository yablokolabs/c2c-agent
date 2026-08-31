"""Interactive setup.

Writes `.env`. Nothing else in C2C needs configuring — the benchmark, the policy
and the cases are all in the repository, and the evaluation runs with no
configuration at all.

What this is really for is the two things that cannot live in a repository: a
model credential, and a Telegram bot. It checks both rather than taking them on
trust, because "chat not found" at demo time is a five-second fix that costs
twenty minutes to diagnose.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ENV = Path(".env")


def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    suffix = f" [{'*' * 8 if secret and default else default}]" if default else ""
    try:
        got = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)
    return got or default


def existing() -> dict[str, str]:
    if not ENV.exists():
        return {}
    out = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def write(values: dict[str, str]) -> None:
    lines = ["# C2C configuration. Gitignored — never commit this file.", ""]
    for k, v in values.items():
        if v:
            lines.append(f"{k}={v}")
    ENV.write_text("\n".join(lines) + "\n")
    ENV.chmod(0o600)


def check_model(values: dict[str, str]) -> bool:
    key = values.get("ANTHROPIC_API_KEY")
    if key:
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages",
                           headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                           json={"model": "claude-haiku-4-5-20251001", "max_tokens": 4,
                                 "messages": [{"role": "user", "content": "hi"}]}, timeout=30)
            if r.status_code == 200:
                print("  ok    API key works")
                return True
            print(f"  FAIL  API key rejected: {r.json().get('error', {}).get('message', r.status_code)}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  could not reach the API: {exc!r}")
            return False

    import shutil
    if shutil.which("claude"):
        print("  ok    no API key, but the Claude CLI is installed — C2C will use it")
        print("        (run `claude` once interactively if you have never logged in)")
        return True
    print("  FAIL  no ANTHROPIC_API_KEY and no `claude` CLI on PATH.")
    print("        C2C needs one of them. See REPRODUCTION_GUIDE.md.")
    return False


def check_telegram(values: dict[str, str]) -> bool:
    token, chat = values.get("C2C_TELEGRAM_TOKEN"), values.get("C2C_TELEGRAM_CHAT_ID")
    if not token:
        print("  skip  no bot token — everything works over HTTP without Telegram")
        return True
    try:
        me = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  could not reach Telegram: {exc!r}")
        return False
    if not me.get("ok"):
        print(f"  FAIL  bad bot token: {me.get('description')}")
        return False
    print(f"  ok    bot @{me['result'].get('username')}")

    if not chat:
        print("  ..    finding your chat id — send your bot any message now, then press Enter")
        input()
        ups = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=25).json()
        ids = {str(u.get("message", {}).get("chat", {}).get("id"))
               for u in ups.get("result", []) if u.get("message")}
        ids.discard("None")
        if not ids:
            print("  FAIL  no messages seen. Open Telegram, find your bot, press Start.")
            return False
        chat = sorted(ids)[0]
        values["C2C_TELEGRAM_CHAT_ID"] = chat
        print(f"  ok    chat id {chat}")

    r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat, "text": "C2C is configured. You should see this."},
                   timeout=20).json()
    if r.get("ok"):
        print("  ok    test message delivered — check your phone")
        return True
    # The failure that cost the most time here: a bot cannot message someone who
    # has never opened the conversation.
    print(f"  FAIL  {r.get('description')}")
    if "chat not found" in str(r.get("description", "")).lower():
        print("        A bot cannot message someone who has not messaged it first.")
        print("        Open Telegram, find your bot, press Start, then re-run this.")
    return False


def main() -> int:
    print("\nC2C setup\n" + "─" * 60)
    print("Writes .env, which is gitignored. Press Enter to keep a existing value.\n")
    values = existing()

    print("Model access — an API key, or the Claude CLI if you have it logged in.")
    values["ANTHROPIC_API_KEY"] = ask("ANTHROPIC_API_KEY (blank to use the CLI)",
                                      values.get("ANTHROPIC_API_KEY", ""), secret=True)
    print("\nTelegram — optional. Everything works over HTTP without it.")
    print("Create a bot with @BotFather, then paste the token it gives you.")
    values["C2C_TELEGRAM_TOKEN"] = ask("C2C_TELEGRAM_TOKEN (blank to skip)",
                                       values.get("C2C_TELEGRAM_TOKEN", ""), secret=True)
    values["C2C_TELEGRAM_CHAT_ID"] = ask("C2C_TELEGRAM_CHAT_ID (blank to detect)",
                                         values.get("C2C_TELEGRAM_CHAT_ID", ""))

    print("\nChecking\n" + "─" * 60)
    ok_model = check_model(values)
    ok_tg = check_telegram(values)
    write(values)
    print(f"\nWrote {ENV} (permissions 600)")

    if ok_model and ok_tg:
        print("\nReady.\n"
              "  make test        the suite, no model calls\n"
              "  make up          control plane and the durable workflow\n"
              "  make bot         C2C on Telegram\n"
              "  make reproduce   the headline result\n")
        return 0
    print("\nSomething above needs fixing. Re-run `make configure` when it is sorted.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
