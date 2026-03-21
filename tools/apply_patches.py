#!/usr/bin/env python3
"""
Extract files and unified diffs from LLM markdown output.

Supports two modes in a single document:
1. Full file blocks  — overwrites the file entirely
2. Patch blocks      — applies unified diff to existing file

Format in markdown:

Full file:
    <!-- file: path/to/file.ext -->
    ```lang
    full content
    ```

Patch:
    <!-- patch: path/to/file.ext -->
    ```diff
    unified diff content
    ```
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# Regex: matches <!-- file: path --> or <!-- patch: path --> followed by a fenced block
BLOCK_RE = re.compile(
    r"<!--\s*(file|patch):\s*(.+?)\s*-->\s*\n"
    r"(`{3,})(\w*)\n"
    r"(.*?)"
    r"\n\3",
    re.DOTALL,
)


def extract_blocks(markdown: str) -> list[dict]:
    """Parse markdown and extract all file/patch blocks."""
    blocks = []
    for m in BLOCK_RE.finditer(markdown):
        kind = m.group(1)       # "file" or "patch"
        path = m.group(2).strip()
        lang = m.group(4)       # language tag
        content = m.group(5)
        blocks.append({
            "kind": kind,
            "path": path,
            "lang": lang,
            "content": content,
        })
    return blocks


def write_file(root: Path, rel_path: str, content: str, dry_run: bool = False):
    """Write full file content."""
    target = root / rel_path
    if dry_run:
        print(f"  [WRITE] {rel_path} ({len(content)} bytes)")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    # Ensure trailing newline
    if content and not content.endswith("\n"):
        content += "\n"
    target.write_text(content, encoding="utf-8")
    print(f"  [WRITE] {rel_path}")


def apply_patch(root: Path, rel_path: str, diff_content: str, dry_run: bool = False):
    """Apply unified diff to an existing file."""
    target = root / rel_path
    if not target.exists():
        print(f"  [WARN]  {rel_path} does not exist — writing as new file from patch context")
        # Try to extract the '+' lines as content
        lines = []
        for line in diff_content.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(line[1:])
            elif line.startswith(" "):
                lines.append(line[1:])
        if lines:
            write_file(root, rel_path, "\n".join(lines), dry_run)
        return

    if dry_run:
        print(f"  [PATCH] {rel_path}")
        return

    # Write diff to a temp file and apply with git apply or patch
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".patch", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(diff_content)
        if not diff_content.endswith("\n"):
            tmp.write("\n")
        tmp_path = tmp.name

    # Try git apply first (smarter), fall back to patch
    result = subprocess.run(
        ["git", "apply", "--directory", str(root), tmp_path],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode == 0:
        print(f"  [PATCH] {rel_path} (git apply)")
        Path(tmp_path).unlink()
        return

    # Fallback: try patch -p1
    result = subprocess.run(
        ["patch", "-p1", "--directory", str(root), "--input", tmp_path],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print(f"  [PATCH] {rel_path} (patch -p1)")
    else:
        print(f"  [ERROR] {rel_path} — patch failed:")
        print(f"          {result.stderr.strip()}")

    Path(tmp_path).unlink()


def process(markdown_path: str, root: str = ".", dry_run: bool = False):
    """Main processing: read markdown, extract blocks, apply."""
    md_content = Path(markdown_path).read_text(encoding="utf-8")
    blocks = extract_blocks(md_content)

    if not blocks:
        print("No <!-- file: --> or <!-- patch: --> blocks found.")
        return

    root_path = Path(root).resolve()
    print(f"Project root: {root_path}")
    print(f"Found {len(blocks)} block(s):\n")

    files_written = 0
    patches_applied = 0

    for block in blocks:
        if block["kind"] == "file":
            write_file(root_path, block["path"], block["content"], dry_run)
            files_written += 1
        elif block["kind"] == "patch":
            apply_patch(root_path, block["path"], block["content"], dry_run)
            patches_applied += 1

    print(f"\nDone: {files_written} file(s) written, {patches_applied} patch(es) applied.")


def main():
    parser = argparse.ArgumentParser(
        description="Extract files and apply patches from LLM markdown output."
    )
    parser.add_argument("input", help="Path to markdown file with LLM output")
    parser.add_argument(
        "-r", "--root", default=".", help="Project root directory (default: cwd)"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Show what would be done"
    )
    args = parser.parse_args()
    process(args.input, args.root, args.dry_run)


if __name__ == "__main__":
    main()
