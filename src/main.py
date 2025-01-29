"""Main module for JSON Flow application.

This module provides example usage of the StreamJsonParser class,
demonstrating various JSON parsing scenarios including partial and
complete JSON objects.

Example:
    To run the example usage:
        $ python main.py
"""

from stack_stream_parser import StreamJsonParser

###############################################################################
# Usage Example
###############################################################################

if __name__ == "__main__":
    parser = StreamJsonParser()
    parser.consume('{"foo": "bar')
    print(parser.get())  # => {"foo": "bar"} (partially complete string "bar")
    parser.consume('"}')
    print(parser.get())  # => {"foo": "bar"}
