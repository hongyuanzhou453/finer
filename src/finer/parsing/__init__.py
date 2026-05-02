"""Finer Parsing Module.

This module provides content parsing and standardization utilities
for the Finer pipeline.

Key Components:
- Content standardization (text, markdown, transcripts)
- Slang detection and mapping
- OCR/ASR processing (future)
"""

from finer.parsing.content_standardizer import (
    standardize_text_source,
    standardize_markdown_source,
    standardize_chat_transcript,
    standardize_audio_transcript,
    standardize_image_strategy,
)

from finer.parsing.feishu_chat_standardizer import (
    FeishuChatMarkdownStandardizer,
)

from finer.parsing.image_ocr_standardizer import (
    ImageOCRLayoutStandardizer,
)

from finer.parsing.pdf_standardizer import (
    PDFStandardizer,
)

from finer.parsing.topic_assembler import (
    TopicAssembler,
)
from finer.parsing.llm_topic_assembly_adapter import (
    LLMTopicAssemblyAdapter,
    LLMTopicAssemblyError,
)
from finer.parsing.manual_text_standardizer import (
    ManualTextStandardizer,
)
from finer.parsing.standardization_router import (
    StandardizationRouter,
    StandardizationReport,
    StandardizationError,
)

__all__ = [
    # Content standardization
    "standardize_text_source",
    "standardize_markdown_source",
    "standardize_chat_transcript",
    "standardize_audio_transcript",
    "standardize_image_strategy",
    # F1 Canonical Standardizers
    "FeishuChatMarkdownStandardizer",
    "ImageOCRLayoutStandardizer",
    "PDFStandardizer",
    "ManualTextStandardizer",
    # F1 Router
    "StandardizationRouter",
    "StandardizationReport",
    "StandardizationError",
    # F1.5 Topic Assembly
    "TopicAssembler",
    "LLMTopicAssemblyAdapter",
    "LLMTopicAssemblyError",
]
