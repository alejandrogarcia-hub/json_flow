"""Main module for JSON Flow application.

This module provides example usage of the StreamJsonParser class,
demonstrating various JSON parsing scenarios including partial and
complete JSON objects.

Example:
    To run the example usage:
        $ python main.py
"""

from config import logger
from stream_parser import JSONDecodeError, StreamJsonParser

if __name__ == "__main__":
    logger.info("starting JsonFlow ...")
    parser = StreamJsonParser()
    try:
        parser.consume('""')
        logger.debug(parser.get())
    except JSONDecodeError:
        pass
    parser = StreamJsonParser()
    parser.consume('{"key":')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"key": "')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"')
    logger.debug(parser.get())
    parser.consume('key')
    logger.debug(parser.get())
    parser.consume('": ')
    parser.consume('"val')
    parser.consume('ue"}')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"key": "val')
    logger.debug(parser.get())

    parser = StreamJsonParser()
    parser.consume('{"outer": {"inner')
    logger.debug(parser.get())
    logger.info("done ...")
