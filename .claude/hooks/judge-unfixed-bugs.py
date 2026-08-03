#!/usr/bin/env python3
"""Stop hook: catch bugs that were described but not fixed.

The failure this exists for: a turn surfaces a real defect, states the correct
behaviour, and then files it in a list instead of fixing it. The list grows
faster than it drains, and each entry costs more to pick up later than it would
have cost to close on the spot.

So after every turn a small, cheap model reads what was just said and answers
one question: did this turn describe a bug whose correct behaviour is already
known, and leave it unfixed? If so the turn is reopened with that as the
instruction.

Deliberately conservative. A false "fix it" wastes a turn; a false "nothing"
just restores today's behaviour. When the judge is unsure it must say NONE.
"""

import json
import re
import subprocess
import sys

JUDGE_MODEL = "claude-haiku-4-5-20251001"
TIMEOUT_SECONDS = 60

# Enough of the turn to judge intent, without paying to re-read a long session.
MAX_CHARS = 6000

PROMPT = """You are reviewing one turn of an AI coding assistant working on a \
Catan game repo.

Answer ONE question: did this turn describe a bug, defect, or wrong behaviour \
where the CORRECT behaviour is already known or obvious, and then NOT fix it?

Reply with exactly one of:

NONE
FIX: <one sentence naming the bug and what the correct behaviour is>

Answer FIX only when ALL of these hold:
- a concrete defect in this project's code is described (not a hypothetical, not \
a limitation of a third-party tool)
- the correct behaviour is stated or unambiguous
- the turn did NOT already fix it, and did NOT already dispatch an agent to fix it
- fixing it needs no decision from the user

Answer NONE if:
- the turn fixed it, committed a fix, or dispatched an agent for it
- the bug is only a possibility, a risk, or something "worth checking"
- the correct behaviour needs a design decision, a preference, or research
- the item is a missing feature, an unimplemented expansion, or a known \
deliberate limitation
- the work is blocked because another agent owns the file
- you are unsure

Be strict. NONE is the safe answer and the common one.

--- TURN ---
{turn}
--- END TURN ---"""


def last_assistant_text(transcript_path: str) -> str:
    """The final assistant message, which is where a bug would be described."""
    try:
        with open(transcript_path) as handle:
            lines = handle.readlines()
    except OSError:
        return ""

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(part for part in parts if part).strip()
        if text:
            return text[-MAX_CHARS:]
    return ""


def ask_judge(turn: str) -> str:
    """Run the small model. Any failure means stay quiet."""
    try:
        result = subprocess.run(
            ["claude", "-p", "--model", JUDGE_MODEL],
            input=PROMPT.format(turn=turn),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    # The hook fires again on the turn it itself caused. Without this the
    # session can only end when the judge happens to say NONE.
    if payload.get("stop_hook_active"):
        return 0

    turn = last_assistant_text(payload.get("transcript_path", ""))
    if len(turn) < 200:
        return 0

    verdict = ask_judge(turn)
    match = re.match(r"\s*FIX:\s*(.+)", verdict, re.IGNORECASE | re.DOTALL)
    if not match:
        return 0

    reason = " ".join(match.group(1).split())[:500]
    json.dump(
        {
            "decision": "block",
            "reason": (
                f"A bug was described but left unfixed: {reason}\n\n"
                "The correct behaviour is known, so fix it now rather than "
                "adding it to a queue. If the file belongs to a running agent, "
                "send that agent the fix instead of editing it. If you disagree "
                "that this is a bug, or it actually needs my decision, say so "
                "in one line and stop."
            ),
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
