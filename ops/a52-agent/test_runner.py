#!/usr/bin/env python3
"""Local, network-free tests for runner parsing and Git publish behavior."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner


def git(args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class CodexJsonlTests(unittest.TestCase):
    def check_lines(self, lines):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "codex.log"
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return runner.has_sandbox_boundary_violation(log_path)

    def test_exit_182_is_sandbox_boundary_violation(self):
        event = {"type": "item.completed", "item": {
            "type": "command_execution", "status": "failed", "exit_code": 182,
        }}
        self.assertTrue(self.check_lines([json.dumps(event)]))

    def test_normal_command_failure_is_not_sandbox_violation(self):
        event = {"type": "item.completed", "item": {
            "type": "command_execution", "status": "failed", "exit_code": 1,
        }}
        self.assertFalse(self.check_lines([json.dumps(event)]))

    def test_invalid_json_is_ignored(self):
        self.assertFalse(self.check_lines(["not valid JSON", "{"]))

    def test_other_event_types_do_not_trigger_violation(self):
        events = [
            {"type": "turn.completed", "item": {
                "type": "command_execution", "status": "failed", "exit_code": 182,
            }},
            {"type": "item.completed", "item": {
                "type": "agent_message", "status": "failed", "exit_code": 182,
            }},
        ]
        self.assertFalse(self.check_lines([json.dumps(event) for event in events]))


class TaskFormatTests(unittest.TestCase):
    def test_parse_and_branch(self):
        task = runner.parse_task(Path("sample-task.md"), b"---\nid: sample-task\ntitle: Sample\n---\nDo it.\n")
        self.assertEqual(task.task_id, "sample-task")
        self.assertEqual(runner.branch_for(task.task_id), "agent/task-sample-task")

    def test_rejects_filename_mismatch_and_unsafe_ids(self):
        content = b"---\nid: sample-task\ntitle: Sample\n---\nDo it.\n"
        with self.assertRaises(runner.RunnerError):
            runner.parse_task(Path("different.md"), content)
        with self.assertRaises(runner.RunnerError):
            runner.branch_for("../main")


class LocalGitFlowTests(unittest.TestCase):
    def make_fixture(self, codex_exit, codex_body="echo partial > partial.txt"):
        temp = tempfile.TemporaryDirectory()
        base = Path(temp.name)
        bare = base / "remote.git"
        repo = base / "checkout"
        state = base / "state"
        git(["init", "--bare", "--initial-branch=main", str(bare)])
        git(["clone", str(bare), str(repo)])
        git(["config", "user.name", "Test"], cwd=repo)
        git(["config", "user.email", "test@example.invalid"], cwd=repo)
        (repo / "AGENTS.md").write_text("Follow repository rules.\n", encoding="utf-8")
        task_dir = repo / "agent" / "tasks"
        task_dir.mkdir(parents=True)
        task_content = b"---\nid: sample-task\ntitle: Sample\n---\nMake a change.\n"
        (task_dir / "sample-task.md").write_bytes(task_content)
        git(["add", "AGENTS.md", "agent/tasks/sample-task.md"], cwd=repo)
        git(["commit", "-m", "fixture"], cwd=repo)
        git(["push", "origin", "main"], cwd=repo)
        fake = base / "fake-codex"
        fake.write_text(
            "#!/bin/sh\n"
            "has_json=0\n"
            "for arg in \"$@\"; do [ \"$arg\" = --json ] && has_json=1; done\n"
            "[ \"$has_json\" = 1 ] || exit 90\n"
            f"{codex_body}\nexit {codex_exit}\n", encoding="utf-8")
        fake.chmod(0o755)
        os.environ["RVE_CODEX"] = str(fake)
        return temp, bare, repo, state, task_content

    def test_success_is_pushed_to_task_branch(self):
        temp, bare, repo, state, content = self.make_fixture(0)
        self.addCleanup(temp.cleanup)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        agent = runner.AgentRunner(repo, state, 60, 30)
        agent.handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Status: **SUCCESS**", result)
        self.assertTrue(git(["--git-dir", str(bare), "cat-file", "-e", "refs/heads/agent/task-sample-task:partial.txt"]) == "")
        self.assertFalse(git(["branch", "--list", "agent/task-sample-task"], cwd=repo))

    def test_codex_failure_pushes_only_failure_result(self):
        temp, bare, repo, state, content = self.make_fixture(7)
        self.addCleanup(temp.cleanup)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        runner.AgentRunner(repo, state, 60, 30).handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Status: **FAILED**", result)
        with self.assertRaises(subprocess.CalledProcessError):
            git(["--git-dir", str(bare), "cat-file", "-e", "refs/heads/agent/task-sample-task:partial.txt"])

    def test_codex_does_not_inherit_github_token(self):
        temp, bare, repo, state, content = self.make_fixture(
            0, 'test -z "$GITHUB_TOKEN" || exit 19\necho success > output.txt')
        self.addCleanup(temp.cleanup)
        os.environ["GITHUB_TOKEN"] = "do-not-inherit"
        self.addCleanup(os.environ.pop, "GITHUB_TOKEN", None)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        runner.AgentRunner(repo, state, 60, 30).handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Status: **SUCCESS**", result)

    def test_codex_created_commit_is_discarded(self):
        script = ('echo secret-free > partial.txt\n'
                  'git -c user.name=Codex -c user.email=codex@example.invalid add partial.txt\n'
                  'git -c user.name=Codex -c user.email=codex@example.invalid commit -m unexpected\n')
        temp, bare, repo, state, content = self.make_fixture(0, script)
        self.addCleanup(temp.cleanup)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        runner.AgentRunner(repo, state, 60, 30).handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Status: **FAILED**", result)
        with self.assertRaises(subprocess.CalledProcessError):
            git(["--git-dir", str(bare), "cat-file", "-e", "refs/heads/agent/task-sample-task:partial.txt"])

    def test_sandbox_violation_event_publishes_failure(self):
        event = json.dumps({"type": "item.completed", "item": {
            "type": "command_execution", "status": "failed", "exit_code": 182,
        }})
        temp, bare, repo, state, content = self.make_fixture(0, f"echo '{event}'")
        self.addCleanup(temp.cleanup)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        runner.AgentRunner(repo, state, 60, 30).handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Codex sandbox boundary violation detected; see A52 logs", result)
        self.assertIn("Status: **FAILED**", result)

    def test_normal_command_failure_event_can_recover(self):
        event = json.dumps({"type": "item.completed", "item": {
            "type": "command_execution", "status": "failed", "exit_code": 1,
        }})
        temp, bare, repo, state, content = self.make_fixture(0, f"echo '{event}'\necho recovered > recovered.txt")
        self.addCleanup(temp.cleanup)
        task = runner.parse_task(Path("agent/tasks/sample-task.md"), content)
        runner.AgentRunner(repo, state, 60, 30).handle(task)
        result = git(["--git-dir", str(bare), "show", "refs/heads/agent/task-sample-task:agent/results/sample-task.md"])
        self.assertIn("Status: **SUCCESS**", result)


if __name__ == "__main__":
    unittest.main()
