"""数据与启动脚本不能重新绑定到开发者个人机器路径。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OPERATIONAL_FILES = [
    PROJECT_ROOT / "start-windows.bat",
    *sorted((PROJECT_ROOT / "scripts").rglob("*.ps1")),
    *sorted((PROJECT_ROOT / "scripts").rglob("*.py")),
    PROJECT_ROOT / "backend-python" / "app" / "cli" / "import_knowledge.py",
]


def test_operational_scripts_do_not_contain_machine_specific_paths() -> None:
    forbidden = ("F:\\Datasets\\AgriGraph", "D:\\Codesoftwares\\anaconda")
    violations = {
        path.relative_to(PROJECT_ROOT).as_posix(): value
        for path in OPERATIONAL_FILES
        for value in forbidden
        if value.lower() in path.read_text(encoding="utf-8-sig").lower()
    }

    assert violations == {}
