import unittest

import pytest

from config import logger
from main import JSONDecodeError, StreamJsonParser


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

    def test_consume_empty_string(self):
        """Test consuming an empty string"""
        self.parser.consume("")
        self.assertIsNone(self.parser.get())

    def test_consume_invalid_json_root_value(self):
        """Test consuming and invalid JSON root value"""
        with self.assertRaises(JSONDecodeError):
            self.parser.consume('""')

    def test_consume_simple_json(self):
        """Test consuming a simple JSON object"""
        self.parser.consume('{"key": "value"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_consume_partial_key(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_consume_partial_key_extended(self):
        """Test consuming JSON with incomplete key"""
        self.parser.consume('{"key": "value"')
        self.parser.consume(',"new')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_consume_key_no_value_type_known(self):
        """Test consuming JSON with not known value type"""
        self.parser.consume('{"key":')
        result = self.parser.get()
        self.assertEqual(result, {})

    def test_consume_partial_value_open_string(self):
        """Test consuming JSON with incomplete value but known value type"""
        self.parser.consume('{"key": "')
        result = self.parser.get()
        self.assertEqual(result, {"key": ""})

    def test_consume_partial_value(self):
        """Test consuming JSON with incomplete value but String value can be incomple"""
        self.parser.consume('{"key": "val')
        result = self.parser.get()
        self.assertEqual(result, {"key": "val"})

    def test_consume_partial_json(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        self.parser.consume('": "val')
        self.parser.consume('ue"}')
        result = self.parser.get()
        self.assertEqual(result, {"key": "value"})

    def test_consume_partial_json_malformed(self):
        """Test consuming JSON in multiple parts"""
        self.parser.consume('{"key')
        with self.assertRaises(JSONDecodeError):
            # string is missing a closing quote in the key
            self.parser.consume(': "val')

    def test_consume_nested_json(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "value"}}')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_consume_nested_partial_key(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {}})

    def test_consume_nested_partial_value(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "val')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "val"}})


if __name__ == "__main__":
    unittest.main()
