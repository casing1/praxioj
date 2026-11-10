"""Offline build-tool regressions for the two preflight setuptools advisories.

Only synthetic fixture text is used. Builds and legacy metadata handling run in
pytest temporary directories. No artifact is installed and no packaged module
or external provider is run.
"""

from importlib.metadata import version
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import unicodedata

from packaging.requirements import Requirement
from packaging.version import Version
import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_build_backend_pins_match_test_environment_and_shared_lock():
    """A future one-package Dependabot bump must not split build tool versions."""
    lock = {
        requirement.name.lower(): requirement
        for line in (ROOT / "requirements.lock").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for requirement in [Requirement(line)]
    }
    installed = Version(version("setuptools"))
    assert installed >= Version("84.1.0"), "Both reported setuptools flaws require at least 84.1.0"
    assert "setuptools" in lock, "Build tooling must be included in the shared dependency lock"
    for package in ("packages/framework", "apps/api"):
        project = tomllib.loads((ROOT / package / "pyproject.toml").read_text())
        backend = [Requirement(value) for value in project["build-system"]["requires"]]
        pin = next(requirement for requirement in backend if requirement.name.lower() == "setuptools")
        assert str(pin.specifier).startswith("==")
        assert pin.specifier == lock["setuptools"].specifier
        assert installed in pin.specifier


def test_sdist_exclusion_handles_unicode_normalization(tmp_path):
    """GHSA-h35f-9h28-mq5c: NFC exclusion must omit an NFD filename in the artifact."""
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(name='praxioj-packaging-fixture', version='1.0', py_modules=['sample'])\n"
    )
    (fixture / "sample.py").write_text("# Synthetic packaging fixture; never imported.\n")
    (fixture / "README.txt").write_text("Public synthetic fixture text.\n")
    filename = "private_caf\u00e9.txt"
    (fixture / unicodedata.normalize("NFD", filename)).write_text("Synthetic excluded canary.\n")
    (fixture / "MANIFEST.in").write_text(f"global-include *.txt\nglobal-exclude {filename}\n")
    build = subprocess.run(
        [sys.executable, "-c", "from setuptools.build_meta import build_sdist; build_sdist('dist')"],
        cwd=fixture, capture_output=True, text=True, timeout=30,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    artifacts = list((fixture / "dist").glob("*.tar.gz"))
    assert len(artifacts) == 1
    with tarfile.open(artifacts[0]) as archive:
        members = {unicodedata.normalize("NFC", Path(name).name) for name in archive.getnames()}
    assert "README.txt" in members, "The control file must be included so exclusion is actually exercised"
    assert filename not in members


@pytest.mark.parametrize("name", [r"C:\Windows", r"\\server\share", "/outside", "../outside"])
def test_legacy_wheel_rejects_path_like_namespace_metadata(tmp_path, name):
    """GHSA-xmj3-9gf7-h52w: validate metadata before any filesystem mutation."""
    from setuptools.wheel import _resolve_namespace_dir

    with pytest.raises(ValueError, match="invalid namespace package name"):
        _resolve_namespace_dir(str(tmp_path / "destination"), name)


def test_legacy_wheel_does_not_write_outside_temporary_destination(tmp_path):
    """Exercise the legacy metadata consumer, with every possible write inside tmp_path."""
    from setuptools.wheel import Wheel

    destination = tmp_path / "destination"
    outside = tmp_path / "outside"
    metadata = destination / "EGG-INFO"
    metadata.mkdir(parents=True)
    outside.mkdir()
    canary = outside / "canary.txt"
    canary.write_text("Keep this synthetic file unchanged.\n")
    original = canary.read_bytes()
    (metadata / "namespace_packages.txt").write_text(str(outside))
    with pytest.raises(ValueError, match="invalid namespace package name"):
        Wheel._fix_namespace_packages(str(metadata), str(destination))
    assert not (outside / "__init__.py").exists()
    assert canary.read_bytes() == original
