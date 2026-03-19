# Output Directory for LLM Response Processing

This directory contains processed markdown files with LLM responses that follow the **File Output Format** rules defined in `../rules/01.00_Markdown_format.md`.

## Overview

The markdown files in this directory contain structured output from LLM interactions, formatted to enable automated file extraction using the `extract_from_markdown.py` tool.

## File Format

Each markdown file follows these rules:

### File Structure

````markdown
### `path/to/file.ext`

Optional description or notes.

<!-- file: path/to/file.ext -->
```lang
content
```
````

### Key Elements
- **Heading**: `### \`path/to/file.ext`` - Provides human-readable navigation
- **HTML Marker**: `<!-- file: path/to/file.ext -->` - Enables automated extraction (placed immediately before code block)
- **Code Block**: Uses appropriate language tag for syntax highlighting
- **Description**: Optional context between heading and code block

### Special Cases
- Files containing triple backticks use quadruple backticks for proper rendering
- Code blocks without the `<!-- file: -->` marker are treated as illustrative snippets and ignored by the extractor

## Processing Workflow

1. **LLM generates responses** following the File Output Format rules
2. **Responses are saved** as markdown files in this directory
3. **Automated extraction** using `@/tools/extract_from_markdown.py` processes the files
4. **Embedded files** are extracted to their specified paths

## Extraction Tool Usage

Run in the project root:

```bash
# Extract all files to current directory
python tools/extract_from_markdown.py context/output/response.md

# Extract to specific directory
python tools/extract_from_markdown.py context/output/response.md -o ./extracted/

# Overwrite existing files
python tools/extract_from_markdown.py context/output/response.md --overwrite

# Dry run (show what would be extracted)
python tools/extract_from_markdown.py context/output/response.md --dry-run

# List files only
python tools/extract_from_markdown.py context/output/response.md --list
```

## Features

- **Automated directory creation**: Extracts create necessary directory structures
- **Path traversal protection**: Prevents extraction outside target directories
- **Error reporting**: Identifies malformed markers and incomplete code blocks
- **Flexible input**: Supports files or stdin
- **Dry run mode**: Preview extraction without writing to disk

## File Organization

- All markdown files in this directory are ignored by Git (see `.gitignore`)
- Only `README.md` is tracked in version control
- Extracted files are typically placed outside this directory structure

## Safety Notes

- The extraction tool validates paths and prevents directory traversal attacks
- Existing files are preserved by default (use `--overwrite` to replace)
- The tool reports parsing errors for malformed markdown structures

For more details, refer to:
- [@/context/rules/01.00_Markdown_format.md](../rules/01.00_Markdown_format.md) - Format specification
- [@/tools/extract_from_markdown.md](../../tools/extract_from_markdown.md) - Tool documentation
