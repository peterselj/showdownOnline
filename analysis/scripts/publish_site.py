"""Publish the showdown2000.fun explorer to GitHub Pages.

The site lives in its own public repo, github.com/peterselj/showdown2000analysis, served at
https://peterselj.github.io/showdown2000analysis/. This copies results/site/index.html (written
by build_sd2000.py: the same page, without other players' team names) into that repo and pushes.

Usage:  python scripts/build_sd2000.py && python scripts/publish_site.py
Needs git and a GitHub login with push access (gh auth login).
"""
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/peterselj/showdown2000analysis.git"
PAGE = ROOT / "results" / "site" / "index.html"

SITE_README = """# showdown2000.fun card results

Every showdown2000.fun card valued from real games: how many teams use it, its stats pooled
across every team that played it, runs added per game, and bargains vs points.

**Live page:** https://peterselj.github.io/showdown2000analysis/

Built from the analysis in [peterselj/showdownOnline](https://github.com/peterselj/showdownOnline)
(`analysis/` folder), where the method and its checks are explained.
"""


def run(*args, cwd=None):
    print("$", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    if not PAGE.exists():
        sys.exit(f"{PAGE} missing: run python scripts/build_sd2000.py first")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        run("git", "clone", "--depth", "1", REPO, str(work))
        shutil.copyfile(PAGE, work / "index.html")
        (work / "README.md").write_text(SITE_README, encoding="utf-8")
        (work / ".nojekyll").write_text("", encoding="utf-8")   # serve the files as they are
        run("git", "add", "-A", cwd=work)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=work).returncode == 0:
            print("Nothing changed; the site is already up to date.")
            return
        run("git", "commit", "-m", f"Update card results ({date.today().isoformat()})", cwd=work)
        run("git", "push", "origin", "HEAD", cwd=work)
    print("Pushed. GitHub Pages updates https://peterselj.github.io/showdown2000analysis/ in a minute or two.")


if __name__ == "__main__":
    main()
