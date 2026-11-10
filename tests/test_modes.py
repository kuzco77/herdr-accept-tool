"""Permission-vs-question classification and the permissions-only mode."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import test_antigravity as ag  # noqa: E402
import test_parse as cc  # noqa: E402
from herdr_accept_tool import (  # noqa: E402
    DEFAULT_PREFER,
    KIND_PERMISSION,
    KIND_QUESTION,
    MODE_ALL,
    MODE_PERMISSIONS,
    Answerer,
    build_parser,
    parse_prompt,
    prompt_kind,
)

PREFER = re.compile(DEFAULT_PREFER)

CLAUDE_PLAN_APPROVAL = """\
Would you like to proceed?

❯ 1. Yes, and auto-accept edits
  2. Yes, and manually approve edits
  3. No, keep planning
"""

# AskUserQuestion with Yes/No labels still shows the free-text option.
CLAUDE_YES_NO_QUESTION = """\
Should I delete the old migrations?

❯ 1. Yes
  2. No
  3. Type something
"""

UNKNOWN_SHAPE = """\
Pick one

❯ 1. Alpha
  2. Beta
"""


def kind(screen: str) -> str:
    prompt = parse_prompt(screen)
    assert prompt is not None, "fixture must parse as a prompt"
    return prompt_kind(prompt)


class PromptKindTest(unittest.TestCase):
    def test_claude_permission_prompts(self) -> None:
        self.assertEqual(kind(cc.PERMISSION), KIND_PERMISSION)
        self.assertEqual(kind(CLAUDE_PLAN_APPROVAL), KIND_PERMISSION)
        self.assertEqual(kind(cc.VIETNAMESE_YES_NO), KIND_PERMISSION)

    def test_claude_questions(self) -> None:
        self.assertEqual(kind(cc.QUESTION), KIND_QUESTION)
        self.assertEqual(kind(cc.RECOMMENDED_SECOND), KIND_QUESTION)
        self.assertEqual(kind(cc.YES_SECOND), KIND_QUESTION)
        self.assertEqual(kind(cc.SUBMIT), KIND_QUESTION)
        self.assertEqual(kind(cc.MULTI_UNTICKED), KIND_QUESTION)
        self.assertEqual(kind(cc.MULTI_TICKED), KIND_QUESTION)
        self.assertEqual(kind(CLAUDE_YES_NO_QUESTION), KIND_QUESTION)

    def test_antigravity_permission_prompts(self) -> None:
        self.assertEqual(kind(ag.TRUST), KIND_PERMISSION)
        self.assertEqual(kind(ag.BASH_PERMISSION), KIND_PERMISSION)
        self.assertEqual(kind(ag.CREATE_PERMISSION), KIND_PERMISSION)
        self.assertEqual(kind(ag.ARTIFACT_PENDING), KIND_PERMISSION)

    def test_antigravity_questions(self) -> None:
        self.assertEqual(kind(ag.QUESTION), KIND_QUESTION)
        self.assertEqual(kind(ag.MULTI_UNTICKED), KIND_QUESTION)
        self.assertEqual(kind(ag.MULTI_TICKED), KIND_QUESTION)

    def test_unrecognised_dialog_is_a_question(self) -> None:
        self.assertEqual(kind(UNKNOWN_SHAPE), KIND_QUESTION)


class AnswererModeTest(unittest.TestCase):
    def answerer(self, mode: str) -> Answerer:
        return Answerer(pane_id="w1:p1", prefer=PREFER, cooldown=10.0, quiet=True, mode=mode)

    def test_all_mode_answers_questions(self) -> None:
        with mock.patch("herdr_accept_tool.send_keys") as send:
            self.assertTrue(self.answerer(MODE_ALL).answer(cc.QUESTION))
        send.assert_called_once_with("w1:p1", ["Enter"])

    def test_permissions_mode_answers_permission(self) -> None:
        with mock.patch("herdr_accept_tool.send_keys") as send:
            self.assertTrue(self.answerer(MODE_PERMISSIONS).answer(cc.PERMISSION))
        send.assert_called_once_with("w1:p1", ["Enter"])

    def test_permissions_mode_leaves_question(self) -> None:
        answerer = self.answerer(MODE_PERMISSIONS)
        with mock.patch("herdr_accept_tool.send_keys") as send:
            self.assertFalse(answerer.answer(cc.QUESTION))
            self.assertFalse(answerer.answer(ag.QUESTION))
            self.assertFalse(answerer.answer(cc.SUBMIT))
        send.assert_not_called()

    def test_skipped_question_is_logged_once_per_cooldown(self) -> None:
        answerer = Answerer(pane_id="w1:p1", prefer=PREFER, cooldown=10.0, mode=MODE_PERMISSIONS)
        with mock.patch("herdr_accept_tool.log") as logger:
            answerer.answer(cc.QUESTION)
            answerer.answer(cc.QUESTION)
        self.assertEqual(logger.call_count, 1)

    def test_cli_mode_flag(self) -> None:
        self.assertEqual(build_parser().parse_args(["w1:p1"]).mode, MODE_ALL)
        self.assertEqual(
            build_parser().parse_args(["w1:p1", "--mode", "permissions"]).mode, MODE_PERMISSIONS
        )


if __name__ == "__main__":
    unittest.main()
