import os
import sys
import tempfile
from pathlib import Path

# Keep tests away from the real user folders. Must happen before airag is imported.
os.environ["AIRAG_DATA_DIR"] = tempfile.mkdtemp(prefix="airag-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
