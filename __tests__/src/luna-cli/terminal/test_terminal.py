"""Resolve terminal folders using fake processes and desktop tools only."""

import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location("luna_terminal", REPO / "src/luna-cli/terminal/terminal.py")
terminal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(terminal)

FAKE_TOOL = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["TERMINAL_TEST_ROOT"])
name = pathlib.Path(sys.argv[0]).name
with (root / "calls").open("a") as log:
    log.write(json.dumps({"args": [name] + sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
if name == "xdg-terminal-exec":
    sys.exit(0)
sys.stdout.write(os.environ.get(name.upper() + "_RESULT", "{}"))
sys.exit(int(os.environ.get(name.upper() + "_STATUS", "0")))
'''


class TerminalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luna-terminal-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home's $(literal); [folder]"
        self.project = self.root / "project's $(literal); [folder]"
        self.proc = self.root / "proc"
        self.tools = self.root / "tools"
        self.runtime = self.root / "runtime"
        for path in (self.home, self.project, self.proc, self.tools, self.runtime):
            path.mkdir()
        for name in ("hyprctl", "kitten", "xdg-terminal-exec"):
            tool = self.tools / name
            tool.write_text(f"#!{sys.executable}\n" + FAKE_TOOL)
            tool.chmod(0o755)
        # The CLI needs these utilities; omit every real desktop command from PATH.
        for name in ("bash", "dirname", "readlink"):
            (self.tools / name).symlink_to(Path("/usr/bin") / name)
        (self.tools / "python3").symlink_to(sys.executable)
        self.shells = self.root / "shells"
        self.shells.write_text(str(self.executable("zsh")) + "\n")
        environment = dict(os.environ, HOME=str(self.home), PATH=str(self.tools),
                           XDG_RUNTIME_DIR=str(self.runtime), TERMINAL_TEST_ROOT=str(self.root),
                           HYPRCTL_RESULT=json.dumps({"pid": 10, "class": "custom-terminal"}))
        for name in ("LUNA_INSTALL_DIR", "LUNA_CONFIG_DIR", "BASH_ENV", "ENV"):
            environment.pop(name, None)
        self.enterContext(patch.dict(os.environ, environment, clear=True))
        self.enterContext(patch.object(terminal, "PROC", self.proc))
        self.enterContext(patch.object(terminal, "SHELLS", self.shells))

    def executable(self, name):
        executable = self.root / "executables" / name
        executable.parent.mkdir(exist_ok=True)
        executable.touch()
        return executable

    def process(self, pid, executable, cwd=None, children=()):
        process = self.proc / str(pid)
        process.mkdir(exist_ok=True)
        (process / "exe").symlink_to(self.executable(executable))
        if cwd is not None:
            (process / "cwd").symlink_to(cwd)
        task = process / "task" / str(pid)
        task.mkdir(parents=True)
        (task / "children").write_text(" ".join(map(str, children)))

    def kitty_socket(self, pid=10):
        connection = socket.socket(socket.AF_UNIX)
        self.addCleanup(connection.close)
        path = self.runtime / f"luna-kitty-{pid}"
        connection.bind(str(path))
        return path

    def kitty_result(self, *panes):
        os.environ["KITTEN_RESULT"] = json.dumps([{"tabs": [{"windows": panes}]}])

    def calls(self):
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_focused_kitty_pane_uses_shell_folder_during_foreground_job(self):
        self.process(10, "kitty")
        socket_path = self.kitty_socket()
        self.kitty_result({"cwd": str(self.project),
                           "foreground_processes": [{"cmdline": ["vim"], "cwd": str(self.home)}]})

        self.assertEqual(terminal.directory_for(), str(self.project))
        self.assertEqual([call["args"] for call in self.calls()], [
            ["hyprctl", "-j", "activewindow"],
            ["kitten", "@", "--to", f"unix:{socket_path}", "--use-password", "never",
             "ls", "--match", "state:focused"],
        ])

    def test_captured_pid_ignores_new_focus_and_other_kitty_sockets(self):
        self.process(10, "kitty")
        self.kitty_socket(11)
        self.kitty_result({"cwd": str(self.project)})
        self.assertEqual(terminal.directory_for(10), str(self.home))
        self.assertEqual(self.calls(), [])

        self.kitty_socket(10)
        self.assertEqual(terminal.directory_for(10), str(self.project))
        self.assertEqual([call["args"][0] for call in self.calls()], ["kitten"])

    def test_browser_cannot_supply_a_folder_even_with_terminal_window_class(self):
        self.process(10, "zen", children=[11])
        self.process(11, "zsh", self.project)
        os.environ["HYPRCTL_RESULT"] = json.dumps({"pid": 10, "class": "kitty"})
        self.assertEqual(terminal.directory_for(), str(self.home))
        self.assertEqual([call["args"][0] for call in self.calls()], ["hyprctl"])

    def test_missing_focus_and_malformed_window_state_fall_back_home(self):
        for result in ("{}", "null", "[]", "not JSON", '{"pid": true}', '{"pid": "10"}',
                       '{"pid": 0}', '{"pid": -1}', '{"pid": 10}'):
            with self.subTest(result=result):
                os.environ["HYPRCTL_RESULT"] = result
                self.assertEqual(terminal.directory_for(), str(self.home))

    def test_unavailable_desktop_api_falls_back_home(self):
        os.environ["HYPRCTL_STATUS"] = "1"
        self.assertEqual(terminal.directory_for(), str(self.home))
        (self.tools / "hyprctl").unlink()
        self.assertEqual(terminal.directory_for(), str(self.home))

        self.process(10, "kitty")
        self.kitty_socket()
        os.environ["KITTEN_STATUS"] = "1"
        self.assertEqual(terminal.directory_for(10), str(self.home))
        (self.tools / "kitten").unlink()
        self.assertEqual(terminal.directory_for(10), str(self.home))

    def test_malformed_or_ambiguous_kitty_panes_fall_back_home(self):
        self.process(10, "kitty")
        self.kitty_socket()
        for result in ("not JSON", "{}", "null", "[]", '[{"tabs": null}]'):
            with self.subTest(result=result):
                os.environ["KITTEN_RESULT"] = result
                self.assertEqual(terminal.directory_for(10), str(self.home))
        for folder in (None, "relative", str(self.root / "missing"), str(self.shells)):
            with self.subTest(folder=folder):
                self.kitty_result({"cwd": folder})
                self.assertEqual(terminal.directory_for(10), str(self.home))
        self.kitty_result({"cwd": str(self.project)}, {"cwd": str(self.home)})
        self.assertEqual(terminal.directory_for(10), str(self.home))

    def test_proc_fallback_accepts_one_allowed_shell_and_ignores_foreground_job(self):
        self.process(10, "kitty", children=[11, 12])
        self.process(11, "zsh", self.project, children=[13])
        self.process(12, "kitty-helper", self.home)
        self.process(13, "vim", self.home)
        other_task = self.proc / "10/task/14"
        other_task.mkdir()
        (other_task / "children").write_text("11")
        self.assertEqual(terminal.directory_for(10), str(self.project))
        self.assertEqual(self.calls(), [])

    def test_proc_fallback_rejects_multiple_shells_or_unlisted_shell(self):
        self.process(10, "foot", children=[11, 12])
        self.process(11, "zsh", self.project)
        self.process(12, "zsh", self.home)
        self.assertEqual(terminal.directory_for(10), str(self.home))
        self.shells.write_text("# No permitted shells\n")
        self.assertEqual(terminal.directory_for(10), str(self.home))

    def test_launch_passes_the_literal_folder_to_the_default_terminal(self):
        self.process(10, "foot", children=[11])
        self.process(11, "zsh", self.project)
        with patch.object(terminal.os, "chdir") as chdir, patch.object(terminal.os, "execvp") as execute:
            terminal.launch(10)
        chdir.assert_called_once_with(str(self.project))
        execute.assert_called_once_with("xdg-terminal-exec", ["xdg-terminal-exec", f"--dir={self.project}"])

    @unittest.skipUnless(Path("/usr/bin/lua").exists(), "System Lua is required")
    def test_cli_pid_zero_opens_home_without_querying_the_desktop(self):
        result = subprocess.run([str(REPO / "bin/luna"), "terminal", "--pid=0"],
                                cwd=self.project, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [{"args": ["xdg-terminal-exec", f"--dir={self.home}"],
                                        "cwd": str(self.home)}])


if __name__ == "__main__":
    unittest.main()
