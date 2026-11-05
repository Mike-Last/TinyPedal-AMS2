"""
Check whether merging an upstream release changes licence terms

Usage: python check_upstream_licence.py BASE HEAD

Compares what the merge brought in (BASE = fork main before the merge, HEAD = merge result),
so the fork's own edits never trigger it. Prints a Markdown report and exits with 1
if anything licence related changed, or could not be checked, 0 otherwise.

Checked:
- licence files: LICENSE.txt, images/CC-BY-SA-4.0.txt, docs/licenses/
- the "License" section of README.md
- licence lines in the header comment of Python files
- licence files of thirdparty submodules that moved
"""

import re
import subprocess
import sys

LICENCE_PATHS = ("LICENSE.txt", "images/CC-BY-SA-4.0.txt", "docs/licenses/")
REFERENCE_HEADER = "tinypedal/__init__.py"
LICENCE_LINE = re.compile(r"licen[cs]e|GPL|SPDX", re.IGNORECASE)
SUBMODULE_LICENCE = ("License.txt", "LICENSE", "LICENSE.txt", "LICENSE.md")


def git(*args: str, cwd: str = ".", check: bool = True) -> str:
    """Run git command, return output"""
    result = subprocess.run(
        ("git", *args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def show(rev: str, path: str) -> str:
    """File content at revision, empty if missing"""
    return git("show", f"{rev}:{path}", check=False)


def readme_licence_section(text: str) -> str:
    """README "## License" section, up to next level 2 heading

    Copyright years are ignored, as upstream bumps them every year.
    """
    matched = re.search(r"^## License\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not matched:
        return ""
    return re.sub(r"\b\d{4}(?:\s*-\s*\d{4})?\b", "YEAR", matched.group(1).strip())


def header_licence_lines(text: str) -> list:
    """Licence lines in leading comment block of Python source"""
    lines = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        if LICENCE_LINE.search(line):
            lines.append(line.strip())
    return lines


def check_licence_files(base: str, head: str) -> list:
    """Changed licence files"""
    changed = git("diff", "--name-status", base, head, "--", *LICENCE_PATHS).strip()
    if not changed:
        return []
    diff = git("diff", "--stat", base, head, "--", *LICENCE_PATHS).strip()
    return [f"Licence files changed:\n\n```\n{changed}\n\n{diff}\n```"]


def check_readme(base: str, head: str) -> list:
    """Changed README licence section"""
    before = readme_licence_section(show(base, "README.md"))
    after = readme_licence_section(show(head, "README.md"))
    if before == after:
        return []
    return [f"README `License` section changed:\n\nBefore:\n\n```\n{before}\n```\n\nAfter:\n\n```\n{after}\n```"]


def check_source_headers(base: str, head: str) -> list:
    """Python files whose header licence lines differ from the standard header"""
    standard = set(header_licence_lines(show(base, REFERENCE_HEADER)))
    if not standard:
        return [f"Could not read the standard licence header from `{REFERENCE_HEADER}`."]
    files = git("diff", "--name-only", "--diff-filter=AMR", base, head, "--", "*.py").split()
    problems = []
    for path in files:
        before = header_licence_lines(show(base, path))
        after = header_licence_lines(show(head, path))
        if after == before:
            continue
        unknown = [line for line in after if line not in standard]
        removed = [line for line in before if line not in after]
        if unknown or removed:
            detail = "\n".join([f"+ {line}" for line in unknown] + [f"- {line}" for line in removed])
            problems.append(f"`{path}`:\n```\n{detail}\n```")
    if not problems:
        return []
    return ["Licence lines in source file headers changed:\n\n" + "\n\n".join(problems)]


def check_submodules(base: str, head: str) -> list:
    """Changed licence files of moved thirdparty submodules"""
    problems = []
    for line in git("diff", "--raw", base, head, "--", "thirdparty").splitlines():
        fields = line.split()
        if len(fields) < 6 or fields[1] != "160000":  # gitlink (submodule) only
            continue
        old, new, path = fields[2], fields[3], fields[5]
        try:
            for rev in (old, new):
                if git("cat-file", "-t", rev, cwd=path, check=False).strip() != "commit":
                    git("fetch", "--quiet", "origin", rev, cwd=path)
            changed = git("diff", "--name-only", old, new, "--", *SUBMODULE_LICENCE, cwd=path).strip()
        except (RuntimeError, OSError) as error:
            problems.append(f"`{path}`: could not compare licence files ({error})")
            continue
        if changed:
            problems.append(f"`{path}` ({old[:8]} -> {new[:8]}): {changed}")
    if not problems:
        return []
    return ["Licence files of thirdparty submodules changed:\n\n" + "\n".join(f"- {p}" for p in problems)]


def main() -> int:
    """Run all checks"""
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base, head = sys.argv[1], sys.argv[2]
    findings = []
    for check in (check_licence_files, check_readme, check_source_headers, check_submodules):
        try:
            findings.extend(check(base, head))
        except (RuntimeError, OSError) as error:
            findings.append(f"`{check.__name__}` could not run: {error}")
    if findings:
        print("\n\n".join(findings))
        return 1
    print(f"No licence changes between {base} and {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
