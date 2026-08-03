import os
import subprocess
from typing import Any

from langchain_core.tools import tool


@tool
def trigger_offline_quota_computation() -> dict[str, Any]:
    """
    Triggers offline quota computation on the remote cplex host via SSH.
    This runs a git pull in the airflow config directory and then executes the quota script
    in the airflow worker container.
    """
    remote_host = os.environ.get(
        "LEROY_OFFLINE_REMOTE_HOST",
        "atjoshi@prod-perf-cplex10.dfw02.corp.akamai.com",
    )
    ssh_key_path = os.environ.get(
        "LEROY_OFFLINE_SSH_KEY_PATH",
        os.environ.get(
            "LEROY_GIT_SSH_KEY_PATH",
            "~/.ssh/internal/atjoshi-internal-2026-07-20",
        ),
    )
    repo_dir = os.environ.get(
        "LEROY_OFFLINE_REPO_DIR",
        "/ss1/netopt/atjoshi/netopt-airflow/tmpdata/git/leroy_config",
    )
    docker_container = os.environ.get(
        "LEROY_OFFLINE_DOCKER_CONTAINER",
        "netopt-airflow-airflow-worker-1",
    )
    dags_dir = os.environ.get("LEROY_OFFLINE_DAGS_DIR", "/opt/airflow/dags")
    script_path = os.environ.get(
        "LEROY_OFFLINE_SCRIPT_PATH",
        "lib/leroy/auxilary_scripts/compute_quota_offline.py",
    )
    override_path = os.environ.get(
        "LEROY_OFFLINE_OVERRIDE_PATH",
        "/opt/airflow/tmpdata/git/leroy_config/config/override/override.toml",
    )
    dynamic_path = os.environ.get(
        "LEROY_OFFLINE_DYNAMIC_PATH",
        "/opt/airflow/tmpdata/git/leroy_config/config/dynamic/dynamic_config.json",
    )
    timeout_seconds = int(os.environ.get("LEROY_OFFLINE_TRIGGER_TIMEOUT_SEC", "300"))

    remote_cmd = (
        f"cd {repo_dir} && "
        "git pull && "
        # Run docker exec, but redirect ALL output to a log file
        f"docker exec {docker_container} bash -c "
        f"'cd {dags_dir} && python3 {script_path} "
        f"--override={override_path} "
        f"--dynamic={dynamic_path}' > /tmp/leroy_offline_run.log 2>&1 ; "
        # Capture the exit code of the docker exec command
        "EXIT_CODE=$? ; "
        # Print the last 100 lines so the LLM still has debugging context
        "tail -n 100 /tmp/leroy_offline_run.log ; "
        # Exit with the original docker exec exit code
        "exit $EXIT_CODE"
    )

    full_cmd = (
        'eval "$(ssh-agent -s)" && '
        f"ssh-add {ssh_key_path} && "
        f'ssh -2A -o StrictHostKeyChecking=no -o BatchMode=yes {remote_host} "{remote_cmd}" ; '
        "kill $SSH_AGENT_PID"
    )

    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "host": remote_host,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "remote_command": remote_cmd,
            "shell_command": full_cmd,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "error": f"Offline quota computation timed out after {timeout_seconds} seconds.",
            "host": remote_host,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "remote_command": remote_cmd,
            "shell_command": full_cmd,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to trigger offline quota computation: {exc}",
            "host": remote_host,
            "stdout": "",
            "stderr": "",
            "remote_command": remote_cmd,
            "shell_command": full_cmd,
        }


CPLEX_TOOLS = [
    trigger_offline_quota_computation,
]
