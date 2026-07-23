import logging
import os
import subprocess
from pathlib import Path
from lerai.config import required_env

logger = logging.getLogger(__name__)

LEROY_GIT_REPO_URL = required_env("LEROY_GIT_REPO_URL")
LEROY_GIT_LOCAL_PATH = os.path.expanduser(required_env("LEROY_GIT_LOCAL_PATH"))
LEROY_GIT_SSH_KEY_PATH = os.path.expanduser(required_env("LEROY_GIT_SSH_KEY_PATH"))


def _run_git_command(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {LEROY_GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no"
    )

    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Git command failed: %s | stderr: %s",
            " ".join(args),
            (exc.stderr or "").strip(),
        )
        raise RuntimeError(f"Git command failed: {' '.join(args)}") from exc


def ensure_workspace() -> None:
    git_dir = os.path.join(LEROY_GIT_LOCAL_PATH, ".git")

    if not os.path.isdir(LEROY_GIT_LOCAL_PATH) or not os.path.isdir(git_dir):
        _run_git_command(["git", "clone", LEROY_GIT_REPO_URL, LEROY_GIT_LOCAL_PATH])
        return

    _run_git_command(["git", "fetch"], cwd=LEROY_GIT_LOCAL_PATH)
    _run_git_command(["git", "pull"], cwd=LEROY_GIT_LOCAL_PATH)


def commit_and_push(file_relative_path: str, commit_message: str) -> None:
    _run_git_command(["git", "add", file_relative_path], cwd=LEROY_GIT_LOCAL_PATH)
    _run_git_command(["git", "commit", "-m", commit_message], cwd=LEROY_GIT_LOCAL_PATH)
    _run_git_command(["git", "push"], cwd=LEROY_GIT_LOCAL_PATH)


def get_latest_commit_hash() -> str:
    result = _run_git_command(["git", "rev-parse", "HEAD"], cwd=LEROY_GIT_LOCAL_PATH)
    return result.stdout.strip()


def get_override_toml_path() -> Path:
    local_path = os.environ.get("LEROY_GIT_LOCAL_PATH")
    if not local_path:
        raise RuntimeError("Missing required environment variable: LEROY_GIT_LOCAL_PATH")
    return Path(os.path.expanduser(local_path)) / "override.toml"
