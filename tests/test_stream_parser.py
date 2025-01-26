import unittest
from main import StreamJsonParser


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

    def test_consume_partial_value(self):
        """Test consuming JSON with incomplete value"""
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

    def test_consume_nested_json(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "value"}}')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_consume_nested_partial_key(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})

    def test_consume_nested_partial_value(self):
        """Test consuming nested JSON objects"""
        self.parser.consume('{"outer": {"inner": "val')
        result = self.parser.get()
        self.assertEqual(result, {"outer": {"inner": "value"}})


if __name__ == "__main__":
    unittest.main()
