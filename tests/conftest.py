import sys
from pathlib import Path

# Make the Version 2 modules importable from the tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "v2"))
