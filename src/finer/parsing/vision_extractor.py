import os
import logging
import base64
import mimetypes
from pathlib import Path

from finer.llm.client import LLMClient
from finer.model_config import get_vision_registry
from finer.schemas.content import ContentRecord
from finer.schemas.segment import SegmentRecord

class VisionExtractor:
    """
    Legacy image extractor that emits SegmentRecord blocks.

    New F1 code should use ImageOCRLayoutStandardizer. This compatibility
    extractor still exists for older ingestion flows, but it uses the same
    MiMo-V2.5 vision registry as canonical F1 OCR.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("MIMO_API_KEY")
        if not self.api_key:
            raise ValueError("MIMO_API_KEY is not set.")
        registry = get_vision_registry()
        model_config = registry.models[0]
        self.client = LLMClient(
            api_key=self.api_key,
            base_url=model_config.base_url,
            model=model_config.name,
            max_tokens=model_config.max_tokens,
            api_key_header=model_config.api_key_header,
            api_key_scheme=model_config.api_key_scheme,
            max_tokens_field=model_config.max_tokens_field,
        )

    def extract_image(self, content_record: ContentRecord) -> list[SegmentRecord]:
        """
        Calls MiMo-V2.5 to extract text from a single image and parse it into manageable segments.
        """
        source_path = Path(content_record.source_path)
        if not source_path.exists():
            logging.error(f"Image not found: {source_path}")
            return []

        prompt = (
            "你是一个专业的金融文档解析助手。请精准提取这张图片中的所有文字信息，"
            "并严格按照原图的视觉排版结构，将其转化为逻辑连贯的Markdown格式返回。"
            "遇到图表，请尽可能提取表头结构和主要数据。"
            "注意：只需返回Markdown本身，不要附加额外问候语。"
        )

        logging.info("Sending %s to MiMo-V2.5 vision OCR...", source_path.name)
        image_b64 = base64.b64encode(source_path.read_bytes()).decode("ascii")
        mime_type = mimetypes.guess_type(str(source_path))[0] or "image/png"
        text_result = self.client.chat_with_images(
            text=prompt,
            image_base64=image_b64,
            mime_type=mime_type,
        )

        if text_result:
            # Better chunking: track Markdown headers for structural context
            lines = text_result.split("\n")
            segments = []
            current_heading = "未分类"
            current_block = []
            block_idx = 0

            def flush_block(text_lines, heading, idx):
                full_text = "\n".join(text_lines).strip()
                if not full_text:
                    return None
                return SegmentRecord(
                    segment_id=f"{content_record.content_id}-imgblock-{idx}",
                    content_id=content_record.content_id,
                    block_index=idx,
                    text=full_text,
                    source_modality="image_ocr",
                    metadata={"parent_heading": heading}
                )

            for line in lines:
                if line.strip().startswith("#"):
                    # Before changing heading, flush current block
                    if current_block:
                        seg = flush_block(current_block, current_heading, block_idx)
                        if seg:
                            segments.append(seg)
                            block_idx += 1
                        current_block = []
                    current_heading = line.strip().replace("#", "").strip()
                elif not line.strip():
                    if current_block:
                        seg = flush_block(current_block, current_heading, block_idx)
                        if seg:
                            segments.append(seg)
                            block_idx += 1
                        current_block = []
                else:
                    current_block.append(line)
            
            # Final flush
            if current_block:
                seg = flush_block(current_block, current_heading, block_idx)
                if seg:
                    segments.append(seg)

            return segments
        else:
            logging.error("MiMo-V2.5 vision OCR returned no text for %s", source_path.name)
            return []
