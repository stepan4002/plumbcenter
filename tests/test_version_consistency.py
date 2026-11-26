"""The release workflow and the exe smoke test rely on these three version strings agreeing."""

import re
from pathlib import Path

import plumbcenter

ROOT = Path(__file__).resolve().parent.parent


def test_package_pyproject_and_exe_metadata_agree():
    pyproject = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")
    product = re.search(r"StringStruct\('ProductVersion', '([^']+)'\)", info).group(1)
    file_ver = re.search(r"StringStruct\('FileVersion', '([^']+)'\)", info).group(1)
    fixed = tuple(int(x) for x in re.search(r"filevers=\(([\d, ]+)\)", info).group(1).split(","))
    assert plumbcenter.__version__ == pyproject == product == file_ver
    assert fixed[:3] == tuple(int(x) for x in pyproject.split("."))


def test_release_workflow_triggers_on_version_tags():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "tags:" in wf and "v[0-9]" in wf
    assert "windows-latest" in wf and "packaging/build.ps1" in wf
    assert "branches:" not in wf          # never fires on a branch push
