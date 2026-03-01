"""Compatibility wrapper for `python -m rag.build_index`."""

from rag.indexing.build_index import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
