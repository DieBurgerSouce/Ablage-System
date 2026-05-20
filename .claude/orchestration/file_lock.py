"""
Cross-platform File Locking Utility.

Provides thread-safe file locking that works on both Unix/Linux and Windows:
- Unix/Linux/macOS: Uses fcntl.flock
- Windows: Uses msvcrt.locking
"""

import os
import sys
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
import logging

logger = logging.getLogger("orchestration.file_lock")

# Platform detection and imports
if sys.platform == 'win32':
    # Windows file locking
    import msvcrt
    LOCK_MODE = 'windows'
else:
    # Unix/Linux/macOS file locking
    import fcntl
    LOCK_MODE = 'unix'


@contextmanager
def file_lock(file_path: Path, mode: str = 'r') -> Generator[None, None, None]:
    """
    Cross-platform context manager for file locking (thread-safe file access).

    Args:
        file_path: Path to file to lock
        mode: File open mode ('r' or 'w')

    Yields:
        None

    Example:
        >>> with file_lock(cache_file, 'w'):
        ...     # Safe to write to file
        ...     pass
    """
    lock_path = file_path.with_suffix('.lock')
    lock_file = None

    try:
        # Create lock file
        lock_file = open(lock_path, 'w')

        if LOCK_MODE == 'unix':
            # Unix/Linux: Use fcntl.flock for exclusive lock
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        else:
            # Windows: Use msvcrt.locking for exclusive lock
            # Lock 1 byte at the start of the file
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

        yield

    finally:
        if lock_file:
            # Release lock
            try:
                if LOCK_MODE == 'unix':
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                else:
                    # Windows: Unlock the byte
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception as e:
                logger.warning("lock_release_failed", error=str(e))

            lock_file.close()

        # Clean up lock file
        if lock_path.exists():
            try:
                lock_path.unlink()
            except OSError as e:
                logger.debug("lock_file_cleanup_failed", error=str(e))
                pass  # Ignore if already deleted


def get_lock_mode() -> str:
    """
    Get current platform lock mode.

    Returns:
        'unix' or 'windows'
    """
    return LOCK_MODE
