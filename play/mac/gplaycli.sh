#!/usr/bin/env bash
# gplaycli wrapper: Homebrew gplaycli on Python 3.14 breaks without setuptools
# (pkg_resources). Use pip's vendored copy, then run as a module.
set -euo pipefail
PY="${GPLAYCLI_PYTHON:-python3.14}"
VENDOR="$(dirname "$("$PY" -c 'import pip, os; print(os.path.dirname(pip.__file__))')")/_vendor"
export PYTHONPATH="${VENDOR}${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m gplaycli.gplaycli "$@"
