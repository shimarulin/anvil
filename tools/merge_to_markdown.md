

# Скрипт для склейки файлов в Markdown-документ

Скрипт читает указанные файлы и формирует единый `.md` документ, соблюдая все правила формата вывода проектных файлов.

### `tools/merge_to_markdown.py`

<!-- file: tools/merge_to_markdown.py -->
```python
#!/usr/bin/env python3
"""
Склеивает содержимое нескольких файлов в один Markdown-документ
согласно правилам вывода проектных файлов (File Output Format).

Использование:
    python merge_to_markdown.py -o output.md file1.py file2.js docs/README.md
    python merge_to_markdown.py -o output.md src/          # все файлы в директории
    python merge_to_markdown.py -o output.md -d "Описание проекта" file1.py file2.py
    cat filelist.txt | xargs python merge_to_markdown.py -o output.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ── Маппинг расширений → язык для подсветки синтаксиса ──────────────────────

LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".jsonc": "jsonc",
    ".json5": "json5",
    ".xml": "xml",
    ".svg": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "conf",
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "rst",
    ".txt": "text",
    ".csv": "csv",
    ".tsv": "tsv",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".bat": "batch",
    ".cmd": "batch",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".swift": "swift",
    ".m": "objectivec",
    ".mm": "objectivec",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".php": "php",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".dockerfile": "dockerfile",
    ".docker": "dockerfile",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".vue": "vue",
    ".svelte": "svelte",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".hs": "haskell",
    ".lhs": "haskell",
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".cljc": "clojure",
    ".dart": "dart",
    ".zig": "zig",
    ".nim": "nim",
    ".v": "v",
    ".sol": "solidity",
    ".tex": "latex",
    ".bib": "bibtex",
    ".makefile": "makefile",
    ".mk": "makefile",
    ".cmake": "cmake",
    ".gradle": "gradle",
    ".groovy": "groovy",
    ".diff": "diff",
    ".patch": "diff",
    ".env": "dotenv",
    ".gitignore": "gitignore",
    ".editorconfig": "editorconfig",
}

# Имена файлов без расширения → язык
FILENAME_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "Jenkinsfile": "groovy",
    "Vagrantfile": "ruby",
    "Gemfile": "ruby",
    "Rakefile": "ruby",
    "CMakeLists.txt": "cmake",
    ".gitignore": "gitignore",
    ".dockerignore": "gitignore",
    ".editorconfig": "editorconfig",
    ".env": "dotenv",
    ".env.local": "dotenv",
    ".env.example": "dotenv",
}


def detect_language(filepath: Path) -> str:
    """Определяет язык подсветки синтаксиса по расширению или имени файла."""
    name = filepath.name

    # Сначала проверяем точное имя файла
    if name in FILENAME_MAP:
        return FILENAME_MAP[name]

    # Затем по расширению
    suffix = filepath.suffix.lower()
    if suffix in LANG_MAP:
        return LANG_MAP[suffix]

    # Файлы без расширения или неизвестные
    return "text"


def content_has_triple_backticks(content: str) -> bool:
    """Проверяет, содержит ли текст тройные обратные кавычки."""
    return "```" in content


def determine_fence(content: str) -> tuple[str, str]:
    """
    Выбирает ограждение для code-блока.
    Если содержимое включает ```, используем ``````.
    Если содержимое включает и ````, используем ```````.
    И так далее — всегда на один уровень больше максимального в содержимом.
    """
    max_run = 0
    current_run = 0
    for ch in content:
        if ch == "`":
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0

    # Минимум 3 бэктика; если в содержимом есть N подряд, берём N+1
    fence_len = max(3, max_run + 1)
    fence = "`" * fence_len
    return fence, fence


