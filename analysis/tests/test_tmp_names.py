import glob
import os


def test_no_save_shares_a_temp_file_name_between_processes():
    """Two engine processes saving the same file at once must not share a temp file (one would rename it out from under the other)."""
    bad = []
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "filmcrafter_engine", "*.py")):
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            if '.tmp"' in line and "getpid" not in line and "def " not in line:
                bad.append(f"{os.path.basename(f)}:{i}")
    assert not bad, bad
