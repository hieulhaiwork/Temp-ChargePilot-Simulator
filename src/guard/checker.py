"""Chạy các luật FR12 trên một lệnh / một lô lệnh → GuardVerdict.

Ngữ nghĩa (đã cài, có test ở tests/test_guard/test_checker.py):
  - Chạy MỌI luật, không dừng ở vi phạm đầu tiên → màn S7 hiện đủ lý do chặn.
  - Vi phạm bất kỳ ⇒ passed=False ⇒ dispatcher chặn lệnh.
  - `rules` truyền vào được → test checker bằng luật giả, độc lập với 7 luật thật.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from src.guard.rules import RULES, GuardContext, Rule
from src.models.control import Command, GuardRule, GuardVerdict


def check(cmd: Command, ctx: GuardContext, rules: Mapping[GuardRule, Rule] = RULES) -> GuardVerdict:
    violations = [v for rule in rules.values() if (v := rule(cmd, ctx)) is not None]
    return GuardVerdict(
        command_id=cmd.command_id,
        passed=not violations,
        violations=violations,
        checked_at=ctx.now,
    )


def check_batch(
    cmds: Sequence[Command], ctx: GuardContext, rules: Mapping[GuardRule, Rule] = RULES
) -> list[GuardVerdict]:
    """Kiểm một lô; mọi lệnh thấy cả lô qua ctx.batch (luật xung đột cần điều này)."""
    batch_ctx = replace(ctx, batch=tuple(cmds))
    return [check(cmd, batch_ctx, rules) for cmd in cmds]
