# Verification and acceptance boundaries

`desktop_ui_verified=false` after the 2026-11-02 recheck. A passing native CLI test is not
desktop UI acceptance. Keep blocked and failed evidence private and intact rather
than deleting it or turning a missing desktop receipt into a pass.

Known desktop blocker: the reported test messages were identified by their known
synthetic-input hashes and hook metadata as Home-workspace chats. Harness² rejects
a business project that contains its own state directory, so the old UNKNOWN
closure is retained. No dialogue contents were read for this diagnosis. A new
desktop test does not change that historical UNKNOWN. Do not treat a working CLI
run as desktop acceptance.

The recheck restored the official desktop app-tools connection, obtained native
folder consent, registered the concrete project and created independent desktop
chats with the correct working directory. The fresh synthetic marker did not
obtain a corresponding automatic save receipt and was not recalled in the other
chat. Those observations remain a non-pass.

In the installed desktop version `26.1027.51404`, the official `create_thread` and
`send_message_to_thread` entry points use `codex_app` tool-output delegation when
called by another chat. They are not ordinary user-input turns. The official
new-chat deep link only prefills the composer; it does not submit the prompt.
These controls therefore cannot establish ordinary-user hook acceptance. This
does not establish that every native lifecycle hook was skipped, or that an
unrelated task receipt belongs to the test chat. Do not guess session mappings,
forge caller identities, write trust state or bypass a denied GUI control to
manufacture a passing result.

## Portable offline checks

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B scripts/check_release.py
```

The 17 tests use temporary directories, synthetic facts and mock HTTP transport.
They cover raw-content canaries, confirmation/privacy rejection before persistence,
real artifact hashes, symlink containment, sensitive file names, signature and
project isolation, single submission, read-only UNKNOWN recovery, fair pending
processing, Stop continuation, complete-document integrity, and SessionEnd cleanup.
They do not import credentials or contact a live backend.

## Manual acceptance using normal desktop chats

1. Use a dedicated synthetic acceptance project and a configured local backend.
   Confirm the approved plugin is loaded in the actual desktop client; leave
   existing Obsidian configuration and hooks untouched.
2. Start a new desktop chat. Give an ordinary task with one harmless technical
   fact or synthetic marker, labelled as test data. Do not tell the user to run
   `stage`, prepare JSON, call a helper, or manually issue a memory command.
3. Let the assistant complete the task normally. Verify from the summary-only
   adapter's phase receipt that the appropriate task was automatically created,
   the assistant reviewed/staged the safe summary, and Stop submitted it.
   `submitted` alone is not a pass; independently confirm `indexed` without
   replaying a write whose result is uncertain.
4. Start a second desktop chat in the same project. Ask for the previous harmless
   test fact without supplying it again. Confirm it arrives through automatic
   task-start context, not a manual recall, file read or copied chat context.
5. Confirm different real desktop session identifiers locally, correct project
   scope, no raw dialogue/tool/transcript collection, and unchanged Obsidian and
   model configuration. Retain only a minimal sanitized receipt, not screenshots
   containing unrelated chats or raw tool logs.

If desktop control or telemetry is unavailable, record blocked/UNKNOWN. Do not
use native CLI sessions as a substitute and label them desktop acceptance. Do not
disable foreign hooks, bypass trust or collect private histories to obtain proof.

## Development validation already performed

The local development environment separately verified a real Cognee backend and
two independent native Codex CLI sessions: automatic task injection, Stop submission,
indexed readback, and automatic recall in a fresh session whose prompt did not
contain the marker. Only synthetic facts were used. Private identifiers, raw
transcripts, local paths, keys and runtime evidence are deliberately excluded
from the public repository.

A further ordinary-language CLI check passed six criteria. Session A received
only a harmless synthetic fact, with no memory/helper/staging instructions; the
assistant independently staged it once and the real Stop hook submitted it to an
indexed state. Session B asked only for the prior fact, with no marker in its
input; it recalled automatically and independently skipped an unnecessary write.
This confirms that a user need not manually invoke the helper in that tested CLI
flow. It remains separate from the pending desktop UI acceptance.

The finite privacy-policy Harness² comparison passed the frozen cases in all four
candidates. That did not show a measured general performance improvement and does
not replace the integration checks above.
