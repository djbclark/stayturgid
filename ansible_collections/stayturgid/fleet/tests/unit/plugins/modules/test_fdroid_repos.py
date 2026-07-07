"""Basic unit tests for fdroid_repos module (parse logic etc.)."""
import pytest

# Import the module under test (adjust if packaged differently)
# For collection units, often they exec or use ansible test runner.
# Here a simple functional test of the parser.

def test_parse_current_repos():
    sample = """
* IzzyOnDroid https://apt.izzysoft.de/fdroid/repo
Guardian https://guardianproject.info/fdroid/repo
"""
    # Minimal parser test; the real one is in the module
    from ansible_collections.stayturgid.fleet.plugins.modules import fdroid_repos as mod
    parsed = mod.parse_current_repos(sample)
    assert any("IzzyOnDroid" in str(p) for p in parsed)
    assert any("guardian" in str(p).lower() for p in parsed) or len(parsed) > 0
