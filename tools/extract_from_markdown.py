#!/usr/bin/env python3
"""
Извлекает файлы и применяет патчи из Markdown-документа,
сформированного по правилам File Output Format
(маркеры <!-- file: path --> и <!-- patch: path --> перед code-блоками).

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
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


# ── Константы ─────────────────────────────────────────────────────────────

SUBPROCESS_TIMEOUT = 30
FUZZ_RANGE = 50  # ±N строк при поиске контекста хенка


# ── Данные ────────────────────────────────────────────────────────────────


@dataclass
class ExtractedFile:
    """Один извлечённый файл или патч."""

    path: str
    language: str
    content: str
    line_number: int
    kind: str = "file"


@dataclass
class ParseResult:
    """Результат парсинга Markdown-документа."""

    files: list[ExtractedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── Регулярные выражения ──────────────────────────────────────────────────

MARKER_RE = re.compile(
    r"^\s*<!--\s*(?P<kind>file|patch):\s*(?P<path>.+?)\s*-->\s*$"
)

FENCE_OPEN_RE = re.compile(
    r"^(?P<fence>`{3,})(?P<lang>\w*)\s*$"
)

HUNK_HEADER_RE = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"
)


# ── Парсер Markdown ───────────────────────────────────────────────────────


def parse_markdown(text: str) -> ParseResult:
    """
    Парсит Markdown-текст и извлекает все файлы/патчи.
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
        kind = marker_match.group("kind").strip()
        marker_line = i + 1

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
        close_re = re.compile(r"^`{" + str(fence_len) + r",}\s*$")

        while k < total:
            if close_re.match(lines[k]):
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

        if kind == "patch" and lang and lang != "diff":
            result.errors.append(
                f"Строка {marker_line}: patch для «{file_path}» — "
                f"ожидался язык 'diff', но указан '{lang}'"
            )

        result.files.append(
            ExtractedFile(
                path=file_path,
                language=lang,
                content=content,
                line_number=marker_line,
                kind=kind,
            )
        )

        i = k + 1

    return result


# ── Безопасность путей ────────────────────────────────────────────────────


def sanitize_path(raw_path: str) -> Path:
    cleaned = raw_path.replace("\\", "/").lstrip("/")
    parts = Path(cleaned).parts
    if ".." in parts:
        raise ValueError(
            f"Путь содержит '..': {raw_path}"
        )
    if not cleaned:
        raise ValueError(f"Пустой путь после очистки: {raw_path!r}")
    return Path(cleaned)


# ── Интерактивный запрос ──────────────────────────────────────────────────


def ask_overwrite(path: Path) -> bool:
    try:
        answer = (
            input(
                f"⚠  Файл «{path}» уже существует. Перезаписать? [y/N]: "
            )
            .strip()
            .lower()
        )
    except EOFError:
        return False
    return answer in ("y", "yes", "д", "да")


# ── Парсер unified diff ──────────────────────────────────────────────────


@dataclass
class DiffHunk:
    """Один хенк unified diff."""

    old_start: int  # 1-based
    old_count: int
    new_start: int
    new_count: int
    # Каждая запись: (тип, содержимое)
    # тип: " " = контекст, "-" = удаление, "+" = добавление
    lines: list[tuple[str, str]] = field(default_factory=list)


def parse_unified_diff(diff_content: str) -> list[DiffHunk]:
    """
    Парсит unified diff в список хенков.
    Устойчив к типичным проблемам LLM-сгенерированных diff'ов:
    - контекстные строки без ведущего пробела
    - пустые строки без пробела-префикса
    - текст после @@ ... @@ (имена функций/секций)
    """
    diff_lines = diff_content.splitlines()
    hunks: list[DiffHunk] = []
    idx = 0

    # Пропускаем всё до первого @@ (заголовки ---, +++, и прочее)
    while idx < len(diff_lines):
        if HUNK_HEADER_RE.match(diff_lines[idx]):
            break
        idx += 1

    while idx < len(diff_lines):
        hunk_match = HUNK_HEADER_RE.match(diff_lines[idx])
        if not hunk_match:
            idx += 1
            continue

        old_start = int(hunk_match.group(1))
        old_count = (
            int(hunk_match.group(2))
            if hunk_match.group(2) is not None
            else 1
        )
        new_start = int(hunk_match.group(3))
        new_count = (
            int(hunk_match.group(4))
            if hunk_match.group(4) is not None
            else 1
        )

        hunk = DiffHunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
        )

        idx += 1

        # Счётчики для валидации: сколько строк old/new мы уже набрали
        old_seen = 0
        new_seen = 0

        while idx < len(diff_lines):
            dline = diff_lines[idx]

            # Следующий хенк — прекращаем текущий
            if HUNK_HEADER_RE.match(dline):
                break

            if dline.startswith("-") and not dline.startswith("---"):
                hunk.lines.append(("-", dline[1:]))
                old_seen += 1
            elif dline.startswith("+") and not dline.startswith("+++"):
                hunk.lines.append(("+", dline[1:]))
                new_seen += 1
            elif dline.startswith(" "):
                hunk.lines.append((" ", dline[1:]))
                old_seen += 1
                new_seen += 1
            elif dline.startswith("\\"):
                # "\ No newline at end of file"
                idx += 1
                continue
            elif dline.startswith("---") or dline.startswith("+++"):
                # Заголовки файла внутри diff — пропускаем
                idx += 1
                continue
            else:
                # Строка без стандартного diff-префикса.
                # Типичная ошибка LLM: контекстная строка без пробела.
                # Также пустая строка "" в diff = пустая контекстная строка.
                if dline == "":
                    hunk.lines.append((" ", ""))
                else:
                    hunk.lines.append((" ", dline))
                old_seen += 1
                new_seen += 1

            idx += 1

        hunks.append(hunk)

    return hunks


