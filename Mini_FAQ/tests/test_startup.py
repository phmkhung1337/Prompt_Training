import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import run
from scripts.package_project import package


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.venv = self.root / ".venv"
        (self.root / "app.py").write_text("", encoding="utf-8")
        (self.root / "faq.md").write_text("### Q\nA", encoding="utf-8")
        (self.root / ".env.example").write_text("API_KEY=placeholder\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("demo==1.0\n", encoding="utf-8")
        for context in (
            patch.object(run, "ROOT", self.root), patch.object(run, "VENV", self.venv),
            patch.object(run, "REQUIREMENTS", self.root / "requirements.txt"),
            patch.object(run, "RUNTIME_FILES", ("app.py", ".env.example")),
        ):
            context.start()
            self.addCleanup(context.stop)

    def create_environment(self, folder):
        folder.mkdir()
        (folder / "pyvenv.cfg").write_text(f"home = {sys.base_prefix}\n", encoding="utf-8")
        executable = run.python_in(folder)
        executable.parent.mkdir()
        executable.write_text("", encoding="utf-8")

    def valid_info(self):
        return {"prefix": str(self.venv), "base": sys.base_prefix, "packages": {"demo": "1.0"}}

    def test_first_run_creates_environment_dependencies_and_env(self):
        with patch.object(run.venv, "EnvBuilder") as builder, patch.object(run, "probe", return_value=self.valid_info()), patch.object(run, "checked") as checked:
            builder.return_value.create.side_effect = self.create_environment
            python = run.ensure_environment()
        self.assertEqual(python, run.python_in(self.venv))
        builder.assert_called_once_with(with_pip=True)
        self.assertIn("install", checked.call_args_list[0].args[0])
        self.assertEqual((self.root / ".env").read_text(), "API_KEY=placeholder\n")

    def test_matching_environment_does_not_install_or_overwrite_credentials(self):
        self.create_environment(self.venv)
        (self.root / ".env").write_text("KEEP_THIS_VALUE", encoding="utf-8")
        with patch.object(run, "probe", return_value=self.valid_info()), patch.object(run, "checked") as checked:
            run.ensure_environment()
        checked.assert_not_called()
        self.assertEqual((self.root / ".env").read_text(), "KEEP_THIS_VALUE")

    def test_copied_environment_is_backed_up_and_recreated(self):
        self.create_environment(self.venv)
        marker = self.venv / "keep.txt"
        marker.write_text("old environment", encoding="utf-8")
        copied = dict(self.valid_info(), base=str(self.root / "another-computer"))
        with patch.object(run, "probe", side_effect=[copied, self.valid_info()]), patch.object(run.venv, "EnvBuilder") as builder, patch.object(run, "checked"):
            builder.return_value.create.side_effect = self.create_environment
            run.ensure_environment()
        backups = list(self.root.glob(".venv.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "keep.txt").read_text(), "old environment")
        self.assertFalse((self.venv / "keep.txt").exists())

    def test_check_is_read_only_when_environment_missing(self):
        with self.assertRaisesRegex(run.StartupError, "chưa sẵn sàng"):
            run.ensure_environment(check_only=True)
        self.assertFalse(self.venv.exists())
        self.assertFalse((self.root / ".env").exists())

    def test_environment_outside_project_cannot_be_moved(self):
        with patch.object(run, "VENV", self.root.parent / "outside-environment"):
            with self.assertRaisesRegex(run.StartupError, "ngoài project"):
                run.backup_environment()

    def test_used_port_reports_action_without_starting_another_server(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.listen()
            with patch.object(run, "ensure_environment", return_value=Path(sys.executable)), patch.object(run.subprocess, "run") as start:
                self.assertEqual(run.main(["--port", str(port)]), 1)
            start.assert_not_called()

    def test_package_contains_runtime_assets_without_local_keys_or_environment(self):
        archive = package(self.root / "portable.zip")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            for needed in ("run.py", "start.bat", "app.py", "ui.css", "design_tokens.json", "faq.md", ".streamlit/config.toml", ".env.example"):
                self.assertIn("Campus_FAQ/" + needed, names)
            self.assertFalse(any(Path(name).name == ".env" or "secrets.toml" in name for name in names))
            self.assertFalse(any("/.venv/" in name or "/.cache/" in name or "/.git/" in name for name in names))
            self.assertIsNone(bundle.testzip())
