#!/usr/bin/env python3
"""
Скрипт для извлечения путей к файлам из заголовков Markdown
и добавления комментариев <!-- file: ... --> перед блоками кода.
"""

import re
import sys
import os


def process_markdown(content: str, filename: str = "<stdin>") -> tuple[str, list[str]]:
    lines = content.split('\n')
    result = []
    logs = []
    i = 0

    # Заголовок с путём: ### `some/path/file.ext`
    # Допускаем пробелы в конце, \r и т.д.
    header_pattern = re.compile(r'^(#{1,6})\s+`([^`]+)`\s*$')

    # Блок кода — допускаем пробелы/\r в конце
    code_fence_pattern = re.compile(r'^```\s*(\S*)\s*$')

    # Существующий комментарий file:
    file_comment_pattern = re.compile(r'^<!--\s*file:\s*(.+?)\s*-->$')

    while i < len(lines):
        # Убираем \r для корректного матчинга, но сохраняем оригинал
        line_raw = lines[i]
        line = line_raw.rstrip('\r')

        header_match = header_pattern.match(line)

        if header_match:
            filepath = header_match.group(2).strip()
            result.append(line_raw)
            i += 1

            if i >= len(lines):
                logs.append(
                    f"  [WARN]    {filename}:{i}  "
                    f"— заголовок '{filepath}' в конце файла, нечего обрабатывать"
                )
                break

            next_raw = lines[i]
            next_line = next_raw.rstrip('\r')
            comment_match = file_comment_pattern.match(next_line)

            if comment_match:
                existing_path = comment_match.group(1).strip()

                if existing_path == filepath:
                    logs.append(
                        f"  [SKIP]    {filename}:{i + 1}  "
                        f"— уже корректный комментарий для '{filepath}'"
                    )
                    result.append(next_raw)
                    i += 1
                else:
                    new_comment = f"<!-- file: {filepath} -->"
                    logs.append(
                        f"  [REPLACE] {filename}:{i + 1}  "
                        f"— '{existing_path}' → '{filepath}'"
                    )
                    result.append(new_comment)
                    i += 1
            else:
                code_match = code_fence_pattern.match(next_line)

                if code_match:
                    new_comment = f"<!-- file: {filepath} -->"
                    logs.append(
                        f"  [ADD]     {filename}:{i + 1}  "
                        f"— добавлен комментарий для '{filepath}'"
                    )
                    result.append(new_comment)
                    result.append(next_raw)
                    i += 1
                else:
                    # Между заголовком и кодом может быть пустая строка
                    # Проверяем через одну строку
                    if next_line.strip() == '' and (i + 1) < len(lines):
                        after_raw = lines[i + 1]
                        after_line = after_raw.rstrip('\r')
                        code_match2 = code_fence_pattern.match(after_line)

                        if code_match2:
                            new_comment = f"<!-- file: {filepath} -->"
                            logs.append(
                                f"  [ADD]     {filename}:{i + 2}  "
                                f"— добавлен комментарий для '{filepath}' "
                                f"(пустая строка между заголовком и кодом)"
                            )
                            result.append(next_raw)       # пустая строка
                            result.append(new_comment)
                            result.append(after_raw)      # ```lang
                            i += 2
                        else:
                            result.append(next_raw)
                            i += 1
                    else:
                        result.append(next_raw)
                        i += 1
        else:
            result.append(line_raw)
            i += 1

    return '\n'.join(result), logs


def process_file(filepath: str, dry_run: bool = False) -> list[str]:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content, logs = process_markdown(content, filepath)

    if not logs:
        # Диагностика: показать сколько заголовков с бэктиками вообще найдено
        header_count = len(re.findall(
            r'^#{1,6}\s+`[^`]+`', content, re.MULTILINE
        ))
        fence_count = len(re.findall(r'^```', content, re.MULTILINE))
        return [
            f"  [—]       {filepath}: изменений не требуется "
            f"(заголовков с `path`: {header_count}, блоков кода: {fence_count})"
        ]

    if content != new_content and not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return logs


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Добавляет <!-- file: path --> комментарии в Markdown файлы'
    )
    parser.add_argument('files', nargs='+', help='Пути к Markdown файлам')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Только показать изменения')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Показать отладочную информацию')

    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN (файлы не будут изменены) ===\n")

    total_logs = []

    for filepath in args.files:
        if not os.path.isfile(filepath):
            print(f"  [ERROR]   '{filepath}' не найден", file=sys.stderr)
            continue

        print(f"📄 {filepath}")

        if args.debug:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for idx, line in enumerate(lines):
                stripped = line.rstrip('\n\r')
                if re.match(r'^#{1,6}\s+`', stripped):
                    print(f"  [DEBUG]   line {idx+1}: {stripped!r}")
                    if idx + 1 < len(lines):
                        next_l = lines[idx+1].rstrip('\n\r')
                        print(f"  [DEBUG]   line {idx+2}: {next_l!r}")
                    if idx + 2 < len(lines):
                        next_l2 = lines[idx+2].rstrip('\n\r')
                        print(f"  [DEBUG]   line {idx+3}: {next_l2!r}")

        logs = process_file(filepath, dry_run=args.dry_run)
        for log in logs:
            print(log)
        total_logs.extend(logs)
        print()

    added = sum(1 for l in total_logs if '[ADD]' in l)
    replaced = sum(1 for l in total_logs if '[REPLACE]' in l)
    skipped = sum(1 for l in total_logs if '[SKIP]' in l)

    print("─" * 50)
    print(f"Итого: добавлено={added}, заменено={replaced}, пропущено={skipped}")

    if args.dry_run and (added or replaced):
        print("\n⚠  Запустите без --dry-run для применения изменений.")


if __name__ == '__main__':
    main()