# ── Применение патчей ─────────────────────────────────────────────────────


def _normalize(s: str) -> str:
    """Нормализует строку для сравнения: убирает trailing whitespace."""
    return s.rstrip()


def _try_apply_hunk(
    result_lines: list[str],
    hunk: DiffHunk,
    verbose: bool = False,
) -> bool:
    """
    Применяет один хенк к списку строк (in-place).
    Возвращает True при успехе.

    Строки в result_lines НЕ содержат \\n (splitlines).
    """
    # Собираем старые и новые строки из хенка
    old_lines: list[str] = []
    new_lines: list[str] = []

    for typ, content in hunk.lines:
        if typ == " ":
            old_lines.append(content)
            new_lines.append(content)
        elif typ == "-":
            old_lines.append(content)
        elif typ == "+":
            new_lines.append(content)

    if not old_lines:
        # Чистая вставка — вставляем перед old_start
        pos = hunk.old_start - 1
        if pos < 0:
            pos = 0
        if pos > len(result_lines):
            pos = len(result_lines)
        for idx, nl in enumerate(new_lines):
            result_lines.insert(pos + idx, nl)
        return True

    # Ищем позицию old_lines в result_lines
    nominal_pos = hunk.old_start - 1  # 0-based

    def match_at(pos: int) -> bool:
        if pos < 0 or pos + len(old_lines) > len(result_lines):
            return False
        return all(
            _normalize(result_lines[pos + i]) == _normalize(old_lines[i])
            for i in range(len(old_lines))
        )

    # Сначала пробуем номинальную позицию
    found_pos: int | None = None

    if match_at(nominal_pos):
        found_pos = nominal_pos
    else:
        # Fuzz: ищем в расширяющемся радиусе
        for offset in range(1, FUZZ_RANGE + 1):
            if match_at(nominal_pos - offset):
                found_pos = nominal_pos - offset
                break
            if match_at(nominal_pos + offset):
                found_pos = nominal_pos + offset
                break

    if found_pos is None:
        if verbose:
            print(
                f"    ⚠  Хенк @@ -{hunk.old_start},{hunk.old_count} "
                f"+{hunk.new_start},{hunk.new_count} @@: "
                f"контекст не найден",
                file=sys.stderr,
            )
            print(
                f"       Ожидалось (первые 3 строки):",
                file=sys.stderr,
            )
            for ol in old_lines[:3]:
                print(f"         {ol!r}", file=sys.stderr)
            actual_start = max(0, nominal_pos)
            actual_end = min(
                len(result_lines), actual_start + len(old_lines)
            )
            actual = result_lines[actual_start:actual_end]
            print(
                f"       Реально на позиции {nominal_pos} "
                f"(первые 3 строки):",
                file=sys.stderr,
            )
            for al in actual[:3]:
                print(f"         {al!r}", file=sys.stderr)
        return False

    # Заменяем
    result_lines[found_pos: found_pos + len(old_lines)] = new_lines
    return True


def _apply_patch_internal(
    original: str,
    diff_content: str,
    file_path: str,
    verbose: bool = False,
) -> str | None:
    """
    Встроенное применение unified diff.
    Возвращает новое содержимое файла или None при ошибке.
    """
    hunks = parse_unified_diff(diff_content)
    if not hunks:
        if verbose:
            print(
                f"    ⚠  Не удалось распарсить ни одного хенка из diff",
                file=sys.stderr,
            )
        return None

    # Работаем со строками без \n (splitlines)
    result_lines = original.splitlines()

    # Применяем хенки в обратном порядке (от конца файла к началу),
    # чтобы смещения от предыдущих хенков не влияли
    for hunk in reversed(hunks):
        if not _try_apply_hunk(result_lines, hunk, verbose=verbose):
            return None

    # Собираем результат, сохраняя финальный \n
    result = "\n".join(result_lines)
    if original.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def _extract_new_file_from_diff(diff_content: str) -> str | None:
    """
    Извлекает содержимое нового файла из '+' строк патча.
    """
    lines = []
    for line in diff_content.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif line.startswith(" "):
            lines.append(line[1:])
    if not lines:
        return None
    content = "\n".join(lines)
    if content and not content.endswith("\n"):
        content += "\n"
    return content


