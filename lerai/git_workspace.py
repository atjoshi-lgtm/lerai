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
        branch: str | None = None,
        local_path: str | Path | None = None,
        ssh_key_path: str | None = None,
        lock_path: str | Path = "/tmp/leroy_git.lock",
    ) -> None:
        self.repo_url = repo_url or os.environ.get("LEROY_GIT_REPO_URL")
        self.branch = branch or os.environ.get("LEROY_GIT_BRANCH")
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

            clone_args = ["clone"]
            if self.branch:
                clone_args.extend(["--branch", self.branch])
            clone_args.extend([self.repo_url, str(self.local_path)])

            self._run_git(
                clone_args,
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

            push_args = ["push"]
            if self.branch:
                push_args.extend(["origin", self.branch])
            self._run_git(push_args, cwd=self.local_path, error_type=GitPushError)

    def get_head_diff(self) -> str:
        with self._acquire_lock():
            if not self.local_path.exists():
                raise GitWorkspaceError(f"Workspace does not exist: {self.local_path}")

            completed = subprocess.run(
                ["git", "show", "--pretty=format:", "HEAD"],
                cwd=str(self.local_path),
                env=self._build_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                message = "git show --pretty=format: HEAD failed"
                if stderr:
                    message = f"{message}: {stderr}"
                elif stdout:
                    message = f"{message}: {stdout}"
                raise GitWorkspaceError(message)

            return (completed.stdout or "").strip()

    def get_diff_against_branch(self, target_branch: str = "origin/master") -> str:
        with self._acquire_lock():
            if not self.local_path.exists():
                raise GitWorkspaceError(f"Workspace does not exist: {self.local_path}")

            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(self.local_path),
                env=self._build_env(),
                capture_output=True,
                text=True,
                check=False,
            )

            completed = subprocess.run(
                ["git", "diff", target_branch, "HEAD", "--", "override.toml"],
                cwd=str(self.local_path),
                env=self._build_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                message = f"git diff {target_branch} HEAD -- override.toml failed"
                if stderr:
                    message = f"{message}: {stderr}"
                elif stdout:
                    message = f"{message}: {stdout}"
                raise GitWorkspaceError(message)

            return (completed.stdout or "").strip()

    def get_override_file_timestamps(self, target_branch: str = "origin/master") -> dict[str, str]:
        with self._acquire_lock():
            if not self.local_path.exists():
                raise GitWorkspaceError(f"Workspace does not exist: {self.local_path}")

            def _run_timestamp_command(ref: str) -> str:
                completed = subprocess.run(
                    ["git", "log", "-1", "--format=%cI", ref, "--", "override.toml"],
                    cwd=str(self.local_path),
                    env=self._build_env(),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    stderr = (completed.stderr or "").strip()
                    stdout = (completed.stdout or "").strip()
                    message = f"git log -1 --format=%cI {ref} -- override.toml failed"
                    if stderr:
                        message = f"{message}: {stderr}"
                    elif stdout:
                        message = f"{message}: {stdout}"
                    raise GitWorkspaceError(message)
                return (completed.stdout or "").strip() or "Unknown"

            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(self.local_path),
                env=self._build_env(),
                capture_output=True,
                text=True,
                check=False,
            )

            return {
                "offline_last_modified": _run_timestamp_command("HEAD"),
                "production_last_modified": _run_timestamp_command(target_branch),
            }

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
        local_path = workspace.clone()
        
        print("✅ Clone successful. Copying override.toml...")
        # Copy override.toml from /lerai/override.toml
        source_override = Path("/home/atjoshi/lerai/override.toml")
        target_override = local_path / "override.toml"
        
        if source_override.exists():
            shutil.copy2(source_override, target_override)
            print(f"✅ Copied override.toml")
        else:
            print(f"❌ Source file not found: {source_override}")
            return
            
        print("📝 Committing changes...")
        workspace.commit(
            user_name="Test User",
            user_email="test.user@akamai.com",
            ticket_id="LEROYOPS-999",
            commit_message="Reset override.toml"
        )
        
        print("☁️ Pushing to remote...")
        workspace.push()
        
        print("🧹 Cleaning up local repo...")
        shutil.rmtree(local_path)
        print("🎉 Success! Override.toml reset in remote repository.")

    except GitLockError:
        print("❌ Failed to acquire lock. Is another process running?")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    run_test()
    # pass
