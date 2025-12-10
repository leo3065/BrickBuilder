#!/usr/bin/env python3
import sys
from pathlib import Path

# Add src to python path if not installed as package
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from brickbuilder.main import main

if __name__ == "__main__":
    main()
