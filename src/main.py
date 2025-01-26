"""Main module for JSON Flow application.

This module provides example usage of the StreamJsonParser class,
demonstrating various JSON parsing scenarios including partial and
complete JSON objects.

Example:
    To run the example usage:
        $ python main.py
"""

from config import logger
from stream_parser import StreamJsonParser

if __name__ == "__main__":
    logger.info("starting JsonFlow ...")
    parser = StreamJsonParser()
    pass
