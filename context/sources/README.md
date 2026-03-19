# Project Context Files

This directory contains generated Markdown documents with project source code for providing context to LLMs.

## Using merge_to_markdown.py Script

The `tools/merge_to_markdown.py` script merges the contents of multiple files into a single Markdown document according to the File Output Format rules.

### Basic Usage

```bash
# Merge specific files
python tools/merge_to_markdown.py -o context/sources/api-handlers.md src/api/handler.py src/api/middleware.py

# Merge entire directory
python tools/merge_to_markdown.py -o context/sources/full-codebase.md src/

# Add title and description
python tools/merge_to_markdown.py -o context/sources/auth-module.md -t "Authentication Module" -d "Complete authentication module code with handlers and middleware" src/auth/
```

### Automatic Naming with Date and Time

For convenience, you can use automatic file naming with current date and time:

```bash
# Create file with date and time
TIMESTAMP=$(date +"%Y-%m-%d-%H-%M-%S")
python tools/merge_to_markdown.py -o "context/sources/${TIMESTAMP}-snapshot.md" -t "Code Snapshot ($TIMESTAMP)" src/

# Short version for daily snapshots
DATE=$(date +"%Y-%m-%d")
python tools/merge_to_markdown.py -o "context/sources/${DATE}-daily.md" -t "Daily Snapshot ($DATE)" src/
```

### Advanced Examples

```bash
# Merge only specific file types
find src/ -name "*.py" -o -name "*.js" | xargs python tools/merge_to_markdown.py -o context/sources/backend.md

# Create context for specific task
python tools/merge_to_markdown.py -o context/sources/task-refactor-auth.md \
  -t "Authentication Refactoring" \
  -d "Code related to authentication module refactoring" \
  src/auth/login.py src/auth/register.py src/middleware/auth.py

# Use base directory for relative paths
python tools/merge_to_markdown.py -o context/sources/project-relative.md -b . src/ config/
```

### Reading from File List

```bash
# Create file with list of needed files
echo "src/main.py" > filelist.txt
echo "src/utils.py" >> filelist.txt
echo "config/app.json" >> filelist.txt

# Merge files from list
cat filelist.txt | xargs python tools/merge_to_markdown.py -o context/sources/custom-selection.md
```

## Output File Structure

Each generated file follows this format:

```markdown
# Project Title

Description (optional).

## Table of Contents

- [`src/main.py`](#srcmainpy)
- [`src/utils.py`](#srcutilspy)

---

### `src/main.py`

File description.

<!-- file: src/main.py -->
```python
# file code
```

### `src/utils.py`

<!-- file: src/utils.py -->
```python
# file code
```

## Naming Recommendations

- **By modules**: `api-handlers.md`, `database-models.md`, `auth.md`
- **By tasks**: `task-refactor-auth.md`, `bug-fix-memory-leak.md`
- **By date**: `2025-01-15-snapshot.md`, `2025-01-15-daily.md`
- **By versions**: `v1.2.0-api.md`, `v2.0.0-migration.md`

## Automation

For regular context creation, you can add to `package.json` or `Makefile`:

```bash
# In Makefile
context-snapshot:
    TIMESTAMP=$$(date +"%Y-%m-%d-%H-%M-%S"); \
    python tools/merge_to_markdown.py -o "context/sources/$${TIMESTAMP}-snapshot.md" -t "Snapshot ($${TIMESTAMP})" src/

context-daily:
    DATE=$$(date +"%Y-%m-%d"); \
    python tools/merge_to_markdown.py -o "context/sources/$${DATE}-daily.md" -t "Daily Snapshot ($${DATE})" src/
```

## Important Notes

- All files in this directory (except README.md) are ignored by Git
- The script automatically detects syntax highlighting language by file extension
- Binary files and system directories (`.git`, `node_modules`, `__pycache__`) are skipped
- Files with triple backticks use quadruple backticks for proper rendering

## Cleanup

To delete old context files:

```bash
# Delete files older than 7 days
find context/sources/ -name "*.md" -not -name "README.md" -mtime +7 -delete

# Keep only the last 5 files
ls -t context/sources/*.md | tail -n +6 | xargs rm -f
