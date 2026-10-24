"""Parser and key-plan tests against screens captured from Antigravity CLI 1.2.14."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from herdr_accept_tool import (  # noqa: E402
    ANTIGRAVITY_CURSOR,
    ARTIFACT_CURSOR,
    DEFAULT_PREFER,
    choose_option,
    keys_for,
    parse_prompt,
)

PREFER = re.compile(DEFAULT_PREFER)

TRUST = """\
Accessing workspace:

/tmp/agy-probe

Do you trust the contents of this project?

Antigravity CLI requires permission to read, edit, and execute files here.

> Yes, I trust this folder
  No, exit

  ↑/↓ Navigate · enter Confirm
                                                       accept-edits · Gemini 3.8 Flash · high
"""

BASH_PERMISSION = """\
● Bash(curl -s https://example.com | head -c 50) (ctrl+o to expand)

Command
─────────────────────────────────────────────────────────────────────────────────────────────

Requesting permission for:
   curl -s https://example.com | head -c 50

Run this command?
> 1. Yes, run command
  2. Yes, and always allow in this conversation for commands that start with 'curl -s
https://example.com'
  3. Yes, and always allow for commands that start with 'curl -s https://example.com'
(Persist to settings.json)
  4. No, cancel

  ↑/↓ Navigate · tab Amend · ctrl+g edit/expand command
esc to cancel                                          accept-edits · Gemini 3.8 Flash · high
"""

CREATE_PERMISSION = """\
● Create(/tmp/agy-probe/probe2.txt) (ctrl+o to expand)

Create file
─────────────────────────────────────────────────────────────────────────────────────────────

/private/tmp/agy-probe/probe2.txt  +1
   1 +  world

Allow creation of this file?
> 1. Yes, allow creation
  2. No, deny creation

  ↑/↓ Navigate · tab Amend · f full diff · ctrl+r Review
esc to cancel                                                         Gemini 3.8 Flash · high
"""

QUESTION = """\
? Which color do you prefer?

Question
─────────────────────────────────────────────────────────────────────────────────────────────

Question 1/1: Which color do you prefer?

> 1. Red
  2. Blue
  3. Green
  4. Write-in...

  ↑/↓ Navigate · enter Select · esc Skip
esc to cancel                                          accept-edits · Gemini 3.8 Flash · high
"""

MULTI_UNTICKED = """\
Question 1/2: Which programming languages do you use?

> 1. [ ] Rust
  2. [ ] TypeScript (Recommended)
  3. [ ] Go
  4. [ ] Python
  5. Write-in...

  ↑/↓ Navigate · → Next · space Toggle · enter Submit · esc Skip
esc to cancel                                          accept-edits · Gemini 3.8 Flash · high
"""

MULTI_TICKED = """\
Question 1/2: Which programming languages do you use?

  1. [ ] Rust
> 2. [x] TypeScript (Recommended)
  3. [ ] Go
  4. [ ] Python
  5. Write-in...

  ↑/↓ Navigate · → Next · space Toggle · enter Submit · esc Skip
esc to cancel                                          accept-edits · Gemini 3.8 Flash · high
"""

ARTIFACT_PENDING = """\
─────────────────────────────────────────────────────────────────────────────────────────────
>
─────────────────────────────────────────────────────────────────────────────────────────────
Action required (1 left)
› □ new add_readme_plan.md   open  approve reject

Keyboard: ↑/↓ Navigate  y/n Approve/reject  shift+a Approve all  p Preview
  ctrl+g open in editor  esc Done

                                                               plan · Gemini 3.8 Flash · high
"""

ARTIFACT_APPROVED = """\
─────────────────────────────────────────────────────────────────────────────────────────────
>
─────────────────────────────────────────────────────────────────────────────────────────────
Artifacts
› add_readme_plan.md   open

Keyboard: ↑/↓ Navigate  p preview  enter open  ctrl+g open in editor  esc Dismiss

                                                                      Gemini 3.8 Flash · high
"""

IDLE_WITH_ANSWERS = """\
? Which programming languages do you use?
> TypeScript
? Which deployment target do you use?
> AWS

  Got it! You selected:

  • Languages: TypeScript
  • Deployment Target: AWS

─────────────────────────────────────────────────────────────────────────────────────────────
>
─────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                        accept-edits · Gemini 3.8 Flash · high
"""

IDLE_WITH_ECHO = """\
────────────────────────────────────────────────────────────
> Run this exact shell command and nothing else: curl -s https://example.com | head -c 50

● Bash(curl -s https://example.com | head -c 50) (ctrl+o to expand)


    <!doctype html><html lang=en><head><meta charset=u

─────────────────────────────────────────────────────────────────────────────────────────────
>
─────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                        accept-edits · Gemini 3.8 Flash · high
"""

IDLE_STARTUP = """\
─────────────────────────────────────────────────────────────────────────────────────────────
> Accept-edits mode: file edits auto-approved (shift+tab to cycle)
─────────────────────────────────────────────────────────────────────────────────────────────
? for shortcuts                                        accept-edits · Gemini 3.8 Flash · high
"""


class TrustPromptTest(unittest.TestCase):
    def test_trust_dialog_is_parsed_without_numbers(self) -> None:
        prompt = parse_prompt(TRUST)
        assert prompt is not None
        self.assertEqual(prompt.cursor, ANTIGRAVITY_CURSOR)
        self.assertEqual(
            prompt.question,
            "Antigravity CLI requires permission to read, edit, and execute files here.",
        )
        self.assertEqual(
            [o.label for o in prompt.options], ["Yes, I trust this folder", "No, exit"]
        )
        self.assertEqual(choose_option(prompt, PREFER), 0)
        self.assertEqual(keys_for(prompt, 0), ["Enter"])


class PermissionPromptTest(unittest.TestCase):
    def test_bash_permission_with_wrapped_labels(self) -> None:
        prompt = parse_prompt(BASH_PERMISSION)
        assert prompt is not None
        self.assertEqual(prompt.cursor, ANTIGRAVITY_CURSOR)
        self.assertEqual(prompt.question, "Run this command?")
        self.assertEqual(len(prompt.options), 4)
        self.assertEqual(prompt.options[0].label, "Yes, run command")
        self.assertEqual(prompt.options[3].label, "No, cancel")
        self.assertEqual(choose_option(prompt, PREFER), 0)
        self.assertEqual(keys_for(prompt, 0), ["Enter"])

    def test_create_permission(self) -> None:
        prompt = parse_prompt(CREATE_PERMISSION)
        assert prompt is not None
        self.assertEqual(prompt.question, "Allow creation of this file?")
        self.assertEqual(choose_option(prompt, PREFER), 0)

    def test_question_tool(self) -> None:
        prompt = parse_prompt(QUESTION)
        assert prompt is not None
        self.assertEqual(prompt.question, "Question 1/1: Which color do you prefer?")
        self.assertEqual([o.label for o in prompt.options][:3], ["Red", "Blue", "Green"])
        self.assertEqual(choose_option(prompt, PREFER), 0)


class MultiSelectTest(unittest.TestCase):
    def test_unticked_target_gets_space(self) -> None:
        prompt = parse_prompt(MULTI_UNTICKED)
        assert prompt is not None
        index = choose_option(prompt, PREFER)
        self.assertEqual(index, 1)
        self.assertIs(prompt.options[index].checkbox, False)
        self.assertEqual(keys_for(prompt, index), ["Down", "Space"])

    def test_ticked_target_submits_with_enter(self) -> None:
        prompt = parse_prompt(MULTI_TICKED)
        assert prompt is not None
        index = choose_option(prompt, PREFER)
        self.assertIs(prompt.options[index].checkbox, True)
        self.assertEqual(keys_for(prompt, index), ["Enter"])

    def test_fingerprints_differ_between_states(self) -> None:
        before = parse_prompt(MULTI_UNTICKED)
        after = parse_prompt(MULTI_TICKED)
        assert before is not None and after is not None
        self.assertNotEqual(before.fingerprint(), after.fingerprint())


class ArtifactPromptTest(unittest.TestCase):
    def test_pending_artifact_is_approved_with_y(self) -> None:
        prompt = parse_prompt(ARTIFACT_PENDING)
        assert prompt is not None
        self.assertEqual(prompt.cursor, ARTIFACT_CURSOR)
        self.assertEqual(prompt.question, "Action required (1 left)")
        self.assertEqual(keys_for(prompt, choose_option(prompt, PREFER)), ["y"])

    def test_approved_artifact_panel_is_not_a_prompt(self) -> None:
        self.assertIsNone(parse_prompt(ARTIFACT_APPROVED))


class IdleScreenTest(unittest.TestCase):
    def test_answer_summary_lines_are_not_a_prompt(self) -> None:
        self.assertIsNone(parse_prompt(IDLE_WITH_ANSWERS))

    def test_echoed_user_input_is_not_a_prompt(self) -> None:
        self.assertIsNone(parse_prompt(IDLE_WITH_ECHO))

    def test_startup_banner_is_not_a_prompt(self) -> None:
        self.assertIsNone(parse_prompt(IDLE_STARTUP))


if __name__ == "__main__":
    unittest.main()
