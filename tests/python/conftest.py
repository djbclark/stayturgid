"""Shared pytest paths for the script-twin tests (tests/python/).

The Ansible *module* (termux_pkg) is tested inside the collection via
`ansible-test units`; these plain-pytest tests cover the Termux Python
script twins under termux/py/.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "termux", "py"))
