# Скрипт извлечения файлов из Markdown-документа

Обратная операция: парсит Markdown, находит маркеры `<!-- file: path -->` и извлекает содержимое code-блоков в файловую систему.

### `tools/extract_from_markdown.py`

<!-- file: tools/extract_from_markdown.py -->
```python
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

# Маркер <!-- file: some/path.ext -->
# Допускаем пробелы внутри комментария и необязательный / в начале пути
MARKER_RE = re.compile(
    r"^\s*<!--\s*file:\s*(?P<path>.+?)\s*-->\s*$"
)

# Открывающее ограждение: 3+ бэктиков, опционально язык
FENCE_OPEN_RE = re.compile(
    r"^(?P<fence>`{3,})(?P<lang>[a-zA-Z0-9_.*+-]*)\s*$"
)


def parse_markdown(text: str) -> ParseResult:
    """
    Парсит Markdown-текст и извлекает все файлы, помеченные маркером
    <!-- file: path --> непосредственно перед code-блоком.

    Алгоритм:
    1. Ищем строку с маркером <!-- file: path -->
    2. Следующая непустая строка должна быть открывающим ограждением (```)
    3. Читаем содержимое до закрывающего ограждения той же длины
    4. Сохраняем результат
    """
    result = ParseResult()
    lines = text.splitlines()
    total = len(lines)
    i = 0

    while i < total:
        line = lines[i]

        # Ищем маркер
        marker_match = MARKER_RE.match(line)
        if not marker_match:
            i += 1
            continue

        file_path = marker_match.group("path").strip()
        marker_line = i + 1  # номер строки (1-based)

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

        # Проверяем открывающее ограждение
        fence_match = FENCE_OPEN_RE.match(lines[j])
        if not fence_match:
            result.errors.append(
                f"Строка {marker_line}: маркер для «{file_path}» — "
                f"ожидался code-блок, но найдено: {lines[j]!r}"
            )
            i = j + 1
            continue

        fence_str = fence_match.group("fence")  # например ``` или ````
        lang = fence_match.group("lang") or ""
        fence_len = len(fence_str)

        # Читаем содержимое до закрывающего ограждения
        content_lines: list[str] = []
        k = j + 1
        found_close = False

        while k < total:
            # Закрывающее ограждение: такое же кол-во бэктиков (или больше), ничего после
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

        # Собираем содержимое
        content = "\n".join(content_lines)
        # Гарантируем завершающий перевод строки (как в реальных файлах)
        if content and not content.endswith("\n"):
            content += "\n"
        # Пустой файл — пустая строка
        if not content.strip():
            content = ""

        result.files.append(ExtractedFile(
            path=file_path,
            language=lang,
            content=content,
            line_number=marker_line,
        ))

        # Переходим за закрывающее ограждение
        i = k + 1

    return result


def sanitize_path(raw_path: str) -> Path:
    """
    Очищает путь от опасных компонентов:
    - Убирает ведущий /
    - Запрещает .. (выход за пределы целевой директории)
    - Нормализует разделители
    """
    # Нормализуем разделители
    cleaned = raw_path.replace("\\", "/")

    # Убираем ведущий слэш
    cleaned = cleaned.lstrip("/")

    # Проверяем на path traversal
    parts = Path(cleaned).parts
    if ".." in parts:
        raise ValueError(
            f"Путь содержит '..', что может привести к выходу "
            f"за пределы целевой директории: {raw_path}"
        )

    if not cleaned:
        raise ValueError(f"Пустой путь после очистки: {raw_path!r}")

    return Path(cleaned)


def extract_files(
    result: ParseResult,
    output_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """
    Записывает извлечённые файлы на диск.

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

        # Проверяем существование
        if target.exists() and not overwrite:
            if verbose:
                print(f"⏭  Пропущен (существует): {target}")
            skipped += 1
            continue

        if dry_run:
            status = "перезапись" if target.exists() else "создание"
            print(f"🔍 [{status}] {target}")
            if target.exists():
                overwritten += 1
            else:
                created += 1
            continue

        # Создаём директории
        target.parent.mkdir(parents=True, exist_ok=True)

        # Записываем
        is_overwrite = target.exists()
        target.write_text(ef.content, encoding="utf-8")

        if is_overwrite:
            overwritten += 1
            if verbose:
                print(f"🔄 Перезаписан: {target}")
        else:
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
  %(prog)s project.md --overwrite            # перезаписывать существующие
  %(prog)s project.md --dry-run              # показать что будет сделано
  %(prog)s project.md --list                 # только показать список файлов
  cat project.md | %(prog)s -                # читать из stdin
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
        help="Перезаписывать существующие файлы",
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
        help="Минимальный вывод (только ошибки и итог)",
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

    # Код возврата
    if result.errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
```

---

## Как использовать

```bash
# Извлечь все файлы в текущую директорию
python extract_from_markdown.py project.md

# Извлечь в конкретную папку
python extract_from_markdown.py project.md -o ./extracted/

# Перезаписать существующие файлы
python extract_from_markdown.py project.md -o ./project/ --overwrite

# Посмотреть, что будет извлечено (без записи на диск)
python extract_from_markdown.py project.md --dry-run

# Только список файлов в документе
python extract_from_markdown.py project.md --list

# Из stdin (например, из буфера обмена)
pbpaste | python extract_from_markdown.py - -o ./output/

# Тихий режим — только ошибки и итог
python extract_from_markdown.py project.md -o ./out/ --overwrite -q
```

## Что делает скрипт

| Возможность | Описание |
|---|---|
| **Парсинг маркеров** | Ищет `<!-- file: path -->` и извлекает следующий за ним code-блок |
| **Адаптивные ограждения** | Корректно обрабатывает ```` ```` ````, `` ````` `` и т.д. |
| **Создание каталогов** | Автоматически создаёт всю цепочку директорий (`mkdir -p`) |
| **Перезапись** | Флаг `--overwrite` разрешает перезапись; без него существующие файлы пропускаются |
| **Защита от path traversal** | Блокирует `..` в путях и ведущий `/` |
| **Dry-run** | Показывает план действий без записи на диск |
| **Чтение из stdin** | Поддерживает `-` как входной файл |
| **Отчёт об ошибках** | Сообщает о битых маркерах, незакрытых блоках и т.д. |
