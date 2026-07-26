import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from filelock import Timeout

from lerai.git_workspace import GitCloneError, GitCommitError, GitLockError, GitPushError, TransientGitWorkspace


class TransientGitWorkspaceTests(unittest.TestCase):
    def _workspace(self, base_dir: str) -> TransientGitWorkspace:
        local_path = Path(base_dir) / "workspace"
        key_path = Path(base_dir) / "id_rsa"
        key_path.write_text("dummy key", encoding="utf-8")
        return TransientGitWorkspace(
            repo_url="git@example.com:repo.git",
            local_path=local_path,
            ssh_key_path=str(key_path),
            lock_path=Path(base_dir) / "git.lock",
        )

    def test_clone_removes_existing_workspace_and_sets_ssh_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._workspace(temp_dir)
            workspace.local_path.mkdir(parents=True)
            (workspace.local_path / "stale.txt").write_text("stale", encoding="utf-8")

            with patch("lerai.git_workspace.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")

                result = workspace.clone()

            self.assertEqual(result, workspace.local_path)
            self.assertFalse(workspace.local_path.exists())
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.kwargs["cwd"], None)
            self.assertEqual(run_mock.call_args.kwargs["env"]["GIT_SSH_COMMAND"], f"ssh -i {workspace.ssh_key_path} -o StrictHostKeyChecking=no")
            self.assertEqual(run_mock.call_args.args[0], ["git", "clone", workspace.repo_url, str(workspace.local_path)])

    def test_clone_raises_lock_error_when_lock_is_busy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._workspace(temp_dir)

            lock_mock = MagicMock()
            lock_mock.acquire.side_effect = Timeout("busy")

            with patch("lerai.git_workspace.FileLock", return_value=lock_mock):
                with self.assertRaises(GitLockError):
                    workspace.clone()

    def test_commit_formats_author_and_message(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._workspace(temp_dir)
            workspace.local_path.mkdir(parents=True)

            with patch("lerai.git_workspace.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(args=["git", "add", "-A"], returncode=0, stdout="", stderr=""),
                    subprocess.CompletedProcess(args=["git", "commit"], returncode=0, stdout="", stderr=""),
                ]

                workspace.commit("Alice Example", "alice@example.com", "TICKET-123", "Fix flaky test")

            self.assertEqual(run_mock.call_count, 2)
            commit_call = run_mock.call_args_list[1]
            self.assertEqual(commit_call.kwargs["cwd"], str(workspace.local_path))
            self.assertEqual(commit_call.kwargs["env"]["GIT_SSH_COMMAND"], f"ssh -i {workspace.ssh_key_path} -o StrictHostKeyChecking=no")
            self.assertEqual(
                commit_call.args[0],
                [
                    "git",
                    "commit",
                    "--author=Alice Example <alice@example.com>",
                    "-m",
                    "[TICKET-123] Fix flaky test (Assisted by LeRAI bot)",
                ],
            )

    def test_commit_includes_stderr_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._workspace(temp_dir)
            workspace.local_path.mkdir(parents=True)

            with patch("lerai.git_workspace.subprocess.run") as run_mock:
                run_mock.side_effect = [
                    subprocess.CompletedProcess(args=["git", "add", "-A"], returncode=0, stdout="", stderr=""),
                    subprocess.CompletedProcess(args=["git", "commit"], returncode=1, stdout="", stderr="fatal: no changes added to commit"),
                ]

                with self.assertRaises(GitCommitError) as context:
                    workspace.commit("Alice Example", "alice@example.com", "TICKET-123", "Fix flaky test")

            self.assertIn("fatal: no changes added to commit", str(context.exception))

    def test_push_includes_stderr_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = self._workspace(temp_dir)
            workspace.local_path.mkdir(parents=True)

            with patch("lerai.git_workspace.subprocess.run") as run_mock:
                run_mock.return_value = subprocess.CompletedProcess(args=["git", "push"], returncode=1, stdout="", stderr="fatal: push rejected")

                with self.assertRaises(GitPushError) as context:
                    workspace.push()

            self.assertIn("fatal: push rejected", str(context.exception))


if __name__ == "__main__":
    unittest.main()