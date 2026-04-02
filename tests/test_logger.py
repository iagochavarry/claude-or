"""Tests for claude_or.logger — text extraction from various message formats.

User Story Covered:
  7. "I can see what's happening" — logger correctly extracts text from
     both plain string and Anthropic content block formats.
"""

import pytest

from claude_or.logger import extract_text


class TestExtractText:
    """AC: extract_text handles all content formats Claude Code may send."""

    def test_plain_string(self):
        assert extract_text("hello world") == "hello world"

    def test_string_truncated_at_max_len(self):
        result = extract_text("a" * 200, max_len=50)
        assert len(result) == 50

    def test_newlines_replaced_with_spaces(self):
        assert extract_text("line1\nline2") == "line1 line2"

    def test_empty_string(self):
        assert extract_text("") == ""

    def test_none_returns_empty(self):
        assert extract_text(None) == ""

    def test_text_content_block(self):
        content = [{"type": "text", "text": "hello from block"}]
        assert extract_text(content) == "hello from block"

    def test_tool_result_block(self):
        content = [{"type": "tool_result", "content": "some result"}]
        assert extract_text(content) == "[tool_result]"

    def test_thinking_block(self):
        content = [{"type": "thinking", "thinking": "hmm..."}]
        assert extract_text(content) == "[thinking]"

    def test_tool_use_block(self):
        content = [{"type": "tool_use", "name": "Read", "input": {}}]
        assert extract_text(content) == "[tool: Read]"

    def test_tool_use_without_name(self):
        content = [{"type": "tool_use"}]
        assert extract_text(content) == "[tool: ?]"

    def test_unknown_block_type(self):
        content = [{"type": "image", "source": {}}]
        assert extract_text(content) == "[image]"

    def test_mixed_content_blocks(self):
        content = [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "name": "Bash", "input": {}},
            {"type": "text", "text": "world"},
        ]
        result = extract_text(content)
        assert "hello" in result
        assert "[tool: Bash]" in result
        assert "world" in result

    def test_non_dict_in_list_ignored(self):
        content = ["just a string", {"type": "text", "text": "real block"}]
        result = extract_text(content)
        assert "real block" in result

    def test_fallback_to_str(self):
        result = extract_text(12345)
        assert result == "12345"
