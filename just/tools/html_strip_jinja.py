#!/usr/bin/env python3
"""Strip Jinja2 template syntax from HTML for validation by html-validate.

Reads stdin or a file, removes Jinja {# #}, {{ }}, {% %} blocks,
and prints clean HTML to stdout. Falls back to original text for
non-Jinja files.

Usage:
  python3 html_strip_jinja.py < input.html
  python3 html_strip_jinja.py input.html > output.html
"""

import re
import sys
from pathlib import Path


def strip_jinja(text: str) -> str:
    text = re.sub(r"{#.*?#}", "", text, flags=re.DOTALL)
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\{%.*?%\}", "", text, flags=re.DOTALL)
    return text


def main() -> int:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    sys.stdout.write(strip_jinja(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
