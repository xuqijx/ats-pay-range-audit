"""Copy fictional fixtures into the wheel at build time. The sdist keeps them at the root."""

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        root = Path.cwd()
        dest = Path(self.build_lib) / "ats_pay_range_audit" / "bundled"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        shutil.copytree(root / "fixtures", dest / "fixtures")
        shutil.copytree(root / "examples", dest / "examples")
        (dest / "__init__.py").write_text(
            '"""Fictional fixtures and example boards copied into the wheel."""\n',
            encoding="utf-8",
        )


setup(cmdclass={"build_py": BuildPy})
