🏗️ PERFEKTER TECH-STACK & ARCHITEKTUR
Intelligent Document Processing System - Complete Blueprint

📋 SYSTEM-ÜBERSICHT
┌─────────────────────────────────────────────────────────────┐
│                     EXTERNAL INTERFACE                       │
│                  (REST API / File Upload)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    API GATEWAY LAYER                         │
│                      (FastAPI)                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  - Authentication & Authorization                     │  │
│  │  - Request Validation                                 │  │
│  │  - Rate Limiting                                      │  │
│  │  - Document Type Detection                            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  ORCHESTRATOR LAYER                          │
│                   (Job Scheduler)                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Intelligence Router:                                 │  │
│  │  ├─ Document Complexity Score                         │  │
│  │  ├─ Backend Health Check                             │  │
│  │  ├─ Load Balancing Logic                             │  │
│  │  └─ Priority Queue Management                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────┬──────────────────┬──────────────────┬────────────────┘
      │                  │                  │
      ▼                  ▼                  ▼
┌─────────────┐  ┌──────────────┐  ┌──────────────┐
│  GPU-A      │  │   GPU-B      │  │   CPU        │
│  DeepSeek   │  │   GOT-OCR    │  │   Surya +    │
│  Janus-Pro  │  │   2.0        │  │   Docling    │
│             │  │              │  │              │
│  Complex    │  │   Fast       │  │   Fallback   │
│  Docs       │  │   OCR        │  │   / Overflow │
└─────┬───────┘  └──────┬───────┘  └──────┬───────┘
      │                  │                  │
      └──────────────────┼──────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              POST-PROCESSING PIPELINE                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. Confidence Scoring                                │  │
│  │  2. Data Validation                                   │  │
│  │  3. Supplier Recognition                              │  │
│  │  4. Table Normalization                               │  │
│  │  5. Format Conversion (JSON/XML/CSV)                  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   STORAGE LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │    Redis     │  │   MinIO/S3   │      │
│  │              │  │              │  │              │      │
│  │ - Metadata   │  │ - Queue      │  │ - Original   │      │
│  │ - Results    │  │ - Cache      │  │   Files      │      │
│  │ - Audit Log  │  │ - Sessions   │  │ - Processed  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘

🎯 TECH-STACK DETAILS
1. Core Framework
yamlFramework: FastAPI 0.110+
  Warum:
    - Async/Await Support (wichtig für GPU-Warteschlangen)
    - Automatic OpenAPI Documentation
    - Pydantic Validation
    - WebSocket Support (für Real-time Updates)
    
Language: Python 3.11+
  Warum:
    - Beste ML-Library Support
    - Type Hints für bessere Code-Qualität
    - Performance Improvements vs 3.10
2. GPU-Backend A: DeepSeek-Janus-Pro
yamlModel: DeepSeek-Janus-Pro-1.3B
Repository: https://huggingface.co/deepseek-ai/Janus-Pro-1B

Dependencies:
  - torch >= 2.1.0 (CUDA 12.1)
  - transformers >= 4.37.0
  - accelerate >= 0.25.0
  - pillow >= 10.0.0
  
Hardware Requirements:
  VRAM: 12-16 GB
  RAM: 8 GB
  
Initialization:
  - Model Loading: ~5-8 seconds
  - Memory Footprint: 14 GB VRAM
  - Warmup: 1 inference vorher
  
Performance:
  - Single Page: 1-2 seconds
  - Batch (4 pages): 4-6 seconds
  - Max Batch Size: 4 (memory constrained)
3. GPU-Backend B: GOT-OCR 2.0
yamlModel: GOT-OCR 2.0 (580M parameters)
Repository: https://github.com/Ucas-HaoranWei/GOT-OCR2.0

Dependencies:
  - torch >= 2.1.0 (CUDA 12.1)
  - transformers >= 4.37.0
  - tiktoken >= 0.5.0
  
Hardware Requirements:
  VRAM: 10-12 GB
  RAM: 6 GB
  
Initialization:
  - Model Loading: ~3-5 seconds
  - Memory Footprint: 11 GB VRAM
  - Warmup: 1 inference
  
