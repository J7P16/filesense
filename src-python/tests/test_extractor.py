"""
Tests for the text extractor.

Uses temporary files to test extraction from various file types.
"""

import pytest
from pathlib import Path
from app.core.extractor import extract_text, ExtractionError


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestPlaintextExtraction:
    def test_extract_txt(self, tmp_dir):
        f = tmp_dir / "test.txt"
        f.write_text("Hello, this is a text file.")
        result = extract_text(f)
        assert "Hello" in result
        assert "text file" in result

    def test_extract_markdown(self, tmp_dir):
        f = tmp_dir / "test.md"
        f.write_text("# Title\n\nSome **bold** text.")
        result = extract_text(f)
        assert "Title" in result
        assert "bold" in result

    def test_extract_python(self, tmp_dir):
        f = tmp_dir / "test.py"
        f.write_text('def hello():\n    return "world"')
        result = extract_text(f)
        assert "def hello" in result

    def test_extract_json(self, tmp_dir):
        f = tmp_dir / "test.json"
        f.write_text('{"key": "value", "number": 42}')
        result = extract_text(f)
        assert "key" in result
        assert "value" in result

    def test_extract_empty_file(self, tmp_dir):
        f = tmp_dir / "empty.txt"
        f.write_text("")
        result = extract_text(f)
        assert result == ""

    def test_extract_utf8_bom(self, tmp_dir):
        f = tmp_dir / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello BOM")
        result = extract_text(f)
        assert "Hello BOM" in result


class TestCSVExtraction:
    def test_extract_csv(self, tmp_dir):
        f = tmp_dir / "test.csv"
        f.write_text("name,age,city\nAlice,30,London\nBob,25,Paris")
        result = extract_text(f)
        assert "Alice" in result
        assert "London" in result

    def test_extract_tsv(self, tmp_dir):
        f = tmp_dir / "test.tsv"
        f.write_text("name\tage\tcity\nAlice\t30\tLondon")
        result = extract_text(f)
        assert "Alice" in result
        assert "London" in result


class TestErrorHandling:
    def test_nonexistent_file(self):
        with pytest.raises(ExtractionError):
            extract_text(Path("/nonexistent/file.txt"))

    def test_binary_file_graceful(self, tmp_dir):
        f = tmp_dir / "binary.txt"
        f.write_bytes(b"\x00\x01\x02\x03\x04\x05")
        # Should not crash, may return garbled text
        result = extract_text(f)
        assert isinstance(result, str)