def build_file_block(
    filepath: Path,
    base_dir: Path | None = None,
    description: str = "",
) -> str:
    """
    Формирует Markdown-блок для одного файла по правилам File Output Format.

    Структура:
        ### `relative/path/to/file.ext`

        Optional description.

        <!-- file: relative/path/to/file.ext -->
        ```lang
        content
        ```
    """
    # Вычисляем относительный путь
    if base_dir is not None:
        try:
            display_path = filepath.resolve().relative_to(base_dir.resolve())
        except ValueError:
            display_path = filepath
    else:
        display_path = filepath

    # Нормализуем к POSIX-стилю (прямые слэши)
    display_str = display_path.as_posix()

    # Читаем содержимое
    content = filepath.read_text(encoding="utf-8", errors="replace")

    # Убираем trailing whitespace на каждой строке и лишние переводы в конце
    lines = [line.rstrip() for line in content.splitlines()]
    content_clean = "\n".join(lines)
    # Гарантируем ровно один \n в конце, если файл не пустой
    if content_clean:
        content_clean = content_clean.rstrip("\n") + "\n"

    # Определяем язык и ограждение
    lang = detect_language(filepath)
    fence_open, fence_close = determine_fence(content_clean)

    # Собираем блок
    parts: list[str] = []
    parts.append(f"### `{display_str}`")
    parts.append("")

    if description:
        parts.append(description)
        parts.append("")

    parts.append(f"<!-- file: {display_str} -->")
    parts.append(f"{fence_open}{lang}")
    parts.append(content_clean.rstrip("\n"))
    parts.append(fence_close)

    return "\n".join(parts)


def collect_files(paths: list[str], recursive: bool = True) -> list[Path]:
    """
    Собирает список файлов из переданных путей.
    Если путь — директория, обходит её (рекурсивно или нет).
    Пропускает скрытые файлы/папки (начинающиеся с точки) и бинарные файлы.
    """
    SKIP_DIRS = {
        ".git", ".svn", ".hg", "__pycache__", "node_modules",
        ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
        "dist", "build", ".next", ".nuxt",
    }

    BINARY_EXTENSIONS = {
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".o", ".a", ".lib", ".obj",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
        ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ".sqlite", ".db",
    }

    result: list[Path] = []

    for raw_path in paths:
        p = Path(raw_path)

        if p.is_file():
            if p.suffix.lower() not in BINARY_EXTENSIONS:
                result.append(p)
        elif p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            for child in sorted(iterator):
                if child.is_file():
                    # Пропускаем скрытые и служебные директории
                    parts = child.relative_to(p).parts
                    if any(
                        part.startswith(".") or part in SKIP_DIRS
                        for part in parts[:-1]
                    ):
                        continue
                    # Пропускаем скрытые файлы
                    if child.name.startswith(".") and child.name not in FILENAME_MAP:
                        continue
                    # Пропускаем бинарные
                    if child.suffix.lower() in BINARY_EXTENSIONS:
                        continue
                    result.append(child)
        else:
            print(f"⚠  Пропущен (не найден): {raw_path}", file=sys.stderr)

    return result


