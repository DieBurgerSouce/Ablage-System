"""Hybrid OCR Agent - Multi-engine fusion for maximum accuracy."""

import asyncio
from typing import Any, Dict, List, Tuple

from app.agents.base import OCRAgent
from app.gpu_manager import GPUManager

from .deepseek_agent import DeepSeekAgent
from .got_ocr_agent import GOTOCRAgent
from .surya_docling_agent import SuryaDoclingAgent


class HybridOCRAgent(OCRAgent):
    """
    Hybrid OCR agent that combines multiple engines for maximum accuracy.

    Strategy:
    1. Smart parallel execution based on available VRAM
    2. Backends that fit in memory run in parallel
    3. Remaining backends run sequentially with cleanup
    4. Compare results with confidence-based voting
    5. Merge results using intelligent fusion
    """

    # Backend VRAM requirements in GB (muss mit gpu_manager.py uebereinstimmen)
    BACKEND_VRAM_MAP = {
        "deepseek": 12.0,      # DeepSeek-Janus-Pro needs 12GB
        "got_ocr": 10.0,       # GOT-OCR 2.0 needs 10GB
        "surya_docling": 0.5,  # Surya+Docling is mostly CPU (minimal GPU)
    }

    # Backend Prioritaet (hoeher = wichtiger, wird zuerst versucht)
    BACKEND_PRIORITY = {
        "deepseek": 3,     # Beste Qualitaet
        "got_ocr": 2,      # Gut fuer Tabellen/Formeln
        "surya_docling": 1 # CPU-Fallback
    }

    def __init__(self):
        super().__init__(name="hybrid_ocr_agent", gpu_required=True, vram_gb=12)

        # Initialize sub-agents
        self.deepseek = DeepSeekAgent()
        self.got_ocr = GOTOCRAgent()
        self.surya_docling = SuryaDoclingAgent()

        # GPU Manager fuer VRAM-Checks
        self.gpu_manager = GPUManager()

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
        """
        Smart Parallel OCR - Maximiert GPU-Nutzung ohne OOM.

        OPTIMIERUNG: Statt rein sequentieller Verarbeitung:
        1. Pruefe verfuegbaren VRAM
        2. Sortiere Backends nach Prioritaet
        3. Backends die zusammen passen → parallel
        4. Rest → sequentiell mit Memory Cleanup

        Auf RTX 4080 (16GB) mit 13.6GB nutzbarem VRAM:
        - DeepSeek (12GB) + Surya (0.5GB) = 12.5GB → parallel moeglich!
        - Dann GOT-OCR (10GB) → sequentiell nach Cleanup

        Erwarteter Speedup: ~30-40% gegenueber rein sequentiell.
        """
        try:
            import torch
            TORCH_AVAILABLE = torch.cuda.is_available()
        except ImportError:
            TORCH_AVAILABLE = False

        valid_results = []
        engines = [
            ("deepseek", self.deepseek),
            ("got_ocr", self.got_ocr),
            ("surya_docling", self.surya_docling),
        ]

        # Hole verfuegbaren VRAM
        available_vram_gb = self._get_available_vram()

        self.logger.info(
            "hybrid_ocr_smart_parallel_starting",
            available_vram_gb=round(available_vram_gb, 2),
            backends=[name for name, _ in engines]
        )

        # Sortiere nach Prioritaet (hoeher zuerst)
        sorted_engines = sorted(
            engines,
            key=lambda x: self.BACKEND_PRIORITY.get(x[0], 0),
            reverse=True
        )

        # Teile in parallel und sequential Gruppen
        parallel_tasks: List[Tuple[str, Any]] = []
        sequential_queue: List[Tuple[str, Any]] = []
        remaining_vram = available_vram_gb

        for engine_name, engine in sorted_engines:
            vram_required = self.BACKEND_VRAM_MAP.get(engine_name, 8.0)

            if vram_required <= remaining_vram:
                # Passt in verfuegbaren VRAM → parallel
                parallel_tasks.append((engine_name, engine))
                remaining_vram -= vram_required
            else:
                # Passt nicht → sequentiell spaeter
                sequential_queue.append((engine_name, engine))

        self.logger.info(
            "hybrid_ocr_execution_plan",
            parallel_backends=[name for name, _ in parallel_tasks],
            sequential_backends=[name for name, _ in sequential_queue],
            parallel_vram_usage=round(available_vram_gb - remaining_vram, 2)
        )

        # PHASE 1: Parallele Ausfuehrung
        if parallel_tasks:
            parallel_results = await self._run_parallel_group(
                parallel_tasks, input_data, TORCH_AVAILABLE
            )
            valid_results.extend(parallel_results)

        # PHASE 2: Sequentielle Ausfuehrung mit Memory Cleanup
        if sequential_queue:
            # Cleanup vor sequentieller Phase
            self._cleanup_gpu_memory(TORCH_AVAILABLE)

            sequential_results = await self._run_sequential_group(
                sequential_queue, input_data, TORCH_AVAILABLE
            )
            valid_results.extend(sequential_results)

        return valid_results

    async def _run_parallel_group(
        self,
        engines: List[Tuple[str, Any]],
        input_data: Dict[str, Any],
        torch_available: bool
    ) -> List[Dict[str, Any]]:
        """
        Fuehre eine Gruppe von Backends parallel aus.

        Args:
            engines: Liste von (name, engine) Tupeln
            input_data: OCR Input
            torch_available: PyTorch verfuegbar?

        Returns:
            Liste von Ergebnissen
        """
        if not engines:
            return []

        self.logger.info(
            "hybrid_ocr_parallel_phase",
            backends=[name for name, _ in engines]
        )

        async def process_engine(name: str, engine: Any) -> Dict[str, Any]:
            """Wrapper fuer einzelnes Backend mit Error Handling."""
            try:
                self.logger.debug(f"hybrid_parallel_starting_{name}")
                result = await engine.process(input_data)
                self.logger.info(
                    "hybrid_parallel_completed",
                    engine=name,
                    confidence=result.get("confidence", 0.0)
                )
                return {**result, "engine": name}
            except Exception as e:
                self.logger.warning(
                    "hybrid_parallel_failed",
                    engine=name,
                    error=str(e)
                )
                return {"engine": name, "error": str(e), "confidence": 0.0}

        # Alle parallel starten
        tasks = [process_engine(name, engine) for name, engine in engines]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtere erfolgreiche Ergebnisse
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.warning("hybrid_parallel_exception", error=str(result))
            elif isinstance(result, dict) and "error" not in result:
                valid_results.append(result)

        return valid_results

    async def _run_sequential_group(
        self,
        engines: List[Tuple[str, Any]],
        input_data: Dict[str, Any],
        torch_available: bool
    ) -> List[Dict[str, Any]]:
        """
        Fuehre eine Gruppe von Backends sequentiell aus mit Memory Cleanup.

        Args:
            engines: Liste von (name, engine) Tupeln
            input_data: OCR Input
            torch_available: PyTorch verfuegbar?

        Returns:
            Liste von Ergebnissen
        """
        valid_results = []

        for engine_name, engine in engines:
            try:
                self.logger.info(
                    "hybrid_sequential_starting",
                    engine=engine_name
                )

                result = await engine.process(input_data)
                valid_results.append({**result, "engine": engine_name})

                self.logger.info(
                    "hybrid_sequential_completed",
                    engine=engine_name,
                    confidence=result.get("confidence", 0.0)
                )

            except Exception as e:
                self.logger.warning(
                    "hybrid_sequential_failed",
                    engine=engine_name,
                    error=str(e)
                )
            finally:
                # Memory Cleanup nach jedem Backend
                self._cleanup_gpu_memory(torch_available)

        return valid_results

    def _get_available_vram(self) -> float:
        """
        Hole verfuegbaren VRAM in GB.

        Returns:
            Verfuegbarer VRAM in GB (mit 15% Safety Buffer)
        """
        try:
            import torch
            if not torch.cuda.is_available():
                return 0.0

            total = torch.cuda.get_device_properties(0).total_memory
            allocated = torch.cuda.memory_allocated(0)
            free = total - allocated

            # 15% Safety Buffer
            safe_free = free * 0.85

            return safe_free / (1024**3)

        except Exception as e:
            self.logger.warning("vram_check_failed", error=str(e))
            return 0.0

    def _cleanup_gpu_memory(self, torch_available: bool) -> None:
        """GPU Memory aufraeumen."""
        if not torch_available:
            return

        try:
            import gc
            import torch

            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

            allocated_gb = torch.cuda.memory_allocated() / (1024**3)
            self.logger.debug(
                "hybrid_memory_cleanup",
                allocated_gb=round(allocated_gb, 2)
            )
        except Exception as e:
            self.logger.warning("memory_cleanup_failed", error=str(e))

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

        # Use internal Levenshtein implementation
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
