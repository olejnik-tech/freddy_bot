from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from freddy_bot.app.commands import run_all, send_once
from freddy_bot.app.watcher import watch
from freddy_bot.browser.inspector import inspect
from freddy_bot.config import DEFAULT_CONFIG_PATH, WatcherConfig
from freddy_bot.logging import Logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a manually opened Brave/Chromium chat page for tagged messages."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config JSON. Defaults to config.json.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Start Brave, then watch tags and generate Codex replies.",
    )
    run_parser.add_argument(
        "--wait-seconds",
        type=float,
        default=30,
        help="How long to wait for Brave remote debugging to become available.",
    )
    run_parser.add_argument(
        "--codex-replies",
        action="store_true",
        default=True,
        help="Generate replies with codex exec. This is the default for run.",
    )
    run_parser.add_argument(
        "--manual-replies",
        action="store_true",
        help="Type replies manually instead of using Codex.",
    )
    run_parser.add_argument(
        "--auto-send-ai",
        action="store_true",
        help="Send Codex replies without terminal confirmation, overriding config.",
    )
    run_parser.add_argument(
        "--confirm-replies",
        action="store_true",
        help="Require terminal confirmation before sending, overriding config.",
    )

    watch_parser = subparsers.add_parser(
        "watch", help="Watch chat messages and capture matching prompts."
    )
    watch_parser.add_argument(
        "--send-replies",
        action="store_true",
        help="Send text from reply_inbox back to the chat page.",
    )
    watch_parser.add_argument(
        "--manual-replies",
        action="store_true",
        help="Ask for a reply in the terminal whenever a prompt is captured.",
    )
    watch_parser.add_argument(
        "--codex-replies",
        action="store_true",
        help="Generate replies with codex exec whenever a prompt is captured.",
    )
    watch_parser.add_argument(
        "--auto-send-ai",
        action="store_true",
        help="Send Codex replies without terminal confirmation, overriding config.",
    )
    watch_parser.add_argument(
        "--confirm-replies",
        action="store_true",
        help="Require terminal confirmation before sending, overriding config.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Print selector matches to help tune config."
    )
    inspect_parser.add_argument("--limit", type=int, default=5)

    send_parser = subparsers.add_parser(
        "send", help="Send one message to the chat input using configured selectors."
    )
    send_parser.add_argument("text")

    return parser.parse_args()

def should_auto_send(config: WatcherConfig, args: argparse.Namespace) -> bool:
    if getattr(args, "auto_send_ai", False):
        return True
    if getattr(args, "confirm_replies", False):
        return False
    return not config.confirm_codex_replies

def main() -> None:
    args = parse_args()
    config = WatcherConfig.from_file(args.config)

    if args.command == "watch":
        logger = Logger(config.log_file)
        auto_send_ai = should_auto_send(config, args)
        asyncio.run(
            watch(
                config,
                args.send_replies,
                args.manual_replies,
                args.codex_replies,
                auto_send_ai,
                logger,
            )
        )
    elif args.command == "inspect":
        asyncio.run(inspect(config, args.limit))
    elif args.command == "send":
        asyncio.run(send_once(config, args.text))
    elif args.command == "run":
        codex_replies = args.codex_replies and not args.manual_replies
        auto_send_ai = should_auto_send(config, args)
        asyncio.run(
            run_all(
                config,
                args.wait_seconds,
                codex_replies,
                args.manual_replies,
                auto_send_ai,
            )
        )


if __name__ == "__main__":
    main()