Performance:
  - Single Page: 0.3-0.5 seconds
  - Batch (8 pages): 3-4 seconds
  - Max Batch Size: 8
4. CPU-Backend: Surya + Docling
yamlComponents:
  Primary OCR: Surya OCR
    Repository: https://github.com/VikParuchuri/surya
    RAM: 8 GB per worker
    
  Layout Analysis: Docling
    Repository: https://github.com/DS4SD/docling
    RAM: 6 GB per worker

Dependencies:
  - surya-ocr >= 0.4.0
  - docling >= 1.0.0
  - onnxruntime >= 1.16.0 (CPU optimized)
  
Hardware Requirements:
  RAM: 12-16 GB per worker
  CPU: 4+ cores per worker
  
Initialization:
  - Model Loading: ~2-3 seconds per worker
  - Memory Footprint: 14 GB RAM total
  
Performance:
  - Single Page: 3-5 seconds
  - Parallel Workers: 2-3 (based on 64GB RAM)
  - Throughput: ~720-1200 pages/hour
5. Queue & Caching
yamlMessage Queue: Redis 7.2+
  Purpose:
    - Job Queue (Bull/RQ)
    - Result Caching (24h TTL)
    - Session Management
    - Real-time Status Updates
    
  Configuration:
    maxmemory: 4GB
    maxmemory-policy: allkeys-lru
    persistence: AOF + RDB
6. Database
yamlPrimary DB: PostgreSQL 16+
  Extensions:
    - pgvector (für future: semantic search)
    - pg_trgm (für fuzzy supplier matching)
    
  Schema Design:
    Tables:
      - documents
      - processing_jobs
      - ocr_results
      - suppliers
      - audit_logs
      - system_metrics
7. File Storage
yamlObject Storage: MinIO (S3-compatible)
  Buckets:
    - original-documents
    - processed-documents
    - thumbnails
    
  Lifecycle Policies:
    - Original: 90 days retention
    - Processed: 30 days retention
    - Thumbnails: 7 days retention
8. Monitoring & Observability
yamlMetrics: Prometheus + Grafana
  Metrics to Track:
    - Processing time per backend
    - Queue depth
    - GPU utilization
    - Memory usage
    - Error rates
    - Confidence scores distribution
    
Logging: Structured JSON logging
  - Winston/Loguru
  - ELK Stack optional

🔧 DETAILED IMPLEMENTATION
Architecture Pattern: Strategy + Factory
python# /backend/core/base_backend.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pydantic import BaseModel

class ProcessingResult(BaseModel):
    """Standardized result format für alle Backends"""
    text: str
    confidence: float
    layout: Dict[str, Any]
    tables: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    processing_time: float
    backend_used: str

