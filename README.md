# Freddy Bot

Python watcher for detecting chat messages addressed to `Freddy_922` on `chat-avenue.com/singles`.

## Analysis

The chat page is JavaScript-driven, so plain HTTP scraping is not the right first tool. The practical approach is browser automation attached to a real browser session:

- You open Brave manually, so login and human checks stay manual.
- Brave runs with Chrome DevTools remote debugging enabled.
- The Python app connects to that running browser with Playwright.
- The app polls configured DOM selectors for chat message text.
- If a new message starts with `Freddy_922`, it stores the prompt, appends it to history, and can ask you for a manual terminal reply.

The main missing information is the exact CodyChat DOM selector used after login. This version includes common candidate selectors and an `inspect` command to print selector matches from the live page. After seeing real samples, tune `config.json`.

## Files

- `src/freddy_bot/chat_watcher.py` - main watcher app
- `config.example.json` - starter config
- `scripts/start_brave_debug.ps1` - helper to start Brave in incognito mode with remote debugging
- `captures/prompts.jsonl` - created automatically when prompts are captured
- `captures/history.jsonl` - created automatically with caught tags and reply records
- `captures/latest_prompt.json` - overwritten with the latest caught tag

## Setup

Install Python dependencies:

```powershell
python -m pip install -e .
```

Install Playwright's browser support if needed:

```powershell
python -m playwright install chromium
```

The repo includes a ready `config.json`. If you need to reset it from the template:

```powershell
Copy-Item config.example.json config.json
```

## Start Brave

You can use the helper:

```powershell
.\scripts\start_brave_debug.ps1
```

Or start Brave manually with equivalent flags:

```powershell
brave.exe --remote-debugging-port=9222 --user-data-dir="$env:TEMP\freddy_bot_brave" --incognito https://www.chat-avenue.com/singles
```

Then log in or enter the chat manually.

## One-Terminal Run

This starts Brave through the PowerShell helper, logs to both console and `captures/runtime.log`, watches for tagged messages, and generates Codex replies from `persona_freddy.md`:

```powershell
python run_freddy_bot.py --config config.json run
```

If Brave takes longer to start:

```powershell
python run_freddy_bot.py --config config.json run --wait-seconds 60
```

After Brave opens, log in or enter the room manually. Keep the Python terminal open. When a matching tag appears, it prints the captured message and asks:

```text
Press Enter to send, type replacement, or type /skip:
```

To use the old manual-only mode:

```powershell
python run_freddy_bot.py --config config.json run --manual-replies
```

## Codex Replies

Edit `persona_freddy.md` to shape the reply style.

To generate a Codex reply, review it in the terminal, then press Enter to send:

```powershell
python run_freddy_bot.py --config config.json run
```

When Codex suggests a reply, the terminal asks:

```text
Press Enter to send, type replacement, or type /skip:
```

To send Codex replies without confirmation:

```powershell
python run_freddy_bot.py --config config.json run --codex-replies --auto-send-ai
```

By default, `config.json` has:

```json
"confirm_codex_replies": false
```

Set it to `true` if you want terminal confirmation back. CLI overrides are also available:

```powershell
python run_freddy_bot.py --config config.json run --confirm-replies
python run_freddy_bot.py --config config.json run --auto-send-ai
```

The terminal uses colors for key events: incoming tagged messages, your saved messages, Codex suggestions, ignored echoes, and sent replies.

Codex is called with the configured command:

```json
["codex", "exec", "--ephemeral", "--sandbox", "read-only"]
```

It receives the persona file, the previous conversation with the detected partner, and the current incoming message. The final Codex output is used as the candidate chat reply body.

If new chat messages arrive while Codex is generating, the app logs them and regenerates the suggestion once with that newer context before asking you to confirm.

The app writes conversation context to `captures/chat_context.jsonl`, but only for conversations involving you:

- their messages that start with `Freddy_922`
- your rendered messages that look like `Freddy_922 20/06 18:02 TheirName ...`

When a conversation partner can be detected, the app appends those lines to `captures/users/<username>.md` and includes that person’s recent notes when they tag you.

Sending searches all page frames for the configured input selectors. If no visible input is found, it falls back to typing into the currently focused browser element, so keep the chat input focused if selector tuning is still incomplete.

If Codex returns a meta-reply like asking for more context, the app rejects it and asks for a replacement instead of sending it. Failed sends are logged to `captures/history.jsonl` as `reply_send_failed` and the watcher keeps running.

For debugging, the exact prompt sent to Codex is written to `captures/last_codex_prompt.txt`, and the console logs how many characters were loaded from `persona_freddy.md`.

Outgoing replies are addressed deterministically by the script. Codex generates only the reply body, then the app prefixes the detected partner username before sending, for example `BellaVam sounds like a lot, but nice when it is finally coming together.`

If replies are generated but not sent, run:

```powershell
python run_freddy_bot.py --config config.json inspect
```

The inspect output lists input candidates from the page and all frames, including ids, names, classes, placeholders, and visibility. Use that to tune `input_selectors`.

## Inspect Selectors

Run this after the chat room is visible:

```powershell
python run_freddy_bot.py --config config.json inspect
```

Look for a selector that prints individual chat messages rather than a large block of the whole chat. Put the best selector first in `config.json`.

## Watch Messages

```powershell
python run_freddy_bot.py --config config.json watch
```

The watcher prints captured prompts and appends JSON records to `captures/prompts.jsonl`.

## Watch And Reply Manually

Use this mode to catch tags, type a reply in the terminal, and send it back to the page:

```powershell
python run_freddy_bot.py --config config.json watch --manual-replies
```

When a matching tag appears, the terminal prompts:

```text
Reply to send, or blank to skip:
```

The reply is sent through the configured chat input selector, then recorded in `captures/history.jsonl`.

If sending fails, run `inspect` and tune `input_selectors` in `config.json`.

The watcher ignores likely echoes of your own replies. By default it skips rows that look like `Freddy_922 20/06 17:32 ...` and also ignores recently sent reply text if the chat page re-renders it as a new message.

## File-Based Reply Test

For a later local AI integration, the watcher can also read reply text from `captures/next_reply.txt`:

```powershell
python run_freddy_bot.py --config config.json watch --send-replies
```

When a prompt is active and `captures/next_reply.txt` contains text, that text is sent and the file is cleared.

## Send One Test Message

```powershell
python run_freddy_bot.py --config config.json send "test message"
```

## Current Scope

This version does not call a local AI model yet. It captures messages that start with the configured nickname, lets you provide a manual reply, sends it, and records both prompt and reply history.