def is_text_file(filepath: Path, sample_size: int = 8192) -> bool:
    """Эвристическая проверка: является ли файл текстовым."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(sample_size)
        # Если содержит нулевые байты — скорее всего бинарный
        if b"\x00" in chunk:
            return False
        return True
    except (OSError, PermissionError):
        return False


def merge_files(
    files: list[Path],
    output: Path | None,
    title: str,
    description: str,
    base_dir: Path | None,
) -> str:
    """Собирает итоговый Markdown-документ."""
    sections: list[str] = []

    # Заголовок документа
    if title:
        sections.append(f"# {title}")
        sections.append("")

    if description:
        sections.append(description)
        sections.append("")

    # Оглавление (Table of Contents)
    if len(files) > 1:
        sections.append("## Содержание")
        sections.append("")
        for filepath in files:
            if base_dir:
                try:
                    display = filepath.resolve().relative_to(base_dir.resolve())
                except ValueError:
                    display = filepath
            else:
                display = filepath
            display_str = display.as_posix()
            # Генерируем якорь: GitHub-стиль
            anchor = display_str.lower().replace("/", "").replace(".", "").replace(" ", "-")
            sections.append(f"- [`{display_str}`](#{anchor})")
        sections.append("")
        sections.append("---")
        sections.append("")

    # Блоки файлов
    for i, filepath in enumerate(files):
        if not is_text_file(filepath):
            print(f"⚠  Пропущен (бинарный): {filepath}", file=sys.stderr)
            continue

        try:
            block = build_file_block(filepath, base_dir=base_dir)
            sections.append(block)
            if i < len(files) - 1:
                sections.append("")
        except Exception as e:
            print(f"⚠  Ошибка при чтении {filepath}: {e}", file=sys.stderr)

    result = "\n".join(sections) + "\n"

    # Вывод
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result, encoding="utf-8")
        print(f"✅ Записано {len(files)} файл(ов) → {output}")
    else:
        sys.stdout.write(result)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Склеивает файлы в Markdown-документ по правилам File Output Format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s -o project.md src/main.py src/utils.py
  %(prog)s -o project.md src/
  %(prog)s -o project.md -t "My Project" -d "Исходный код проекта" src/
  %(prog)s --no-recursive -o flat.md src/
  %(prog)s src/main.py  # вывод в stdout
        """,
    )

    parser.add_argument(
        "paths",
        nargs="+",
        help="Файлы и/или директории для включения",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Путь к выходному .md файлу (по умолчанию — stdout)",
    )
    parser.add_argument(
        "-t", "--title",
        default="",
        help="Заголовок документа (H1)",
    )
    parser.add_argument(
        "-d", "--description",
        default="",
        help="Описание проекта (под заголовком)",
    )
    parser.add_argument(
        "-b", "--base-dir",
        type=Path,
        default=None,
        help="Базовая директория для вычисления относительных путей "
             "(по умолчанию — текущая)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Не обходить директории рекурсивно",
    )

    args = parser.parse_args()

    base_dir = args.base_dir or Path.cwd()
    files = collect_files(args.paths, recursive=not args.no_recursive)

    if not files:
        print("❌ Не найдено ни одного файла для обработки.", file=sys.stderr)
        sys.exit(1)

    merge_files(
        files=files,
        output=args.output,
        title=args.title,
        description=args.description,
        base_dir=base_dir,
    )


if __name__ == "__main__":
    main()
```

---

## Как использовать

```bash
# Склеить конкретные файлы
python merge_to_markdown.py -o output.md src/main.py src/utils.py config.yaml

# Склеить всю директорию рекурсивно
python merge_to_markdown.py -o output.md src/

# С заголовком и описанием
python merge_to_markdown.py -o output.md -t "My Project" -d "Backend API source code" src/

# Вывод в stdout (для пайплайнов)
python merge_to_markdown.py src/main.py | pbcopy

# Без рекурсии — только файлы верхнего уровня директории
python merge_to_markdown.py --no-recursive -o output.md src/

# Указать базовую директорию для красивых относительных путей
python merge_to_markdown.py -b /home/user/project -o output.md /home/user/project/src/
```

## Что делает скрипт

| Возможность | Описание |
|---|---|
| **Заголовок `### \`path\``** | Каждый файл получает читаемый заголовок |
| **Маркер `<!-- file: path -->`** | Ставится строго перед code-блоком для автоматической экстракции |
| **Определение языка** | 90+ расширений → правильный тег подсветки |
| **Адаптивное ограждение** | Если файл содержит `` ``` ``, автоматически используются ```` ```` ```` и т.д. |
| **Оглавление** | Генерируется при нескольких файлах |
| **Фильтрация** | Пропускает бинарные файлы, `.git`, `node_modules`, `__pycache__` и т.д. |
| **Рекурсивный обход** | Директории обходятся рекурсивно (отключается флагом `--no-recursive`) |
