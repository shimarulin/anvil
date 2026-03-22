#!/usr/bin/env bash
# settools.sh — load project commands
# Usage: source settools.sh
# All commands work from any directory

# === Determine path to project folder (where this script is located) ===
# Works in both bash and zsh
if [[ -n "${ZSH_VERSION:-}" ]]; then
    THIS_DIR="${(%):-%x}"
elif [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    THIS_DIR="${BASH_SOURCE[0]}"
else
    THIS_DIR="${0}"
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$THIS_DIR")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/context/output"

# === Create output file: mkout "title" ===
mkout() {
    local title="${1:-output}"
    local clean_title=$(echo "$title" | sed 's/[#:*?"<>|]/_/g; s/ /_/g; s/[^a-zA-Z0-9._-]/_/g; s/__*/_/g; s/^_*//; s/_*$//')
    local filename="$OUTPUT_DIR/$(date +'%Y-%m-%d_%H-%M-%S')_${clean_title}.md"

    local clipboard_content=""

    # Try different ways to read clipboard
    if command -v pbpaste >/dev/null 2>&1; then
        # macOS
        clipboard_content=$(pbpaste 2>/dev/null) || clipboard_content=""
    elif command -v wl-paste >/dev/null 2>&1; then
        # Wayland
        clipboard_content=$(wl-paste -n 2>/dev/null) || clipboard_content=""
    elif command -v xclip >/dev/null 2>&1; then
        # X11
        clipboard_content=$(xclip -selection clipboard -o 2>/dev/null) || clipboard_content=""
    elif command -v xsel >/dev/null 2>&1; then
        # X11 (alternative)
        clipboard_content=$(xsel --clipboard --output 2>/dev/null) || clipboard_content=""
    fi

    # Create file
    touch "$filename" || { echo "❌ Cannot create file: $filename" >&2; return 1; }

    # Add text from clipboard if available
    if [[ -n "$clipboard_content" ]]; then
        printf '%s' "$clipboard_content" >> "$filename"
        echo "📋 Text from clipboard added (raw, no escape interpretation)"
    else
        echo "📁 File is empty (clipboard is empty or unavailable)" > "$filename"
    fi

    echo "✅ Record created: $(basename "$filename")"
    echo "   Full path: $filename"
}

# === Clear output: clrout ===
clrout() {
    local files=("$OUTPUT_DIR"/*.md)
    if [[ -e "${files[0]}" ]] || [[ -L "${files[0]}" ]]; then
        rm -f "${files[@]}"
        echo "🗑 Cleared: $(basename "$OUTPUT_DIR")"
    else
        echo "📁 No .md files to remove in $(basename "$OUTPUT_DIR")"
    fi
}

# === List output: lsout ===
lsout() {
    if compgen -G "$OUTPUT_DIR/*.md" > /dev/null; then
        printf '%s\n' "$OUTPUT_DIR"/*.md | xargs -n1 basename
    else
        echo "📁 No files in $(basename "$OUTPUT_DIR")"
    fi
}
