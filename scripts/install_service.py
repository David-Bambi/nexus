"""Install or remove Nexus as a service that starts when the user's session opens.

Usage:
    uv run python scripts/install_service.py install
    uv run python scripts/install_service.py uninstall

Linux uses a systemd user unit, macOS a launchd agent, Windows a scheduled
task. The definitions are rendered by pure functions so they can be tested
on any platform; only the registration step talks to the operating system.
"""
import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable
from xml.sax.saxutils import escape

# Repo root, where `python -m src.main` must run.
REPO = Path(__file__).resolve().parent.parent

# Name of the systemd unit and of the Windows scheduled task.
SERVICE_NAME = "nexus"

# Identifier of the launchd agent.
LAUNCHD_LABEL = "com.nexus.app"


def _command(uv : str, repo : Path) -> list:
    """Return the command line that starts the app.

    Args:
        uv: Path of the uv executable.
        repo: Path of the repository.

    Returns:
        The arguments, without any host option: the server address is fixed
        in the app itself (ADR-0004).
    """
    return [uv, "run", "--frozen", "--directory", str(repo), "python", "-m", "src.main"]


def _quote(argument : str) -> str:
    """Wrap an argument in double quotes when it contains whitespace."""
    return f'"{argument}"' if any(c.isspace() for c in argument) else argument


def render_systemd_unit(uv : str, repo : Path, nexus_home : str | None = None) -> str:
    """Render the systemd user unit.

    Args:
        uv: Path of the uv executable.
        repo: Path of the repository.
        nexus_home: Value of NEXUS_HOME to pass to the app, if any.

    Returns:
        The unit file content.
    """
    lines = [
        "[Unit]",
        "Description=Nexus local project manager",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={_quote(str(repo))}",
        f"ExecStart={' '.join(_quote(a) for a in _command(uv, repo))}",
        "Restart=on-failure",
        "RestartSec=2",
    ]
    if nexus_home:
        lines.append(f"Environment={_quote('NEXUS_HOME=' + nexus_home)}")
    lines += ["", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(lines)


def render_launchd_plist(uv : str, repo : Path, log_file : Path, nexus_home : str | None = None) -> bytes:
    """Render the launchd agent definition.

    Args:
        uv: Path of the uv executable.
        repo: Path of the repository.
        log_file: File receiving the service's stdout and stderr.
        nexus_home: Value of NEXUS_HOME to pass to the app, if any.

    Returns:
        The property list, in XML.
    """
    definition = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": _command(uv, repo),
        "WorkingDirectory": str(repo),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }
    if nexus_home:
        definition["EnvironmentVariables"] = {"NEXUS_HOME": nexus_home}
    return plistlib.dumps(definition)


def render_windows_task(uv : str, repo : Path) -> str:
    """Render the Windows scheduled task definition.

    Args:
        uv: Path of the uv executable.
        repo: Path of the repository.

    Returns:
        The task as XML: started at logon, restarted up to 3 times, one
        minute apart, if it fails.
    """
    arguments = " ".join(_quote(a) for a in _command(uv, repo)[1:])
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Nexus local project manager</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(uv)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(str(repo))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def detect_platform() -> str:
    """Return "linux", "macos" or "windows" for the running system.

    Raises:
        SystemExit: On any other system.
    """
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    raise SystemExit(f"Unsupported platform: {sys.platform}")


def systemd_unit_path(home : Path) -> Path:
    """Return where the systemd user unit lives."""
    return home / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def launchd_plist_path(home : Path) -> Path:
    """Return where the launchd agent definition lives."""
    return home / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _write(path : Path, content : str | bytes, encoding : str = "utf-8") -> None:
    """Write a file, creating its folder.

    An existing symbolic link at the destination is replaced rather than
    written through: a link left over from an older setup may point nowhere.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding)


def install(platform : str, uv : str, repo : Path, home : Path, nexus_home : str | None,
            run : Callable = subprocess.run) -> None:
    """Register the service for the given platform and start it.

    Args:
        platform: "linux", "macos" or "windows".
        uv: Path of the uv executable.
        repo: Path of the repository.
        home: The user's home directory.
        nexus_home: Value of NEXUS_HOME to pass to the app, if any.
        run: Function used to run system commands (replaced in tests).
    """
    if platform == "linux":
        _write(systemd_unit_path(home), render_systemd_unit(uv, repo, nexus_home))
        run(["systemctl", "--user", "daemon-reload"], check=True)
        run(["systemctl", "--user", "enable", SERVICE_NAME], check=True)
        # restart, not start: a reinstall must pick up a changed definition.
        run(["systemctl", "--user", "restart", SERVICE_NAME], check=True)
    elif platform == "macos":
        path = launchd_plist_path(home)
        log_file = Path(nexus_home).expanduser() / "app.log" if nexus_home else home / ".nexus" / "app.log"
        _write(path, render_launchd_plist(uv, repo, log_file, nexus_home))
        run(["launchctl", "unload", str(path)], check=False)
        run(["launchctl", "load", "-w", str(path)], check=True)
    elif platform == "windows":
        if nexus_home:
            print("Note: NEXUS_HOME is not carried into the Windows task; the default folder is used.")
        with tempfile.TemporaryDirectory() as folder:
            definition = Path(folder) / f"{SERVICE_NAME}.xml"
            _write(definition, render_windows_task(uv, repo), encoding="utf-16")
            run(["schtasks", "/Create", "/TN", SERVICE_NAME, "/XML", str(definition), "/F"], check=True)
        run(["schtasks", "/Run", "/TN", SERVICE_NAME], check=True)
    else:
        raise ValueError(f"unknown platform '{platform}'")


def uninstall(platform : str, home : Path, run : Callable = subprocess.run) -> None:
    """Stop and remove the service for the given platform.

    Only removes what install() created; the app's data is never touched.

    Args:
        platform: "linux", "macos" or "windows".
        home: The user's home directory.
        run: Function used to run system commands (replaced in tests).
    """
    if platform == "linux":
        run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
        systemd_unit_path(home).unlink(missing_ok=True)
        run(["systemctl", "--user", "daemon-reload"], check=True)
    elif platform == "macos":
        path = launchd_plist_path(home)
        run(["launchctl", "unload", str(path)], check=False)
        path.unlink(missing_ok=True)
    elif platform == "windows":
        run(["schtasks", "/End", "/TN", SERVICE_NAME], check=False)
        run(["schtasks", "/Delete", "/TN", SERVICE_NAME, "/F"], check=False)
    else:
        raise ValueError(f"unknown platform '{platform}'")


def main(argv : list | None = None) -> int:
    """Command-line entry point.

    Args:
        argv: Arguments, defaulting to sys.argv.

    Returns:
        The process exit code.
    """
    parser = argparse.ArgumentParser(description="Install or remove the Nexus service.")
    parser.add_argument("action", choices=["install", "uninstall"])
    args = parser.parse_args(argv)

    platform = detect_platform()
    try:
        if args.action == "install":
            uv = shutil.which("uv")
            if uv is None:
                print("Cannot find the 'uv' executable on PATH.", file=sys.stderr)
                return 1
            install(platform, uv, REPO, Path.home(), os.environ.get("NEXUS_HOME"))
            print(f"Nexus service installed and started ({platform}).")
            if platform == "linux":
                print("To start it at boot without logging in, run once: loginctl enable-linger")
        else:
            uninstall(platform, Path.home())
            print(f"Nexus service removed ({platform}). Your data was not touched.")
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
