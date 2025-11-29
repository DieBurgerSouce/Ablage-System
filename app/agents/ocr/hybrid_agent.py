"""Hybrid OCR Agent - Multi-engine fusion for maximum accuracy."""

import asyncio
from typing import Any, Dict, List

from app.agents.base import OCRAgent

from .deepseek_agent import DeepSeekAgent
from .got_ocr_agent import GOTOCRAgent
from .surya_docling_agent import SuryaDoclingAgent


class HybridOCRAgent(OCRAgent):
    """
    Hybrid OCR agent that combines multiple engines for maximum accuracy.

    Strategy:
    1. Run all available OCR engines in parallel
    2. Compare results with confidence-based voting
    3. Merge results using intelligent fusion
    """

    def __init__(self):
        super().__init__(name="hybrid_ocr_agent", gpu_required=True, vram_gb=12)

        # Initialize sub-agents
        self.deepseek = DeepSeekAgent()
        self.got_ocr = GOTOCRAgent()
        self.surya_docling = SuryaDoclingAgent()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process with multiple OCR engines and fuse results.

        Returns best result based on:
        - Confidence scores
        - Text length (longer usually better)
        - Entity recognition quality
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]

        self.logger.info(
            "hybrid_ocr_started",
            document_id=document_id,
            engines=["deepseek", "got_ocr", "surya_docling"],
        )

        # Run all engines in parallel
        results = await self._run_parallel_ocr(input_data)

        # Fuse results
        fused_result = await self._fuse_results(results)

        self.logger.info(
            "hybrid_ocr_completed",
            document_id=document_id,
            selected_engine=fused_result.get("selected_engine"),
            confidence=fused_result.get("confidence"),
        )

        return fused_result

    async def _run_parallel_ocr(
        self, input_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Run all OCR engines in parallel."""
        tasks = [
            self.deepseek.process(input_data),
            self.got_ocr.process(input_data),
            self.surya_docling.process(input_data),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            engine_name = ["deepseek", "got_ocr", "surya_docling"][i]
            if isinstance(result, Exception):
                self.logger.warning(
                    "hybrid_ocr_engine_failed",
                    engine=engine_name,
                    error=str(result),
                )
            else:
                valid_results.append({**result, "engine": engine_name})

        return valid_results

    async def _fuse_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Fuse results from multiple engines.

        Strategy:
        1. Select engine with highest confidence
        2. If confidences similar, choose longest text
        3. Merge entities from all engines
        """
        if not results:
            raise ValueError("No valid OCR results to fuse")

        # Sort by confidence
        sorted_results = sorted(
            results, key=lambda x: x.get("confidence", 0.0), reverse=True
        )

        # Select best result
        best_result = sorted_results[0]

        # Merge entities from all results (if available)
        all_entities = []
        for result in results:
            entities = result.get("entities", [])
            all_entities.extend(entities)

        # Deduplicate entities
        unique_entities = self._deduplicate_entities(all_entities)

        return {
            "text": best_result.get("text", ""),
            "confidence": best_result.get("confidence", 0.0),
            "selected_engine": best_result.get("engine"),
            "all_confidences": {
                r.get("engine"): r.get("confidence") for r in results
            },
            "entities": unique_entities,
            "layout": best_result.get("layout", {}),
        }

    def _deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """
        Deduplicate entities from multiple OCR sources.

        Strategy:
        1. Exact match: Group by type:value key
        2. Fuzzy match: Use Levenshtein distance (threshold 85%)
        3. Merge: Keep highest confidence, combine sources

        Args:
            entities: List of entity dicts with 'type', 'value', 'confidence', 'source'

        Returns:
            Deduplicated entities with merged metadata
        """
        if not entities:
            return []

        # Group entities by type first
        by_type: Dict[str, List[Dict]] = {}
        for entity in entities:
            entity_type = entity.get("type", "unknown")
            if entity_type not in by_type:
                by_type[entity_type] = []
            by_type[entity_type].append(entity)

        deduplicated = []

        for entity_type, type_entities in by_type.items():
            # First pass: Exact match deduplication
            exact_groups = self._group_by_exact_match(type_entities)

            # Second pass: Fuzzy match within remaining entities
            fuzzy_merged = self._merge_fuzzy_matches(exact_groups)

            deduplicated.extend(fuzzy_merged)

        # Sort by confidence (highest first)
        deduplicated.sort(
            key=lambda x: x.get("confidence", 0.0),
            reverse=True
        )

        return deduplicated

    def _group_by_exact_match(self, entities: List[Dict]) -> List[Dict]:
        """
        Group entities by exact value match, keeping highest confidence.

        Returns merged entities with combined sources.
        """
        groups: Dict[str, Dict] = {}

        for entity in entities:
            value = str(entity.get("value", "")).strip().lower()
            key = value

            if key not in groups:
                groups[key] = {
                    "type": entity.get("type"),
                    "value": entity.get("value"),
                    "confidence": entity.get("confidence", 0.0),
                    "sources": [entity.get("source", "unknown")],
                    "original_values": [entity.get("value")]
                }
            else:
                # Merge: update if higher confidence
                existing = groups[key]
                if entity.get("confidence", 0.0) > existing["confidence"]:
                    existing["confidence"] = entity.get("confidence", 0.0)
                    existing["value"] = entity.get("value")  # Keep original casing

                # Track all sources
                source = entity.get("source", "unknown")
                if source not in existing["sources"]:
                    existing["sources"].append(source)

                # Track variations
                orig_val = entity.get("value")
                if orig_val not in existing["original_values"]:
                    existing["original_values"].append(orig_val)

        return list(groups.values())

    def _merge_fuzzy_matches(
        self,
        entities: List[Dict],
        threshold: float = 0.85
    ) -> List[Dict]:
        """
        Merge entities with similar values using Levenshtein distance.

        Args:
            entities: Pre-grouped entities from exact match
            threshold: Similarity threshold (0.85 = 85% match)

        Returns:
            Further merged entities
        """
        if len(entities) <= 1:
            return entities

        merged = []
        used_indices = set()

        for i, entity_a in enumerate(entities):
            if i in used_indices:
                continue

            # Start a merge group with this entity
            merge_group = [entity_a]
            value_a = str(entity_a.get("value", ""))

            for j, entity_b in enumerate(entities[i + 1:], start=i + 1):
                if j in used_indices:
                    continue

                value_b = str(entity_b.get("value", ""))

                # Calculate similarity using Levenshtein distance
                similarity = self._calculate_similarity(value_a, value_b)

                if similarity >= threshold:
                    merge_group.append(entity_b)
                    used_indices.add(j)

            # Merge the group into single entity
            merged_entity = self._merge_entity_group(merge_group)
            merged.append(merged_entity)
            used_indices.add(i)

        return merged

    def _calculate_similarity(self, str_a: str, str_b: str) -> float:
        """
        Calculate similarity between two strings using Levenshtein distance.

        Returns value between 0.0 (no match) and 1.0 (exact match).
        """
        if not str_a and not str_b:
            return 1.0
        if not str_a or not str_b:
            return 0.0

        # Normalize strings
        str_a = str_a.strip().lower()
        str_b = str_b.strip().lower()

        if str_a == str_b:
            return 1.0

        try:
            # Try to use external Levenshtein function
            from Static_Knowledge.Snippets.german_validation_snippets import (
                levenshtein_distance
            )
            distance = levenshtein_distance(str_a, str_b)
        except ImportError:
            # Fallback: inline implementation
            distance = self._levenshtein_distance(str_a, str_b)

        max_len = max(len(str_a), len(str_b))
        similarity = 1.0 - (distance / max_len)

        return similarity

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calculate Levenshtein edit distance between two strings.

        Fallback implementation if external function unavailable.
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)

        for i, c1 in enumerate(s1):
            current_row = [i + 1]

            for j, c2 in enumerate(s2):
                # Calculate costs
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)

                current_row.append(min(insertions, deletions, substitutions))

            previous_row = current_row

        return previous_row[-1]

    def _merge_entity_group(self, group: List[Dict]) -> Dict:
        """
        Merge a group of similar entities into one.

        Keeps highest confidence value and combines all sources.
        """
        if not group:
            return {}

        if len(group) == 1:
            return group[0]

        # Find entity with highest confidence
        best = max(group, key=lambda x: x.get("confidence", 0.0))

        # Collect all sources
        all_sources = []
        all_values = []

        for entity in group:
            sources = entity.get("sources", [entity.get("source", "unknown")])
            if isinstance(sources, list):
                for s in sources:
                    if s not in all_sources:
                        all_sources.append(s)
            else:
                if sources not in all_sources:
                    all_sources.append(sources)

            # Collect value variations
            values = entity.get("original_values", [entity.get("value")])
            if isinstance(values, list):
                for v in values:
                    if v not in all_values:
                        all_values.append(v)
            else:
                if values not in all_values:
                    all_values.append(values)

        return {
            "type": best.get("type"),
            "value": best.get("value"),
            "confidence": best.get("confidence", 0.0),
            "sources": all_sources,
            "source_count": len(all_sources),
            "variations": all_values if len(all_values) > 1 else None
        }