class BaseOCRBackend(ABC):
    """Abstract Base Class für alle OCR Backends"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_loaded = False
        self.model = None
        
    @abstractmethod
    async def load_model(self):
        """Load ML model into memory"""
        pass
    
    @abstractmethod
    async def unload_model(self):
        """Free GPU/RAM"""
        pass
    
    @abstractmethod
    async def process_document(
        self, 
        image_path: str,
        options: Dict[str, Any]
    ) -> ProcessingResult:
        """Process single document"""
        pass
    
    @abstractmethod
    async def process_batch(
        self,
        image_paths: List[str],
        options: Dict[str, Any]
    ) -> List[ProcessingResult]:
        """Process multiple documents"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if backend is healthy"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Return backend metrics"""
        pass
GPU Backend A: DeepSeek Implementation
python# /backend/gpu/deepseek_backend.py

import torch
from transformers import AutoModelForVision2Seq, AutoProcessor
from PIL import Image
import time
from typing import Dict, Any, List
from ..core.base_backend import BaseOCRBackend, ProcessingResult

class DeepSeekBackend(BaseOCRBackend):
    """DeepSeek-Janus-Pro Backend for complex document understanding"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_name = "deepseek-ai/Janus-Pro-1B"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16  # Half precision für VRAM efficiency
        
    async def load_model(self):
        """Load DeepSeek model"""
        if self.is_loaded:
            return
            
        print(f"Loading DeepSeek-Janus-Pro on {self.device}...")
        start_time = time.time()
        
        self.processor = AutoProcessor.from_pretrained(
            self.model_name,
            trust_remote_code=True
        )
        
        self.model = AutoModelForVision2Seq.from_pretrained(
            self.model_name,
            torch_dtype=self.dtype,
            device_map="auto",
            trust_remote_code=True
        )
        
        # Warmup
        dummy_image = Image.new('RGB', (800, 600), color='white')
        self._warmup(dummy_image)
        
        load_time = time.time() - start_time
        print(f"DeepSeek loaded in {load_time:.2f}s")
        print(f"VRAM usage: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
        
        self.is_loaded = True
        
    async def unload_model(self):
        """Unload model to free VRAM"""
        if not self.is_loaded:
            return
            
        del self.model
        del self.processor
        torch.cuda.empty_cache()
        
        self.model = None
        self.processor = None
        self.is_loaded = False
        
        print("DeepSeek unloaded, VRAM freed")
        
    def _warmup(self, image: Image.Image):
        """Warmup inference"""
        prompt = "Extract all text from this document"
        inputs = self.processor(
            text=prompt,
            images=image,
            return_tensors="pt"
        ).to(self.device)
        
        with torch.no_grad():
            _ = self.model.generate(
                **inputs,
                max_new_tokens=100
            )
    
    async def process_document(
        self,
        image_path: str,
        options: Dict[str, Any] = None
    ) -> ProcessingResult:
        """Process single document with DeepSeek"""
        
        if not self.is_loaded:
            await self.load_model()
        
        start_time = time.time()
        
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Prepare prompt based on document type
        doc_type = options.get('document_type', 'unknown')
        prompt = self._get_prompt_for_type(doc_type)
        
        # Process
        inputs = self.processor(
            text=prompt,
            images=image,
            return_tensors="pt"
        ).to(self.device, dtype=self.dtype)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=2048,
                do_sample=False,
                temperature=None,
                top_p=None
            )
        
        # Decode
        generated_text = self.processor.batch_decode(
            outputs,
            skip_special_tokens=True
        )[0]
        
        # Parse structured output
        parsed_result = self._parse_output(generated_text)
        
        processing_time = time.time() - start_time
        
        return ProcessingResult(
            text=parsed_result['text'],
            confidence=parsed_result['confidence'],
            layout=parsed_result['layout'],
            tables=parsed_result['tables'],
            metadata={
                'model': 'deepseek-janus-pro-1b',
                'document_type': doc_type,
                'image_size': image.size
            },
            processing_time=processing_time,
            backend_used='deepseek'
        )
    
    async def process_batch(
        self,
        image_paths: List[str],
        options: Dict[str, Any] = None
    ) -> List[ProcessingResult]:
        """Batch processing (max 4 images for memory)"""
        
        if len(image_paths) > 4:
            # Process in chunks
            results = []
            for i in range(0, len(image_paths), 4):
                chunk = image_paths[i:i+4]
                chunk_results = await self._process_batch_chunk(chunk, options)
                results.extend(chunk_results)
            return results
        else:
            return await self._process_batch_chunk(image_paths, options)
    
    def _get_prompt_for_type(self, doc_type: str) -> str:
        """Get specialized prompt based on document type"""
        prompts = {
            'invoice': """Extract all information from this invoice in structured format:
- Invoice number
- Date
- Supplier information
- Line items (with quantities, prices)
- Total amount
- Any special notes or annotations""",
            
            'contract': """Extract key information from this contract:
- Contract parties
- Contract number
- Key dates
- Main terms and conditions
- Signatures""",
            
            'unknown': """Extract all text from this document preserving structure and layout."""
        }
        return prompts.get(doc_type, prompts['unknown'])
    
    def _parse_output(self, text: str) -> Dict[str, Any]:
        """Parse model output into structured format"""
        # TODO: Implement sophisticated parsing
        # For now, simple structure
        return {
            'text': text,
            'confidence': 0.95,  # TODO: Calculate actual confidence
            'layout': {},
            'tables': []
        }
    
    def health_check(self) -> bool:
        """Check if backend is operational"""
        return self.is_loaded and torch.cuda.is_available()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return backend metrics"""
        if not torch.cuda.is_available():
            return {}
            
        return {
            'vram_allocated': torch.cuda.memory_allocated() / 1024**3,
            'vram_reserved': torch.cuda.memory_reserved() / 1024**3,
            'is_loaded': self.is_loaded,
            'device': str(self.device)
        }
GPU Backend B: GOT-OCR Implementation
python# /backend/gpu/got_ocr_backend.py

import torch
from transformers import AutoModel, AutoTokenizer
from PIL import Image
import time
from typing import Dict, Any, List
from ..core.base_backend import BaseOCRBackend, ProcessingResult

class GOTOCRBackend(BaseOCRBackend):
    """GOT-OCR 2.0 Backend for fast text extraction"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_name = "ucaslcl/GOT-OCR2_0"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
    async def load_model(self):
        """Load GOT-OCR model"""
        if self.is_loaded:
            return
            
        print(f"Loading GOT-OCR 2.0 on {self.device}...")
        start_time = time.time()
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True
        )
        
        self.model = AutoModel.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            device_map="auto",
            trust_remote_code=True
        ).eval()
        
        load_time = time.time() - start_time
        print(f"GOT-OCR loaded in {load_time:.2f}s")
        print(f"VRAM usage: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
        
        self.is_loaded = True
        
    async def unload_model(self):
        """Unload model"""
        if not self.is_loaded:
            return
            
        del self.model
        del self.tokenizer
        torch.cuda.empty_cache()
        
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        
        print("GOT-OCR unloaded")
    
    async def process_document(
        self,
        image_path: str,
        options: Dict[str, Any] = None
    ) -> ProcessingResult:
        """Fast OCR with GOT-OCR 2.0"""
        
        if not self.is_loaded:
            await self.load_model()
        
        start_time = time.time()
        
        # GOT-OCR specific inference
        result_text = self.model.chat(
            self.tokenizer,
            image_path,
            ocr_type='ocr'  # or 'format' for formatted output
        )
        
        processing_time = time.time() - start_time
        
        return ProcessingResult(
            text=result_text,
            confidence=0.92,  # GOT-OCR doesn't provide confidence
            layout={},  # Extract from output if needed
            tables=[],  # Can be parsed from formatted output
            metadata={
                'model': 'got-ocr-2.0',
                'ocr_type': 'ocr'
            },
            processing_time=processing_time,
            backend_used='got_ocr'
        )
    
    async def process_batch(
        self,
        image_paths: List[str],
        options: Dict[str, Any] = None
    ) -> List[ProcessingResult]:
        """Batch processing (sequential for GOT-OCR)"""
        results = []
        for path in image_paths:
            result = await self.process_document(path, options)
            results.append(result)
        return results
    
    def health_check(self) -> bool:
        return self.is_loaded and torch.cuda.is_available()
    
    def get_metrics(self) -> Dict[str, Any]:
        if not torch.cuda.is_available():
            return {}
            
        return {
            'vram_allocated': torch.cuda.memory_allocated() / 1024**3,
            'vram_reserved': torch.cuda.memory_reserved() / 1024**3,
            'is_loaded': self.is_loaded,
            'device': str(self.device)
        }
CPU Backend: Surya + Docling
python# /backend/cpu/surya_docling_backend.py

from surya.ocr import run_ocr
from surya.model.detection.model import load_model as load_det_model, load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor
from docling.document_converter import DocumentConverter
from PIL import Image
import time
from typing import Dict, Any, List
from ..core.base_backend import BaseOCRBackend, ProcessingResult

class SuryaDoclingBackend(BaseOCRBackend):
    """CPU-based OCR using Surya + Docling"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.langs = config.get('languages', ['de', 'en'])
        
    async def load_model(self):
        """Load Surya models"""
        if self.is_loaded:
            return
            
        print("Loading Surya models (CPU)...")
        start_time = time.time()
        
        # Load detection model
        self.det_model = load_det_model()
        self.det_processor = load_det_processor()
        
        # Load recognition model
        self.rec_model = load_rec_model()
        self.rec_processor = load_rec_processor()
        
        # Load Docling
        self.docling_converter = DocumentConverter()
        
        load_time = time.time() - start_time
        print(f"Surya + Docling loaded in {load_time:.2f}s")
        
        self.is_loaded = True
        
    async def unload_model(self):
        """Unload models"""
        # Models are lightweight, can keep loaded
        pass
    
    async def process_document(
        self,
        image_path: str,
        options: Dict[str, Any] = None
    ) -> ProcessingResult:
        """Process with Surya + Docling"""
        
        if not self.is_loaded:
            await self.load_model()
        
        start_time = time.time()
        
        # Load image
        image = Image.open(image_path)
        
        # Run Surya OCR
        predictions = run_ocr(
            [image],
            [self.langs],
            self.det_model,
            self.det_processor,
            self.rec_model,
            self.rec_processor
        )
        
        # Extract text and layout
        ocr_result = predictions[0]
        
        # Use Docling for layout analysis
        docling_result = self.docling_converter.convert(image_path)
        
        processing_time = time.time() - start_time
        
        return ProcessingResult(
            text=self._extract_text(ocr_result),
            confidence=self._calculate_confidence(ocr_result),
            layout=self._extract_layout(docling_result),
            tables=self._extract_tables(docling_result),
            metadata={
                'model': 'surya + docling',
                'languages': self.langs
            },
            processing_time=processing_time,
            backend_used='cpu_surya'
        )
    
    async def process_batch(
        self,
        image_paths: List[str],
        options: Dict[str, Any] = None
    ) -> List[ProcessingResult]:
        """Batch processing on CPU"""
        # Load all images
        images = [Image.open(path) for path in image_paths]
        
        # Batch OCR
        predictions = run_ocr(
            images,
            [self.langs] * len(images),
            self.det_model,
            self.det_processor,
            self.rec_model,
            self.rec_processor
        )
        
        # Process each result
        results = []
        for i, (path, prediction) in enumerate(zip(image_paths, predictions)):
            # Individual docling processing
            docling_result = self.docling_converter.convert(path)
            
            result = ProcessingResult(
                text=self._extract_text(prediction),
                confidence=self._calculate_confidence(prediction),
                layout=self._extract_layout(docling_result),
                tables=self._extract_tables(docling_result),
                metadata={'model': 'surya + docling'},
                processing_time=0,  # Calculated in batch
                backend_used='cpu_surya'
            )
            results.append(result)
        
        return results
    
    def _extract_text(self, ocr_result) -> str:
        """Extract plain text from Surya result"""
        text_lines = []
        for text_line in ocr_result.text_lines:
            text_lines.append(text_line.text)
        return '\n'.join(text_lines)
    
    def _calculate_confidence(self, ocr_result) -> float:
        """Calculate average confidence"""
        if not ocr_result.text_lines:
            return 0.0
        confidences = [line.confidence for line in ocr_result.text_lines]
        return sum(confidences) / len(confidences)
    
    def _extract_layout(self, docling_result) -> Dict[str, Any]:
        """Extract layout from Docling"""
        # TODO: Parse docling structure
        return {}
    
    def _extract_tables(self, docling_result) -> List[Dict[str, Any]]:
        """Extract tables from Docling"""
        # TODO: Parse tables
        return []
    
    def health_check(self) -> bool:
        return self.is_loaded
    
    def get_metrics(self) -> Dict[str, Any]:
        import psutil
        return {
            'ram_usage': psutil.virtual_memory().percent,
            'cpu_usage': psutil.cpu_percent(),
            'is_loaded': self.is_loaded
        }

🎛️ ORCHESTRATOR - Intelligentes Routing
python# /backend/orchestrator/router.py

import asyncio
from typing import Dict, Any, Optional
from enum import Enum
from ..core.base_backend import ProcessingResult
from ..gpu.deepseek_backend import DeepSeekBackend
from ..gpu.got_ocr_backend import GOTOCRBackend
from ..cpu.surya_docling_backend import SuryaDoclingBackend

class BackendType(Enum):
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    CPU_SURYA = "cpu_surya"

class DocumentComplexity(Enum):
    SIMPLE = 1      # Clean scans, standard layouts
    MODERATE = 2    # Some variations, decent quality
    COMPLEX = 3     # Multiple layouts, poor quality, handwriting

class IntelligentRouter:
    """Smart routing zwischen backends basierend auf Document-Eigenschaften"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Initialize backends
        self.backends = {
            BackendType.DEEPSEEK: DeepSeekBackend(config.get('deepseek', {})),
            BackendType.GOT_OCR: GOTOCRBackend(config.get('got_ocr', {})),
            BackendType.CPU_SURYA: SuryaDoclingBackend(config.get('cpu', {}))
        }
        
        # Current active GPU backend
        self.active_gpu_backend: Optional[BackendType] = None
        self.gpu_lock = asyncio.Lock()
        
        # Backend health tracking
        self.backend_health = {
            backend: True for backend in BackendType
        }
        
        # Queue counters
        self.queue_depth = {
            backend: 0 for backend in BackendType
        }
        
    async def route_document(
        self,
        image_path: str,
        options: Dict[str, Any] = None
    ) -> ProcessingResult:
        """Route document to optimal backend"""
        
        # 1. Analyze document
        complexity = await self._analyze_complexity(image_path, options)
        doc_type = options.get('document_type', 'unknown')
        
        # 2. Determine optimal backend
        target_backend = self._select_backend(
            complexity,
            doc_type,
            options.get('force_backend')
        )
        
        # 3. Check if GPU switch needed
        if target_backend in [BackendType.DEEPSEEK, BackendType.GOT_OCR]:
            await self._ensure_gpu_backend(target_backend)
        
        # 4. Process
        backend = self.backends[target_backend]
        
        self.queue_depth[target_backend] += 1
        try:
            result = await backend.process_document(image_path, options)
        finally:
            self.queue_depth[target_backend] -= 1
        
        return result
    
    async def _analyze_complexity(
        self,
        image_path: str,
        options: Optional[Dict[str, Any]]
    ) -> DocumentComplexity:
        """Analyze document complexity"""
        
        # If user specified, trust them
        if options and 'complexity' in options:
            return DocumentComplexity[options['complexity'].upper()]
        
        # Quick image analysis
        from PIL import Image
        import numpy as np
        
        img = Image.open(image_path).convert('L')  # Grayscale
        img_array = np.array(img)
        
        # Simple heuristics
        score = 0
        
        # Check image quality (variance as proxy)
        variance = np.var(img_array)
        if variance < 1000:  # Low variance = poor quality
            score += 2
        
        # Check size (very large = complex)
        if img.size[0] * img.size[1] > 4000000:  # >4MP
            score += 1
        
        # Check if very small (potentially scan quality issues)
        if img.size[0] * img.size[1] < 500000:  # <0.5MP
            score += 1
        
        # Map score to complexity
        if score == 0:
            return DocumentComplexity.SIMPLE
        elif score <= 2:
            return DocumentComplexity.MODERATE
        else:
            return DocumentComplexity.COMPLEX
    
    def _select_backend(
        self,
        complexity: DocumentComplexity,
        doc_type: str,
        force_backend: Optional[str] = None
    ) -> BackendType:
        """Select optimal backend based on document properties"""
        
        # User override
        if force_backend:
            return BackendType[force_backend.upper()]
        
        # Decision tree
        if complexity == DocumentComplexity.COMPLEX:
            # Complex docs always to DeepSeek
            if self.backend_health[BackendType.DEEPSEEK]:
                return BackendType.DEEPSEEK
            else:
                # Fallback to CPU
                return BackendType.CPU_SURYA
        
        elif complexity == DocumentComplexity.SIMPLE:
            # Simple docs to fast GOT-OCR
            if self.backend_health[BackendType.GOT_OCR]:
                return BackendType.GOT_OCR
            else:
                return BackendType.CPU_SURYA
        
        else:  # MODERATE
            # Check queue depth
            if self.queue_depth[BackendType.DEEPSEEK] < 5:
                return BackendType.DEEPSEEK
            elif self.queue_depth[BackendType.GOT_OCR] < 10:
                return BackendType.GOT_OCR
            else:
                # GPU busy, use CPU
                return BackendType.CPU_SURYA
    
    async def _ensure_gpu_backend(self, target: BackendType):
        """Ensure correct GPU backend is loaded"""
        
        async with self.gpu_lock:
            if self.active_gpu_backend == target:
                # Already loaded
                return
            
            # Need to switch
            if self.active_gpu_backend:
                # Unload current
                current = self.backends[self.active_gpu_backend]
                await current.unload_model()
            
            # Load new
            new_backend = self.backends[target]
            await new_backend.load_model()
            
            self.active_gpu_backend = target
            
            print(f"GPU backend switched to: {target.value}")
    
    async def health_check_all(self):
        """Check health of all backends"""
        for backend_type, backend in self.backends.items():
            self.backend_health[backend_type] = backend.health_check()
        
        return self.backend_health
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics"""
        return {
            'active_gpu_backend': self.active_gpu_backend.value if self.active_gpu_backend else None,
            'backend_health': {k.value: v for k, v in self.backend_health.items()},
            'queue_depth': {k.value: v for k, v in self.queue_depth.items()},
            'backend_metrics': {
                backend_type.value: backend.get_metrics()
                for backend_type, backend in self.backends.items()
            }
        }

🌐 FastAPI Application
python# /api/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid
import aiofiles
from pathlib import Path

from backend.orchestrator.router import IntelligentRouter, BackendType
from backend.core.base_backend import ProcessingResult

app = FastAPI(
    title="Intelligent Document Processing API",
    version="1.0.0",
    description="Multi-backend OCR system with intelligent routing"
)

# Initialize router
config = {
    'deepseek': {},
    'got_ocr': {},
    'cpu': {'languages': ['de', 'en']}
}
router = IntelligentRouter(config)

# Storage
UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory job store (use Redis in production)
jobs = {}

class ProcessingJob(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    result: Optional[ProcessingResult] = None
    error: Optional[str] = None

@app.on_event("startup")
async def startup():
    """Initialize backends on startup"""
    print("Initializing OCR system...")
    # Pre-load CPU backend (always available)
    await router.backends[BackendType.CPU_SURYA].load_model()
    print("System ready!")

@app.post("/api/v1/ocr/process")
async def process_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = None,
    complexity: Optional[str] = None,
    force_backend: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Process a single document
    
    Parameters:
    - file: PDF or image file
    - document_type: invoice, contract, etc.
    - complexity: simple, moderate, complex
    - force_backend: deepseek, got_ocr, cpu_surya
    """
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Save file
    file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Create job
    job = ProcessingJob(
        job_id=job_id,
        status="pending"
    )
    jobs[job_id] = job
    
    # Process in background
    background_tasks.add_task(
        process_job,
        job_id,
        str(file_path),
        {
            'document_type': document_type,
            'complexity': complexity,
            'force_backend': force_backend
        }
    )
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Document submitted for processing"
    }

async def process_job(job_id: str, file_path: str, options: dict):
    """Background job processor"""
    job = jobs[job_id]
    job.status = "processing"
    
    try:
        result = await router.route_document(file_path, options)
        job.result = result
        job.status = "completed"
    except Exception as e:
        job.error = str(e)
        job.status = "failed"
    finally:
        # Cleanup file
        Path(file_path).unlink(missing_ok=True)

@app.get("/api/v1/ocr/status/{job_id}")
async def get_job_status(job_id: str):
    """Get processing status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return jobs[job_id]

@app.get("/api/v1/health")
async def health_check():
    """System health check"""
    health = await router.health_check_all()
    metrics = router.get_system_metrics()
    
    return {
        "status": "healthy" if any(health.values()) else "degraded",
        "backends": health,
        "metrics": metrics
    }

@app.post("/api/v1/admin/switch-gpu-backend")
async def switch_gpu_backend(backend: str):
    """Manually switch GPU backend"""
    try:
        backend_type = BackendType[backend.upper()]
        await router._ensure_gpu_backend(backend_type)
        return {"status": "success", "active_backend": backend}
    except KeyError:
        raise HTTPException(status_code=400, detail="Invalid backend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