def _run_subprocess(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = SUBPROCESS_TIMEOUT,
) -> subprocess.CompletedProcess[str] | None:
    """
    Запускает команду с таймаутом и закрытым stdin.
    Возвращает None если команда не найдена или таймаут.
    """
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def apply_patch_to_file(
    target: Path,
    diff_content: str,
    file_path: str,
    output_dir: Path,
    dry_run: bool = False,
    verbose: bool = True,
) -> bool:
    """
    Применяет unified diff к файлу.

    Стратегия:
    1. Встроенный Python-парсер
    2. git apply
    3. patch -p1

    Если файл не существует — создаёт из '+' строк.
    """
    # ── Файл не существует — создаём из '+' строк ─────────────────────
    if not target.exists():
        content = _extract_new_file_from_diff(diff_content)
        if content is None:
            if verbose:
                print(
                    f"    ⚠  Файл не существует и нет '+' строк в патче",
                    file=sys.stderr,
                )
            return False
        if dry_run:
            if verbose:
                print(f"🔍 [создание из патча] {target}")
            return True
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if verbose:
            print(f"✅ Создан из патча: {target}")
        return True

    if dry_run:
        if verbose:
            print(f"🔍 [патч]       {target}")
        return True

    original = target.read_text(encoding="utf-8")

    # ── Стратегия 1: встроенный парсер ────────────────────────────────
    result = _apply_patch_internal(
        original, diff_content, file_path, verbose=verbose
    )
    if result is not None:
        target.write_text(result, encoding="utf-8")
        if verbose:
            print(f"🩹 Патч применён: {target} (встроенный)")
        return True

    # ── Стратегия 2: git apply ────────────────────────────────────────
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(diff_content)
            if not diff_content.endswith("\n"):
                tmp.write("\n")
            tmp_path = Path(tmp.name)

        proc = _run_subprocess(
            ["git", "apply", str(tmp_path)],
            cwd=str(output_dir),
        )
        if proc is not None and proc.returncode == 0:
            if verbose:
                print(f"🩹 Патч применён: {target} (git apply)")
            return True
        elif proc is not None and verbose:
            stderr = proc.stderr.strip()
            if stderr:
                print(f"    ⚠  git apply: {stderr}", file=sys.stderr)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    # ── Стратегия 3: patch ────────────────────────────────────────────
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(diff_content)
            if not diff_content.endswith("\n"):
                tmp.write("\n")
            tmp_path = Path(tmp.name)

        proc = _run_subprocess(
            ["patch", "-p1", "-i", str(tmp_path)],
            cwd=str(output_dir),
        )
        if proc is not None and proc.returncode == 0:
            if verbose:
                print(f"🩹 Патч применён: {target} (patch)")
            return True
        elif proc is not None and verbose:
            stderr = proc.stderr.strip()
            if stderr:
                print(f"    ⚠  patch: {stderr}", file=sys.stderr)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    return False


# ── Извлечение на диск ────────────────────────────────────────────────────


def extract_files(
    result: ParseResult,
    output_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
) -> tuple[int, int, int, int]:
    """
    Записывает файлы на диск и применяет патчи.
    Возвращает ``(created, overwritten, patched, skipped)``.
    """
    created = 0
    overwritten = 0
    patched = 0
    skipped = 0

    for ef in result.files:
        try:
            rel_path = sanitize_path(ef.path)
        except ValueError as e:
            print(f"⚠  Пропущен: {e}", file=sys.stderr)
            skipped += 1
            continue

        target = output_dir / rel_path

        # ── Патч ──────────────────────────────────────────────────────
        if ef.kind == "patch":
            success = apply_patch_to_file(
                target=target,
                diff_content=ef.content,
                file_path=ef.path,
                output_dir=output_dir,
                dry_run=dry_run,
                verbose=verbose,
            )
            if success:
                patched += 1
            else:
                if verbose:
                    print(
                        f"❌ Не удалось применить патч: {target} "
                        f"(строка {ef.line_number})",
                        file=sys.stderr,
                    )
                skipped += 1
            continue

        # ── Полный файл ──────────────────────────────────────────────
        if target.exists():
            if dry_run:
                print(f"🔍 [перезапись] {target}")
                overwritten += 1
                continue

            if not overwrite:
                if not ask_overwrite(target):
                    if verbose:
                        print(f"⏭  Пропущен:    {target}")
                    skipped += 1
                    continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ef.content, encoding="utf-8")
            overwritten += 1
            if verbose:
                print(f"🔄 Перезаписан: {target}")

        else:
            if dry_run:
                print(f"🔍 [создание]   {target}")
                created += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ef.content, encoding="utf-8")
            created += 1
            if verbose:
                print(f"✅ Создан:      {target}")

    return created, overwritten, patched, skipped


