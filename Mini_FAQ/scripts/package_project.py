"""Create a source-only ZIP that bootstraps its own environment on another PC."""

from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import RUNTIME_FILES


def package(destination: Path) -> Path:
    files = {ROOT / name for name in RUNTIME_FILES}
    files.update(ROOT / name for name in ("run.py", "start.bat", "requirements.txt", "README.md", ".gitignore", "CHAY_TREN_MAY_KHAC.md"))
    files.update(path for path in (ROOT / "faq.md", ROOT / "faq.json") if path.is_file())
    for directory in ("tests", "scripts"):
        files.update((ROOT / directory).glob("*.py"))
    if not (ROOT / "faq.md").is_file() and not (ROOT / "faq.json").is_file():
        raise FileNotFoundError("Thiếu FAQ")
    missing = [path.name for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("Thiếu file: " + ", ".join(missing))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, "Campus_FAQ/" + path.relative_to(ROOT).as_posix())
    return destination


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    output = package(ROOT / "dist" / "Campus_FAQ_portable.zip")
    print(output)
