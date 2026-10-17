"""Knowledge-base search tool (`kb_search`) over the `KnowledgeBase` read face (src/memory/long_term.py).

Every hit carries its source (`source_url`, null only for internal notes), `version_tag` and `title`, so an answer can
always show where a claim comes from (guardrails-security section 4). The runtime versions filter out notes that do not
apply (D-227); an unknown version filters nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.memory.long_term import KnowledgeBase, KnowledgeUnavailableError, RuntimeVersions
from src.tools.base_tool import SchemaStore, ToolCode, ToolContext, ToolUnavailableError


class KbSearchTool:
    name = "kb_search"

    def __init__(self, knowledge: KnowledgeBase, schemas: SchemaStore) -> None:
        self._knowledge = knowledge
        self._input_schema = schemas.part(self.name, "input")
        self._output_schema = schemas.part(self.name, "output")

    @property
    def tool_code(self) -> ToolCode:
        return "KB_SEARCH"

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self._output_schema

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        runtime = RuntimeVersions.from_strings(arguments.get("java_version"), arguments.get("spring_boot_version"))
        try:
            hits = self._knowledge.search(str(arguments["query"]), runtime, arguments.get("k"))
        except KnowledgeUnavailableError:
            raise ToolUnavailableError("the knowledge base cannot be searched (embedding model unavailable)") from None
        return {
            "hits": [
                {
                    "doc_key": hit.doc_key,
                    "title": hit.title,
                    "source_url": hit.source_url,
                    "source_type": hit.source_type,
                    "version_tag": hit.version_tag,
                    "language": hit.language,
                    "ordinal": hit.ordinal,
                    "text": hit.text,
                    "distance": round(hit.distance, 6),
                }
                for hit in hits
            ]
        }