# ── Вывод ─────────────────────────────────────────────────────────────────


def print_summary(
    result: ParseResult,
    created: int,
    overwritten: int,
    patched: int,
    skipped: int,
    dry_run: bool,
) -> None:
    print()
    print("─" * 50)

    mode = " (dry-run)" if dry_run else ""
    file_count = sum(1 for f in result.files if f.kind == "file")
    patch_count = sum(1 for f in result.files if f.kind == "patch")

    print(f"📊 Итого{mode}:")
    print(f"   Найдено в документе: {len(result.files)}")
    print(f"     файлов:    {file_count}")
    print(f"     патчей:    {patch_count}")
    print(f"   Создано:       {created}")
    print(f"   Перезаписано:  {overwritten}")
    print(f"   Патчей применено: {patched}")
    print(f"   Пропущено:     {skipped}")

    if result.errors:
        print(f"   Ошибок парсинга: {len(result.errors)}")
        print()
        print("⚠  Ошибки:")
        for err in result.errors:
            print(f"   • {err}")


def list_files(result: ParseResult) -> None:
    if not result.files:
        print("Файлы не найдены.")
        return

    file_count = sum(1 for f in result.files if f.kind == "file")
    patch_count = sum(1 for f in result.files if f.kind == "patch")

    print(f"📋 Найдено {len(result.files)} блок(ов):")
    print(f"   файлов: {file_count}, патчей: {patch_count}")
    print()
    for ef in result.files:
        size = len(ef.content.encode("utf-8"))
        lang_info = f" [{ef.language}]" if ef.language else ""
        kind_icon = "📄" if ef.kind == "file" else "🩹"
        kind_label = ef.kind.upper()
        print(
            f"   {kind_icon} [{kind_label}] {ef.path}{lang_info}"
            f"  ({size} байт, строка {ef.line_number})"
        )

    if result.errors:
        print()
        print(f"⚠  Ошибок парсинга: {len(result.errors)}")
        for err in result.errors:
            print(f"   • {err}")


# ── CLI ───────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Извлекает файлы и применяет патчи из Markdown-документа "
            "(формат File Output Format)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Примеры:
  %(prog)s project.md                # извлечь в текущую директорию
  %(prog)s project.md -o output/     # извлечь в указанную директорию
  %(prog)s project.md --overwrite    # перезаписывать все без вопросов
  %(prog)s project.md --dry-run      # показать что будет сделано
  %(prog)s project.md --list         # только показать список файлов
  cat project.md | %(prog)s -        # читать из stdin

Поддерживаемые маркеры:
  <!-- file: path/to/file -->   — полный файл (перезапись)
  <!-- patch: path/to/file -->  — unified diff (частичное обновление)

Применение патчей (по приоритету):
  1. Встроенный Python-парсер unified diff
  2. git apply
  3. patch -p1
  Если файл не существует — создаётся из '+' строк патча.
""",
    )

    parser.add_argument(
        "input",
        help="Входной Markdown-файл (или '-' для stdin)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Целевая директория (по умолчанию — текущая)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Перезаписывать существующие файлы без подтверждения",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать что будет сделано (без записи)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="Только вывести список найденных файлов и патчей",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Минимальный вывод",
    )

    args = parser.parse_args()

    # ── Читаем входной документ ───────────────────────────────────────
    if args.input == "-":
        text = sys.stdin.read()
    else:
        input_path = Path(args.input)
        if not input_path.is_file():
            print(f"❌ Файл не найден: {input_path}", file=sys.stderr)
            sys.exit(1)
        text = input_path.read_text(encoding="utf-8")

    # ── Парсим ────────────────────────────────────────────────────────
    result = parse_markdown(text)

    if not result.files and not result.errors:
        print(
            "❌ В документе не найдено ни одного маркера "
            "<!-- file: ... --> или <!-- patch: ... -->"
        )
        sys.exit(1)

    # ── Режим списка ──────────────────────────────────────────────────
    if args.list_only:
        list_files(result)
        sys.exit(0)

    # ── Извлекаем ─────────────────────────────────────────────────────
    created, overwritten, patched, skipped = extract_files(
        result=result,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    # ── Сводка ────────────────────────────────────────────────────────
    if not args.quiet:
        print_summary(
            result, created, overwritten, patched, skipped, args.dry_run
        )

    if result.errors:
        sys.exit(2)


if __name__ == "__main__":
    main()
