"""Parser and key-plan tests against screens captured from Claude Code 2.1.301."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from herdr_accept_tool import DEFAULT_PREFER, choose_option, keys_for, parse_prompt  # noqa: E402

PREFER = re.compile(DEFAULT_PREFER)

PERMISSION = """\
 Permission rule Bash(curl *) requires
 confirmation for this command.

 Do you want to proceed?
 ❯ 1. Yes
   2. No

 Esc to cancel · Tab to amend
"""

QUESTION = """\
←  ☐ Color  ☐ Size  ✔ Submit  →

Which color?

❯ 1. Red (Recommended)
     Pick red.
  2. Blue
     Pick blue.
  3. Green
     Pick green.
  4. Type something.
─────────────────────────────────────────────
  5. Chat about this

Enter to select · Tab/Arrow keys to navigate
· Esc to cancel
"""

RECOMMENDED_SECOND = """\
Which database?

❯ 1. Mongo
     Document store.
  2. Postgres (Recommended)
     Relational.
  3. Type something.
──────────────────────────────────────────────
  4. Chat about this
"""

YES_SECOND = """\
Enable mode?

❯ 1. No
     Mode off.
  2. Yes
     Mode on.
  3. Type something.
"""

SUBMIT = """\
Review your answers

 ● Which color?
   → Red (Recommended)

Ready to submit your answers?

❯ 1. Submit answers
  2. Cancel
"""

MULTI_UNTICKED = """\
Which languages?

❯ 1. [ ] Rust
         Systems.
  2. [ ] TypeScript (Recommended)
         Web.
  3. [ ] Go
  4. [ ] Type something
     Next
──────────────────────────────────────────────
  5. Chat about this
"""

MULTI_TICKED = MULTI_UNTICKED.replace("[ ] TypeScript", "[✔] TypeScript").replace(
    "❯ 1.", "  1."
).replace("  2. [✔]", "❯ 2. [✔]")

IDLE_WITH_LIST = """\
⏺ Next steps:
  1. Run the tests
  2. Open the PR

─────────────────────────────────────────────
❯
─────────────────────────────────────────────
"""

VIETNAMESE = """\
Chọn cách triển khai?

❯ 1. Giữ nguyên
  2. Tách module (Khuyến nghị)
  3. Viết lại
"""

VIETNAMESE_YES_NO = """\
Bạn có muốn tiếp tục không?

❯ 1. Không
  2. Có
  3. Hỏi lại sau
"""

VIETNAMESE_DE_XUAT = """\
Chọn database?

❯ 1. Mongo
  2. Postgres (đề xuất)
"""


class ParsePromptTest(unittest.TestCase):
    def test_permission_prompt(self) -> None:
        prompt = parse_prompt(PERMISSION)
        assert prompt is not None
        self.assertEqual(prompt.question, "Do you want to proceed?")
        self.assertEqual([o.label for o in prompt.options], ["Yes", "No"])
        self.assertEqual(prompt.cursor_index, 0)

    def test_question_with_descriptions_and_rule(self) -> None:
        prompt = parse_prompt(QUESTION)
        assert prompt is not None
        self.assertEqual(prompt.question, "Which color?")
        self.assertEqual(len(prompt.options), 5)
        self.assertEqual(prompt.options[4].label, "Chat about this")

    def test_idle_screen_with_numbered_list_is_not_a_prompt(self) -> None:
        self.assertIsNone(parse_prompt(IDLE_WITH_LIST))

    def test_empty_screen(self) -> None:
        self.assertIsNone(parse_prompt(""))


class ChooseOptionTest(unittest.TestCase):
    def test_yes_first(self) -> None:
        prompt = parse_prompt(PERMISSION)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 0)
        self.assertEqual(keys_for(prompt, 0), ["Enter"])

    def test_recommended_wins_over_first(self) -> None:
        prompt = parse_prompt(RECOMMENDED_SECOND)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 1)
        self.assertEqual(keys_for(prompt, 1), ["Down", "Enter"])

    def test_yes_wins_over_first_when_no_recommended(self) -> None:
        prompt = parse_prompt(YES_SECOND)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 1)

    def test_submit_screen_picks_submit(self) -> None:
        prompt = parse_prompt(SUBMIT)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 0)

    def test_vietnamese_recommended(self) -> None:
        prompt = parse_prompt(VIETNAMESE)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 1)

    def test_vietnamese_yes_beats_first_option(self) -> None:
        prompt = parse_prompt(VIETNAMESE_YES_NO)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 1)
        self.assertEqual(keys_for(prompt, 1), ["Down", "Enter"])

    def test_vietnamese_de_xuat_is_preferred(self) -> None:
        prompt = parse_prompt(VIETNAMESE_DE_XUAT)
        assert prompt is not None
        self.assertEqual(choose_option(prompt, PREFER), 1)

    def test_cursor_below_target_moves_up(self) -> None:
        screen = YES_SECOND.replace("❯ 1.", "  1.").replace("  3.", "❯ 3.")
        prompt = parse_prompt(screen)
        assert prompt is not None
        self.assertEqual(keys_for(prompt, 1), ["Up", "Enter"])


class MultiSelectTest(unittest.TestCase):
    def test_unticked_target_is_ticked_first(self) -> None:
        prompt = parse_prompt(MULTI_UNTICKED)
        assert prompt is not None
        index = choose_option(prompt, PREFER)
        self.assertEqual(index, 1)
        self.assertIs(prompt.options[index].checkbox, False)
        self.assertEqual(keys_for(prompt, index), ["Down", "Enter"])

    def test_ticked_target_advances_with_tab(self) -> None:
        prompt = parse_prompt(MULTI_TICKED)
        assert prompt is not None
        index = choose_option(prompt, PREFER)
        self.assertIs(prompt.options[index].checkbox, True)
        self.assertEqual(keys_for(prompt, index), ["Tab"])

    def test_fingerprints_differ_between_states(self) -> None:
        before = parse_prompt(MULTI_UNTICKED)
        after = parse_prompt(MULTI_TICKED)
        assert before is not None and after is not None
        self.assertNotEqual(before.fingerprint(), after.fingerprint())


if __name__ == "__main__":
    unittest.main()
