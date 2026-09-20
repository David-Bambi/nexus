import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts import install_service as svc

UV = "/usr/local/bin/uv"
REPO = Path("/home/user/nexus")


class Recorder:
    """Stands in for subprocess.run and remembers the commands it was given."""

    def __init__(self):
        self.commands = []

    def __call__(self, command, check):
        self.commands.append(command)


# Rendering ----------------------------------------------------------------------------------------

def test_systemd_unit_restarts_on_failure_and_starts_at_login():
    """The systemd unit restarts the app on failure and starts with the user session
    Given a uv path and a repository path
    When rendering the unit
    Then it restarts on failure, runs from the repo and is wanted by default.target
    """
    unit = svc.render_systemd_unit(UV, REPO)

    assert "Restart=on-failure" in unit
    assert "RestartSec=2" in unit
    assert "WantedBy=default.target" in unit
    assert f"WorkingDirectory={REPO}" in unit
    assert f"ExecStart={UV} run --frozen --directory {REPO} python -m src.main" in unit

def test_systemd_unit_passes_nexus_home_only_when_given():
    """The unit sets NEXUS_HOME only when one was given
    Given a render with and without a data folder
    When reading both units
    Then only the first has an Environment line
    """
    assert "Environment=NEXUS_HOME=/data/nexus" in svc.render_systemd_unit(UV, REPO, "/data/nexus")
    assert "Environment" not in svc.render_systemd_unit(UV, REPO)

def test_systemd_unit_quotes_paths_with_spaces():
    """Paths containing spaces are quoted
    Given a repository path with a space
    When rendering the unit
    Then the working directory and the command quote it
    """
    unit = svc.render_systemd_unit(UV, Path("/home/my user/nexus"))

    assert 'WorkingDirectory="/home/my user/nexus"' in unit
    assert '--directory "/home/my user/nexus"' in unit

def test_launchd_plist_keeps_alive_and_runs_at_load():
    """The launchd agent starts at load and is kept alive
    Given a uv path, a repository and a log file
    When rendering the plist
    Then it has RunAtLoad and KeepAlive, the command and the log paths
    """
    plist = plistlib.loads(svc.render_launchd_plist(UV, REPO, Path("/home/user/.nexus/app.log")))

    assert plist["Label"] == svc.LAUNCHD_LABEL
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["ProgramArguments"] == [UV, "run", "--frozen", "--directory", str(REPO), "python", "-m", "src.main"]
    assert plist["StandardErrorPath"] == "/home/user/.nexus/app.log"
    assert "EnvironmentVariables" not in plist

def test_launchd_plist_passes_nexus_home():
    """The plist sets NEXUS_HOME when one was given
    Given a data folder
    When rendering the plist
    Then it is in the environment variables
    """
    plist = plistlib.loads(svc.render_launchd_plist(UV, REPO, Path("/log"), "/data/nexus"))
    assert plist["EnvironmentVariables"] == {"NEXUS_HOME": "/data/nexus"}

def test_windows_task_starts_at_logon_and_restarts():
    """The Windows task starts at logon and restarts on failure
    Given a uv path and a repository path
    When rendering the task
    Then it has a logon trigger, a restart policy and the right command
    """
    root = ET.fromstring(svc.render_windows_task("C:\\Tools\\uv.exe", Path("C:\\Users\\me\\nexus")).split("?>", 1)[1])
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

    assert root.find("t:Triggers/t:LogonTrigger", ns) is not None
    assert root.find("t:Settings/t:RestartOnFailure/t:Count", ns).text == "3"
    assert root.find("t:Actions/t:Exec/t:Command", ns).text == "C:\\Tools\\uv.exe"
    assert "python -m src.main" in root.find("t:Actions/t:Exec/t:Arguments", ns).text

def test_no_definition_sets_a_host():
    """No rendered definition selects a network address
    Given the three rendered definitions
    When searching them for a host option or address
    Then none is found, the app keeps its fixed loopback binding
    """
    rendered = [
        svc.render_systemd_unit(UV, REPO),
        svc.render_launchd_plist(UV, REPO, Path("/log")).decode(),
        svc.render_windows_task(UV, REPO),
    ]
    for text in rendered:
        assert "0.0.0.0" not in text
        assert "--host" not in text
        assert "NEXUS_HOST" not in text


# Installing ---------------------------------------------------------------------------------------

def test_install_linux_writes_unit_and_starts_it(tmp_path):
    """Linux install writes the unit and enables and restarts the service
    Given a fresh home directory
    When installing on linux
    Then the unit file exists and systemctl was told to reload, enable and restart
    """
    run = Recorder()

    svc.install("linux", UV, REPO, tmp_path, None, run)

    assert (tmp_path / ".config/systemd/user/nexus.service").read_text().startswith("[Unit]")
    assert run.commands == [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "nexus"],
        ["systemctl", "--user", "restart", "nexus"],
    ]

def test_install_replaces_a_dangling_symlink(tmp_path):
    """Install replaces a leftover symlink instead of writing through it
    Given a nexus.service symlink pointing to a file that doesn't exist
    When installing on linux
    Then the path is now a regular file holding the unit
    """
    unit = tmp_path / ".config/systemd/user/nexus.service"
    unit.parent.mkdir(parents=True)
    unit.symlink_to(tmp_path / "gone" / "nexus.service")

    svc.install("linux", UV, REPO, tmp_path, None, Recorder())

    assert not unit.is_symlink()
    assert unit.read_text().startswith("[Unit]")
    assert not (tmp_path / "gone").exists()

