"""LLM extraction: one LangChain chain that turns a `RawArticle` into a structured `Extraction`."""

from sumnews.extracting.chain import Extractor, build_chain
from sumnews.extracting.schema import Extraction

__all__ = ["Extraction", "Extractor", "build_chain"]
