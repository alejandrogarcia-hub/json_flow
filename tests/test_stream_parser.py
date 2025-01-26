import unittest

import pytest

from config import logger
from stream_parser import JSONDecodeError, StreamJsonParser


@pytest.fixture(autouse=True)
def disable_logging():
    logger.disabled = True
    yield
    logger.disabled = False


class TestStreamJsonParser(unittest.TestCase):
    def setUp(self):
        self.parser = StreamJsonParser()

    def test_initialization(self):
        """Test that parser initializes with empty stack and no current stream"""
        self.assertIsNone(self.parser.get())

    def test_empty_string(self):
        """Test consuming an empty string"""
        self.parser.consume("")
        self.assertIsNone(self.parser.get())

    def test_empty_object(self):
        """Test consuming an empty object"""
        self.parser.consume("{}")
        self.assertEqual(self.parser.get(), {})

    def test_invalid_root_value(self):
        """Test consuming and invalid JSON root value"""
        with self.assertRaises(JSONDecodeError):
            self.parser.consume('""')

    def test_object_one_chunk(self):
        """Test consuming a simple JSON object"""
        self.parser.consume('{"key": "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_partial_key(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_object_partial_key_extended(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key": "value"')
        self.parser.consume(',"new')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_value_type_known(self):
        """Test consuming JSON with not known value type"""
        self.parser.consume('{"key":')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_object_value_type_known_partial(self):
        """Test consuming JSON with incomplete value but known value type"""
        self.parser.consume('{"key": "')
        result = self.parser.get()
        self.assertEqual(result, {"key": ""})

    def test_object_value_type_known_partial_value(self):
        """Test consuming JSON with incomplete value but String value can be incomple"""
        self.parser.consume('{"key": "val')
        result = self.parser.get()
        self.assertEqual(result, {"key": "val"})

    def test_object_in_chunks(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        self.parser.consume('": "val')
        self.parser.consume('ue"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_object_malformed(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        with self.assertRaises(JSONDecodeError):
            # string is missing a closing quote in the key
            self.parser.consume(': "val')

    def test_object_nested_object(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "value"}}')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_object_nested_partial_key(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {}})

    def test_object_nested_partial_value(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "val')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "val"}})

if __name__ == "__main__":
    unittest.main()
