# AI Notes

## Project Intent

Build an application/script that interacts with `chat-avenue.com/singles` and a local AI model.

The chat site appears to use the CodyChat plugin. The first milestone is to detect when the user is tagged in chat and capture the message text.

## Current Trigger Rule

- User nickname: `Freddy_922`
- Trigger condition: a chat message starts with `Freddy_922`
- Initial behavior: grab the message text and save it to a variable
- Later behavior: pass the grabbed text as a prompt to a local AI model

## Preferred Runtime / Browser

- Preferred language: Python
- Browser preference: Brave
- Browser mode: incognito/private mode
- Preference: open the browser manually if possible

## Initial Technical Direction

Use Python browser automation rather than raw HTTP scraping because the chat is likely dynamic and JavaScript-driven.

Likely options:

- Playwright for Python: preferred if we can connect to a running Brave/Chromium instance over the Chrome DevTools Protocol.
- Selenium: possible alternative, especially if Brave-specific setup is easier in this environment.

Recommended approach for manual browser opening:

1. Start Brave manually with remote debugging enabled and a temporary user data directory.
2. Open `https://www.chat-avenue.com/singles` in a private/incognito window.
3. Use Python Playwright to connect to that running browser.
4. Inspect the live DOM and identify reliable selectors for CodyChat message rows.
5. Watch new chat messages, extract text, and check whether each message starts with `Freddy_922`.

Example Brave launch concept:

```powershell
brave.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\freddy_bot_brave" --incognito
```

Exact Brave executable path may vary by system.

## Open Questions

- Confirm the exact DOM structure/selectors used by the chat after login.
- Confirm whether messages include username and body in one text node or separate elements.
- Confirm whether login/session handling needs to be automated or can remain fully manual.
- Choose the local AI model interface later, such as Ollama, LM Studio, llama.cpp server, or another local API.

## Safety / Behavior Notes

- Start with read-only observation of visible chat messages.
- Avoid sending automated replies until message capture is stable and the user explicitly asks for reply automation.
- Keep implementation scoped to messages addressed to `Freddy_922`.

## Current Implementation

Created a first read-only Python watcher:

- Main app: `src/freddy_bot/chat_watcher.py`
- Config template: `config.example.json`
- Brave helper: `scripts/start_brave_debug.ps1`
- Docs: `README.md`

The app connects to a manually opened Brave/Chromium browser through Chrome DevTools Protocol at `http://127.0.0.1:9222`.

Available commands:

```powershell
python run_freddy_bot.py --config config.json inspect
python run_freddy_bot.py --config config.json watch
```

The `inspect` command is used to identify which selector matches actual chat messages after login. The `watch` command captures new messages that start with `Freddy_922`, stores the current text as `last_prompt`, and writes captures to `captures/prompts.jsonl`.

Added manual reply support:

```powershell
python run_freddy_bot.py --config config.json watch --manual-replies
```

When a tagged message is caught, the terminal asks for a reply. A non-empty reply is sent to the chat page through configured input selectors and written to `captures/history.jsonl`. A blank reply records the prompt as skipped.

The watcher now ignores likely echoes of its own replies:

- `ignore_own_timestamped_messages`: skips rows like `Freddy_922 20/06 17:32 ...`
- `ignore_recent_sent_replies`: keeps a short list of sent reply texts and ignores matching re-rendered rows

Added file-based reply support for future local AI integration:

```powershell
python run_freddy_bot.py --config config.json watch --send-replies
```

This watches `captures/next_reply.txt` for reply text when a prompt is active.

Added one-terminal run support:

```powershell
python run_freddy_bot.py --config config.json run
```

This starts Brave through `scripts/start_brave_debug.ps1`, waits for the CDP endpoint, logs to both console and `captures/runtime.log`, watches for tagged messages, and generates Codex replies from `persona_freddy.md`. Use `--manual-replies` for the old terminal-only reply mode.

Added Codex reply support:

- Persona file: `persona_freddy.md`
- Config keys: `personality_file`, `codex_command`, `codex_timeout_seconds`, `ai_history_context_lines`
- Command with confirmation:

```powershell
python run_freddy_bot.py --config config.json run
```

- Command with automatic sending:

```powershell
python run_freddy_bot.py --config config.json run --codex-replies --auto-send-ai
```

Codex is invoked with `codex exec --ephemeral --sandbox read-only`. The app sends Codex the Freddy persona, detected partner, previous conversation with that partner, and the current incoming tagged message.

After Codex generation, the app now scans the chat again. If new messages arrived while Codex was thinking, it logs them and regenerates the suggestion once with that newer context. Reply sending now searches all page frames for input selectors and falls back to typing into the currently focused browser element if no visible input selector is found.

Codex stdout is decoded as UTF-8 to avoid mojibake such as `â€™`. Meta-replies asking for context are rejected. Send failures are now non-fatal and recorded as `reply_send_failed`.

Debugging Codex behavior: every Codex request writes the exact prompt to `captures/last_codex_prompt.txt`, and runtime logs show how many characters were loaded from `persona_freddy.md`.

Outgoing tags are deterministic: Codex should generate only the reply body. The Python script prefixes the detected partner username before sending, so messages to BellaVam start with `BellaVam ...` regardless of model output.

Avoid topic-specific scripted fallbacks. The global approach is:

1. Tell Codex who it is roleplaying: `Freddy_922`.
2. Tell Codex who it is talking to: detected partner username.
3. Give Codex the previous conversation transcript with that partner.
4. Give Codex the current message from that partner.

Validation should stay generic: reject meta-replies, very short non-answers, and generic greetings/acknowledgements. If Codex still fails, ask for manual replacement instead of using hardcoded topic answers.

Reply confirmation is controlled by config key `confirm_codex_replies`. Default is `false`, so Codex replies are sent without asking for terminal confirmation. CLI overrides: `--confirm-replies` and `--auto-send-ai`.

Rejected Codex replies follow the same confirmation mode: with auto-send, rejected replies are skipped; with confirmation enabled, terminal asks for replacement or blank skip.

Terminal output uses ANSI colors: incoming prompts are cyan, saved Freddy messages are magenta, Codex suggestions are yellow, ignored echoes are dim, and sent replies are green.

Conversation tracking rule: a partner becomes tracked only after they tag `Freddy_922` or already have a memory file. First outbound messages from Freddy_922 to a new untracked person are ignored for memory/prompt context, so starting a new chat manually does not contaminate another active conversation. `last_codex_prompt.txt` is cleared at startup.

The watcher now refreshes the Chat Avenue page handle before scans and sends because the original Playwright page can become stale/closed after site navigation. `inspect` now reports input candidates across page frames for selector tuning.

Added filtered room and per-user memory:

- `captures/chat_context.jsonl`: only conversations involving `Freddy_922`
- `captures/users/<username>.md`: per-user observed chat notes for people talking with `Freddy_922`
- Config keys: `chat_context_jsonl`, `user_memory_dir`, `recent_chat_context_lines`

Capture rule: keep their messages that start with `Freddy_922`, and keep Freddy_922's rendered messages when they look like `Freddy_922 20/06 18:02 TheirName ...`. Ignore unrelated room chatter and people replying to each other.

Important: Freddy_922's rendered rows must never be captured as incoming prompts, even though they start with `Freddy_922`. They are context only.

Codex prompts now include personality, recent prompt/reply history, recent filtered conversation context, and per-user notes when available.

Important context rule: unrelated room chatter is saved to `captures/chat_context.jsonl`, but it should not force Codex regeneration for an active prompt. Regeneration after Codex thinking should only use new activity from the same detected username or new activity that starts with `Freddy_922`.
