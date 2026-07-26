"""Transient Git workspace helpers for LeRAI."""

from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
import uuid

from filelock import FileLock, Timeout


class GitWorkspaceError(RuntimeError):
    """Base class for transient Git workspace errors."""


class GitConfigError(GitWorkspaceError):
    """Raised when required Git workspace configuration is missing."""


class GitLockError(GitWorkspaceError):
    """Raised when the workspace lock cannot be acquired."""


class GitCloneError(GitWorkspaceError):
    """Raised when cloning the repository fails."""


class GitCommitError(GitWorkspaceError):
    """Raised when creating a commit fails."""


class GitPushError(GitWorkspaceError):
    """Raised when pushing a commit fails."""


class TransientGitWorkspace:
    """A stateless Git client that always rebuilds its local workspace."""

    def __init__(
        self,
        repo_url: str | None = None,
        local_path: str | Path | None = None,
        ssh_key_path: str | None = None,
        lock_path: str | Path = "/tmp/leroy_git.lock",
    ) -> None:
        self.repo_url = repo_url or os.environ.get("LEROY_GIT_REPO_URL")
        self.local_path = Path(local_path or os.environ.get("LEROY_GIT_LOCAL_PATH", "/tmp/leroy_config_test"))
        self.ssh_key_path = ssh_key_path or os.environ.get("LEROY_GIT_SSH_KEY_PATH")
        self.lock_path = Path(lock_path)

        missing = [
            name
            for name, value in (
                ("LEROY_GIT_REPO_URL", self.repo_url),
                ("LEROY_GIT_SSH_KEY_PATH", self.ssh_key_path),
            )
            if not value
        ]
        if missing:
            raise GitConfigError("Missing required environment variable(s): " + ", ".join(missing))

    def clone(self) -> Path:
        with self._acquire_lock():
            if self.local_path.exists():
                try:
                    shutil.rmtree(self.local_path)
                except OSError as exc:
                    raise GitCloneError(f"Failed to remove existing workspace: {self.local_path}") from exc

            self._run_git(
                ["clone", self.repo_url, str(self.local_path)],
                cwd=None,
                error_type=GitCloneError,
            )
            return self.local_path

    def commit(self, user_name: str, user_email: str, ticket_id: str, commit_message: str) -> None:
        with self._acquire_lock():
            if not self.local_path.exists():
                raise GitCommitError(f"Workspace does not exist: {self.local_path}")

            self._run_git(["add", "-A"], cwd=self.local_path, error_type=GitCommitError)

            author = f"{user_name} <{user_email}>"
            message = f"[{ticket_id}] {commit_message} (Assisted by LeRAI bot)"
            self._run_git(
                ["commit", f"--author={author}", "-m", message],
                cwd=self.local_path,
                error_type=GitCommitError,
            )

    def push(self) -> None:
        with self._acquire_lock():
            if not self.local_path.exists():
                raise GitPushError(f"Workspace does not exist: {self.local_path}")

            self._run_git(["push"], cwd=self.local_path, error_type=GitPushError)

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["GIT_SSH_COMMAND"] = f"ssh -i {self.ssh_key_path} -o StrictHostKeyChecking=no"
        return env

    @contextmanager
    def _acquire_lock(self):
        lock = FileLock(str(self.lock_path))
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise GitLockError(f"Could not acquire Git lock: {self.lock_path}") from exc

        try:
            yield
        finally:
            lock.release()

    def _run_git(self, args: list[str], cwd: str | Path | None, error_type: type[GitWorkspaceError]) -> None:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            env=self._build_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            message = f"git {' '.join(args)} failed"
            if stderr:
                message = f"{message}: {stderr}"
            elif stdout:
                message = f"{message}: {stdout}"
            raise error_type(message)


__all__ = [
    "GitCloneError",
    "GitCommitError",
    "GitConfigError",
    "GitLockError",
    "GitPushError",
    "GitWorkspaceError",
    "TransientGitWorkspace",
]

def run_test():
    try:
        print("🚀 Initializing transient workspace (acquiring lock & cloning)...")
        workspace = TransientGitWorkspace()
        workspace.clone()
        
        print("✅ Clone successful. Writing a test file...")
        # Write a dummy file to simulate an override change
        test_file_path = os.path.join(os.environ["LEROY_GIT_LOCAL_PATH"], "test_override.txt")
        with open(test_file_path, "w") as f:
            f.write(f"Test run: {uuid.uuid4()}\n")
            
        print("📝 Committing changes...")
        workspace.commit(
            user_name="Test User",
            user_email="test.user@akamai.com",
            ticket_id="LEROYOPS-999",
            commit_message="Automated integration test for Git module"
        )
        
        print("☁️ Pushing to remote...")
        workspace.push()
        print("🎉 Success! Check your remote repository.")

    except GitLockError:
        print("❌ Failed to acquire lock. Is another process running?")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    # run_test()
    pass