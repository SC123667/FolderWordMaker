from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from word_merge_app.app import main


if __name__ == "__main__":
    main()
