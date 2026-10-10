"""Container entry for manifest-checked offline execution and image preservation."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow.offline import main

if __name__ == '__main__':
    main()
