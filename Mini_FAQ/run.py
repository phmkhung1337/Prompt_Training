"""Portable launcher. Uses only the Python standard library until setup finishes."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import venv

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
RUNTIME_FILES = (
    "app.py", "llm_client.py", "retrieval.py", "response_schema.py", "streaming.py",
    "api_budget.py", "ui_theme.py", "ui.css", "design_tokens.json", "system_prompt.txt",
    ".env.example", ".streamlit/config.toml", "cli.py",
)
PROBE = """import json, sys
from importlib.metadata import version, PackageNotFoundError
packages = json.loads(sys.argv[1])
installed = {}
for name in packages:
    try:
        installed[name] = version(name)
    except PackageNotFoundError:
        installed[name] = None
print(json.dumps({'prefix': sys.prefix, 'base': sys.base_prefix, 'packages': installed}))
"""


class StartupError(Exception):
    pass


def python_in(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def requirements() -> dict[str, str]:
    result = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", line)
        if not match:
            raise StartupError("requirements.txt cần ghim phiên bản bằng package==version.")
        result[match[1]] = match[2]
    return result


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    # Do not inherit paths into another machine's Python or global packages.
    for name in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    env["PYTHONUTF8"] = "1"
    return env


def probe(python: Path, wanted: dict[str, str]) -> dict | None:
    try:
        process = subprocess.run(
            [str(python), "-c", PROBE, json.dumps(list(wanted))], cwd=ROOT,
            env=child_env(), capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        if process.returncode != 0:
            return None
        return json.loads(process.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def environment_is_local(info: dict | None) -> bool:
    if not info:
        return False
    try:
        if Path(info["prefix"]).resolve() != VENV.resolve():
            return False
        if Path(info["base"]).resolve() != Path(sys.base_prefix).resolve():
            return False
        config = (VENV / "pyvenv.cfg").read_text(encoding="utf-8-sig")
        home = re.search(r"(?m)^home\s*=\s*(.+)$", config)
        return bool(home and Path(home[1].strip()).is_dir())
    except (OSError, KeyError):
        return False


def backup_environment() -> None:
    # Only move the generated environment directly inside this project.
    if VENV.is_symlink() or VENV.resolve().parent != ROOT:
        raise StartupError(".venv trỏ ra ngoài project; hãy tạo môi trường riêng trong thư mục project.")
    backup = ROOT / f".venv.backup-{time.time_ns()}"
    if backup.resolve().parent != ROOT:
        raise StartupError("Đường dẫn sao lưu môi trường không hợp lệ.")
    VENV.rename(backup)
    print(f"Đã giữ môi trường cũ trong {backup.name}; sẽ tạo môi trường cho máy này.", flush=True)


def checked(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, env=child_env())
    if result.returncode:
        raise StartupError("Lệnh cài đặt thất bại. Xem lỗi phía trên, kiểm tra Internet rồi chạy lại start.bat hoặc python run.py.")


def ensure_environment(*, check_only: bool = False) -> Path:
    if sys.version_info < (3, 10):
        raise StartupError("Cần Python 3.10 trở lên; khuyến nghị Python 3.13 như môi trường đã kiểm thử.")
    missing = [name for name in RUNTIME_FILES if not (ROOT / name).is_file()]
    if not (ROOT / "faq.md").is_file() and not (ROOT / "faq.json").is_file():
        missing.append("faq.md hoặc faq.json")
    if missing:
        raise StartupError("Thiếu file project: " + ", ".join(missing))
    wanted = requirements()
    python = python_in(VENV)
    info = probe(python, wanted) if python.is_file() else None
    local = environment_is_local(info)
    matches = bool(local and info["packages"] == wanted)
    if check_only:
        if not matches:
            raise StartupError("Môi trường chưa sẵn sàng hoặc khác phiên bản. Chạy start.bat --setup hoặc python run.py --setup.")
        checked([str(python), "-m", "pip", "check"])
        print("OK: môi trường và các phiên bản thư viện hợp lệ.")
        print("Cấu hình .env: " + ("đã có" if (ROOT / ".env").is_file() else "chưa có; lần chạy đầu sẽ tạo từ .env.example"))
        return python
    if not local:
        if Path(sys.prefix).resolve() == VENV.resolve():
            raise StartupError("Hãy chạy start.bat hoặc Python hệ thống để tạo lại .venv, không chạy bằng môi trường cũ.")
        if VENV.exists():
            backup_environment()
        print("Đang tạo .venv cho máy hiện tại…", flush=True)
        try:
            venv.EnvBuilder(with_pip=True).create(VENV)
        except (OSError, subprocess.SubprocessError) as exc:
            raise StartupError("Không tạo được .venv. Kiểm tra bản cài Python có venv/ensurepip và quyền ghi thư mục project.") from exc
    if not matches:
        print("Đang cài thư viện theo requirements.txt; lần đầu cần Internet…", flush=True)
        checked([str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
        checked([str(python), "-m", "pip", "check"])
        installed = probe(python, wanted)
        if not environment_is_local(installed) or installed["packages"] != wanted:
            raise StartupError("Cài đặt chưa hoàn chỉnh. Chạy lại python run.py --setup và xem lỗi cài thư viện.")
    env_file = ROOT / ".env"
    if not env_file.exists():
        # Exclusive creation preserves existing local credentials.
        with env_file.open("x", encoding="utf-8") as destination:
            destination.write((ROOT / ".env.example").read_text(encoding="utf-8-sig"))
        print("Đã tạo .env từ mẫu. Điền key/model của máy này để bot gọi API.")
    return python


def configured_port() -> int:
    text = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^port\s*=\s*(\d+)\s*$", text)
    return int(match[1]) if match else 8510


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Cài đặt và chạy Campus FAQ trên máy hiện tại.")
    parser.add_argument("--setup", action="store_true", help="Chỉ chuẩn bị môi trường, không chạy server")
    parser.add_argument("--check", action="store_true", help="Kiểm tra môi trường, không cài hoặc gọi API")
    parser.add_argument("--cli", action="store_true", help="Chạy giao diện terminal")
    parser.add_argument("--port", type=int, help="Cổng web, mặc định theo .streamlit/config.toml")
    args = parser.parse_args(argv)
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port phải nằm trong khoảng 1–65535")
    try:
        python = ensure_environment(check_only=args.check)
        if args.setup or args.check:
            return 0
        if args.cli:
            command = [str(python), str(ROOT / "cli.py")]
        else:
            port = args.port if args.port is not None else configured_port()
            try:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", port))
            except OSError as exc:
                raise StartupError(f"Không mở được cổng {port}: cổng đang được dùng hoặc bị chặn. Thử start.bat --port {port + 1 if port < 65535 else 8510}.") from exc
            print(f"Mở http://127.0.0.1:{port} · Ctrl+C để dừng.", flush=True)
            command = [str(python), "-m", "streamlit", "run", str(ROOT / "app.py"),
                       "--server.address", "127.0.0.1", "--server.port", str(port),
                       "--server.headless", "true", "--browser.gatherUsageStats", "false"]
        return subprocess.run(command, cwd=ROOT, env=child_env()).returncode
    except StartupError as exc:
        print(f"Lỗi khởi động: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Không khởi động được: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
