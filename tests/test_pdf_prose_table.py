"""Tests for the F1 prose-table rejection heuristic (pdf_standardizer).

Live-data defect: pdfplumber wraps whole prose pages of transcript-style PDFs
in narrow pseudo tables — a livestream transcript came out as 27/27 blocks of
block_type=table_region with pipe framing around plain speech. The heuristic
demotes those back to text blocks while keeping genuine tables intact.
"""
from __future__ import annotations

from finer.parsing.pdf_standardizer import PDFStandardizer

# Shape observed on disk (data/F1_standardized/local_4fcfe97a…): a "2-row,
# 1-column table" whose cell holds a whole page of multi-line speech.
TRANSCRIPT_PROSE = (
    "看听一听会大家到首先是。\n在2月13日，我们的这个M2 minmax发布的这个在M2基础上发"
    "布的小版本迭代M2.5。但它的整体的编程工具调用等这个场景，它的测评水准都到了一个行业"
    "搜它的这样一个测评的一个前列的位置。\n然后亚马逊也不是很强，亚马逊也不是很强，但是"
    "反正至少是目前来说，在日线级别还是在高位震荡向上的。"
)

FAKE_TABLE = [
    ["20260315内部直播音频.mp3"],
    [TRANSCRIPT_PROSE],
]

GENUINE_TABLE = [
    ["标的", "方向", "仓位", "止损"],
    ["贵州茅台", "看多", "30%", "1450"],
    ["宁德时代", "观察", "-", "-"],
    ["腾讯控股", "看多", "25%", "380"],
]


class TestIsProseTable:
    def setup_method(self):
        self.std = PDFStandardizer()

    def test_transcript_pseudo_table_detected(self):
        assert self.std._is_prose_table(FAKE_TABLE) is True

    def test_genuine_table_kept(self):
        """3+ columns of short label cells is a real table."""
        assert self.std._is_prose_table(GENUINE_TABLE) is False

    def test_two_col_short_cells_kept(self):
        """A narrow but genuinely tabular key-value table stays a table."""
        kv = [["指标", "值"], ["PE", "17x"], ["股息率", "6%"], ["市值", "1.2万亿"]]
        assert self.std._is_prose_table(kv) is False

    def test_two_col_long_cell_demoted(self):
        long_note = "这是一段完整论述，" * 15  # 135 chars ≥ _PROSE_CELL_MAX_LEN
        assert len(long_note) >= PDFStandardizer._PROSE_CELL_MAX_LEN
        assert self.std._is_prose_table([["要点"], [long_note]]) is True

    def test_multiline_cell_demoted(self):
        cell = (
            "第一行是关于宏观环境与流动性的完整观点表述。\n"
            "第二行是关于个股仓位管理与止损纪律的完整观点表述。\n"
            "第三行是收尾总结，行文连贯，读起来完全不像表格单元格。"
        )
        assert len(cell) >= PDFStandardizer._PROSE_MULTILINE_MIN_LEN
        assert self.std._is_prose_table([["标题"], [cell]]) is True

    def test_empty_cells_not_prose(self):
        assert self.std._is_prose_table([["", None], ["", ""]]) is False


class TestCellsToProse:
    def test_flattens_without_pipes(self):
        text = PDFStandardizer._table_cells_to_prose(FAKE_TABLE)
        assert "|" not in text
        assert text.startswith("20260315内部直播音频.mp3")
        assert "亚马逊也不是很强" in text

    def test_skips_empty_cells(self):
        text = PDFStandardizer._table_cells_to_prose([["a", ""], [None, "b"]])
        assert text == "a\nb"
