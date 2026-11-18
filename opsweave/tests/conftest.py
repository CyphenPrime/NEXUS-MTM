import sys
from pathlib import Path

# Add opsweave project directory to sys.path
opsweave_dir = Path(__file__).resolve().parent.parent
if str(opsweave_dir) not in sys.path:
    sys.path.insert(0, str(opsweave_dir))
