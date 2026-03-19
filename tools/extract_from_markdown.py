#!/usr/bin/env python3
"""
Извлекает файлы из Markdown-документа, сформированного по правилам
File Output Format (маркер <!-- file: path --> перед code-блоком).

Использование:
    python extract_from_markdown.py input.md
    python extract_from_markdown.py input.md -o output_dir/
    python extract_from_markdown.py input.md --overwrite
    python extract_from_markdown.py input.md --dry-run
    cat project.md | python extract_from_markdown.py -
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedFile:
    """Один извлечённый файл."""
    path: str
    language: str
    content: str
    line_number: int  # строка маркера в исходном .md


@dataclass
class ParseResult:
    """Результат парсинга Markdown-документа."""
    files: list[ExtractedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Регулярные выражения ────────────────────────────────────────────────────

MARKER_RE = re.compile(
    r"^\s*<!--\s*file:\s*(?P<path>.+?)\s*-->\s*$"
)

FENCE_OPEN_RE = re.compile(
    r"^(?P<fence>`{3,})(?P<lang>[a-zA-Z0-9_.*+-]*)\s*$"
)


def parse_markdown(text: str) -> ParseResult:
    """
    Парсит Markdown-текст и извлекает все файлы, помеченные маркером
    <!-- file: path --> непосредственно перед code-блоком.
    """
    result = ParseResult()
    lines = text.splitlines()
    total = len(lines)
    i = 0

    while i < total:
        line = lines[i]

        marker_match = MARKER_RE.match(line)
        if not marker_match:
            i += 1
            continue

        file_path = marker_match.group("path").strip()
        marker_line = i + 1  # 1-based

        # Пропускаем пустые строки между маркером и ограждением
        j = i + 1
        while j < total and lines[j].strip() == "":
            j += 1

        if j >= total:
            result.errors.append(
                f"Строка {marker_line}: маркер для «{file_path}» — "
                f"после него нет code-блока (конец файла)"
            )
            i = j
            continue

        fence_match = FENCE_OPEN_RE.match(lines[j])
        if not fence_match:
            result.errors.append(
                f"Строка {marker_line}: маркер для «{file_path}» — "
                f"ожидался code-блок, но найдено: {lines[j]!r}"
            )
            i = j + 1
            continue

        fence_str = fence_match.group("fence")
        lang = fence_match.group("lang") or ""
        fence_len = len(fence_str)

        content_lines: list[str] = []
        k = j + 1
        found_close = False

        while k < total:
            close_match = re.match(r"^(`{" + str(fence_len) + r",})\s*$", lines[k])
            if close_match:
                found_close = True
                break
            content_lines.append(lines[k])
            k += 1

        if not found_close:
            result.errors.append(
                f"Строка {marker_line}: маркер для «{file_path}» — "
                f"не найдено закрывающее ограждение ({fence_str})"
            )
            i = k
            continue

        content = "\n".join(content_lines)
        if content and not content.endswith("\n"):
            content += "\n"
        if not content.strip():
            content = ""

        result.files.append(ExtractedFile(
            path=file_path,
            language=lang,
            content=content,
            line_number=marker_line,
        ))

        i = k + 1

    return result


def sanitize_path(raw_path: str) -> Path:
    """
    Очищает путь от опасных компонентов:
    - Убирает ведущий /
    - Запрещает .. (выход за пределы целевой директории)
    """
    cleaned = raw_path.replace("\\", "/").lstrip("/")

    parts = Path(cleaned).parts
    if ".." in parts:
        raise ValueError(
            f"Путь содержит '..', что может привести к выходу "
            f"за пределы целевой директории: {raw_path}"
        )

    if not cleaned:
        raise ValueError(f"Пустой путь после очистки: {raw_path!r}")

    return Path(cleaned)


def ask_overwrite(path: Path) -> bool:
    """
    Спрашивает пользователя, перезаписать ли существующий файл.
    Поддерживает ответы: y/yes/д/да — перезаписать, остальное — пропустить.
    """
    try:
        answer = input(f"⚠  Файл «{path}» уже существует. Перезаписать? [y/N]: ").strip().lower()
    except EOFError:
        # stdin закрыт (пайплайн) — не перезаписываем
        return False

    return answer in ("y", "yes", "д", "да")


def extract_files(
    result: ParseResult,
    output_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """
    Записывает извлечённые файлы на диск.

    Логика для существующих файлов:
    - --overwrite: перезаписать все без вопросов
    - иначе: спросить пользователя для каждого файла

    Возвращает (created, overwritten, skipped).
    """
    created = 0
    overwritten = 0
    skipped = 0

    for ef in result.files:
        try:
            rel_path = sanitize_path(ef.path)
        except ValueError as e:
            print(f"⚠  Пропущен: {e}", file=sys.stderr)
            skipped += 1
            continue

        target = output_dir / rel_path

        # Файл уже существует
        if target.exists():
            if dry_run:
                print(f"🔍 [перезапись] {target}")
                overwritten += 1
                continue

            if not overwrite:
                # Интерактивный запрос
                if not ask_overwrite(target):
                    if verbose:
                        print(f"⏭  Пропущен:    {target}")
                    skipped += 1
                    continue

            # Перезаписываем
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ef.content, encoding="utf-8")
            overwritten += 1
            if verbose:
                print(f"🔄 Перезаписан: {target}")

        else:
            # Файл не существует — создаём
            if dry_run:
                print(f"🔍 [создание]   {target}")
                created += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ef.content, encoding="utf-8")
            created += 1
            if verbose:
                print(f"✅ Создан:      {target}")

    return created, overwritten, skipped


def print_summary(
    result: ParseResult,
    created: int,
    overwritten: int,
    skipped: int,
    dry_run: bool,
) -> None:
    """Выводит итоговую сводку."""
    print()
    print("─" * 50)

    mode = " (dry-run)" if dry_run else ""
    print(f"📊 Итого{mode}:")
    print(f"   Найдено файлов в документе: {len(result.files)}")
    print(f"   Создано:       {created}")
    print(f"   Перезаписано:  {overwritten}")
    print(f"   Пропущено:     {skipped}")

    if result.errors:
        print(f"   Ошибок парсинга: {len(result.errors)}")
        print()
        print("⚠  Ошибки:")
        for err in result.errors:
            print(f"   • {err}")


def list_files(result: ParseResult) -> None:
    """Выводит список найденных файлов без извлечения."""
    if not result.files:
        print("Файлы не найдены.")
        return

    print(f"📋 Найдено {len(result.files)} файл(ов):")
    print()
    for ef in result.files:
        size = len(ef.content.encode("utf-8"))
        lang_info = f" [{ef.language}]" if ef.language else ""
        print(f"   {ef.path}{lang_info}  ({size} байт, строка {ef.line_number})")

    if result.errors:
        print()
        print(f"⚠  Ошибок парсинга: {len(result.errors)}")
        for err in result.errors:
            print(f"   • {err}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Извлекает файлы из Markdown-документа (формат File Output Format).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s project.md                        # извлечь в текущую директорию
  %(prog)s project.md -o output/             # извлечь в указанную директорию
  %(prog)s project.md --overwrite            # перезаписывать все без вопросов
  %(prog)s project.md --dry-run              # показать что будет сделано
  %(prog)s project.md --list                 # только показать список файлов
  cat project.md | %(prog)s -                # читать из stdin

Поведение при существующих файлах:
  По умолчанию скрипт спрашивает для каждого файла: перезаписать или нет.
  Флаг --overwrite перезаписывает все файлы без вопросов.
        """,
    )

    parser.add_argument(
        "input",
        help="Входной Markdown-файл (или '-' для stdin)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("."),
        help="Целевая директория для извлечения (по умолчанию — текущая)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Перезаписывать существующие файлы без подтверждения",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, какие файлы будут созданы (без записи)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Только вывести список найденных файлов",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Минимальный вывод (только запросы на перезапись, ошибки и итог)",
    )

    args = parser.parse_args()

    # Читаем входной документ
    if args.input == "-":
        text = sys.stdin.read()
    else:
        input_path = Path(args.input)
        if not input_path.is_file():
            print(f"❌ Файл не найден: {input_path}", file=sys.stderr)
            sys.exit(1)
        text = input_path.read_text(encoding="utf-8")

    # Парсим
    result = parse_markdown(text)

    if not result.files and not result.errors:
        print("❌ В документе не найдено ни одного маркера <!-- file: ... -->")
        sys.exit(1)

    # Режим списка
    if args.list_only:
        list_files(result)
        sys.exit(0)

    # Извлекаем
    created, overwritten, skipped = extract_files(
        result=result,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    # Сводка
    if not args.quiet:
        print_summary(result, created, overwritten, skipped, args.dry_run)

    if result.errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