def test_uninstall_linux_removes_only_the_unit(tmp_path):
    """Linux uninstall removes the unit and nothing else
    Given an installed unit and another file in the same folder
    When uninstalling
    Then the unit is gone, the other file and the data folder remain
    """
    run = Recorder()
    svc.install("linux", UV, REPO, tmp_path, None, run)
    other = tmp_path / ".config/systemd/user/other.service"
    other.write_text("keep me")
    data = tmp_path / ".nexus" / "data.db"
    data.parent.mkdir()
    data.write_text("my data")

    svc.uninstall("linux", tmp_path, run)

    assert not (tmp_path / ".config/systemd/user/nexus.service").exists()
    assert other.read_text() == "keep me"
    assert data.read_text() == "my data"
    assert ["systemctl", "--user", "disable", "--now", "nexus"] in run.commands

def test_uninstall_when_nothing_is_installed(tmp_path):
    """Uninstalling a service that isn't installed doesn't fail
    Given a home directory without a unit
    When uninstalling on linux
    Then it completes without error
    """
    svc.uninstall("linux", tmp_path, Recorder())

def test_install_macos_writes_plist_and_loads_it(tmp_path):
    """macOS install writes the agent definition and loads it
    Given a fresh home directory
    When installing on macos
    Then the plist exists and launchctl load was called for it
    """
    run = Recorder()

    svc.install("macos", UV, REPO, tmp_path, None, run)

    plist = tmp_path / "Library/LaunchAgents/com.nexus.app.plist"
    assert plistlib.loads(plist.read_bytes())["Label"] == "com.nexus.app"
    assert ["launchctl", "load", "-w", str(plist)] in run.commands

def test_uninstall_macos_unloads_and_removes_the_plist(tmp_path):
    """macOS uninstall unloads and deletes the agent definition
    Given an installed agent
    When uninstalling
    Then launchctl unload ran and the plist is gone
    """
    run = Recorder()
    svc.install("macos", UV, REPO, tmp_path, None, run)
    plist = tmp_path / "Library/LaunchAgents/com.nexus.app.plist"

    svc.uninstall("macos", tmp_path, run)

    assert not plist.exists()
    assert ["launchctl", "unload", str(plist)] in run.commands

def test_install_windows_creates_and_runs_the_task(tmp_path):
    """Windows install registers the task from XML and starts it
    Given a fresh home directory
    When installing on windows
    Then schtasks creates the task from an XML file, then runs it
    """
    run = Recorder()

    svc.install("windows", UV, REPO, tmp_path, None, run)

    create, start = run.commands
    assert create[:5] == ["schtasks", "/Create", "/TN", "nexus", "/XML"]
    assert create[-1] == "/F"
    assert start == ["schtasks", "/Run", "/TN", "nexus"]

def test_uninstall_windows_deletes_the_task(tmp_path):
    """Windows uninstall ends and deletes the task
    Given any state
    When uninstalling on windows
    Then schtasks is told to end then delete it
    """
    run = Recorder()

    svc.uninstall("windows", tmp_path, run)

    assert run.commands == [["schtasks", "/End", "/TN", "nexus"], ["schtasks", "/Delete", "/TN", "nexus", "/F"]]

def test_unknown_platform_is_rejected(tmp_path):
    """An unknown platform name is refused
    Given a platform that doesn't exist
    When installing
    Then a ValueError is raised
    """
    with pytest.raises(ValueError):
        svc.install("plan9", UV, REPO, tmp_path, None, Recorder())


# Detection and CLI --------------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [("linux", "linux"), ("darwin", "macos"), ("win32", "windows")])
def test_detect_platform(monkeypatch, name, expected):
    """The running system is mapped to a platform name
    Given sys.platform set to a known value
    When detecting the platform
    Then the matching name is returned
    """
    monkeypatch.setattr(sys, "platform", name)
    assert svc.detect_platform() == expected

def test_detect_platform_rejects_others(monkeypatch):
    """An unsupported system stops the script
    Given sys.platform set to an unsupported value
    When detecting the platform
    Then the script exits
    """
    monkeypatch.setattr(sys, "platform", "freebsd14")
    with pytest.raises(SystemExit):
        svc.detect_platform()

def test_install_fails_cleanly_without_uv(monkeypatch, capsys):
    """Install reports a missing uv instead of crashing
    Given no uv on the PATH
    When running the install command
    Then the exit code is 1 and the message names uv
    """
    monkeypatch.setattr(svc.shutil, "which", lambda name: None)

    assert svc.main(["install"]) == 1
    assert "uv" in capsys.readouterr().err

def test_failed_system_command_gives_exit_code_one(monkeypatch, capsys):
    """A failing system command is reported, not raised
    Given an install that fails on a system command
    When running the install command
    Then the exit code is 1 and the error is printed
    """
    def failing_install(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["systemctl"])
    monkeypatch.setattr(svc.shutil, "which", lambda name: UV)
    monkeypatch.setattr(svc, "detect_platform", lambda: "linux")
    monkeypatch.setattr(svc, "install", failing_install)

    assert svc.main(["install"]) == 1
    assert "Failed" in capsys.readouterr().err
