# Ablage-System: Enterprise Frontend Implementation Guide

**Phase 1 abgeschlossen** – dieses Dokument konzentriert sich auf die technische Umsetzung von **Phase 2** (Monate 3-4) und **Phase 3** (Monate 5-6) mit maximaler Detailtiefe, produktionsreifen Code-Beispielen und einer unverwechselbaren visuellen Identität nach dem Prinzip "German Engineering Aesthetic".

---

## Design-Philosophie: German Enterprise Premium

Das Ablage-System folgt einer **Bauhaus-inspirierten Präzisionsästhetik**, die sich fundamental von generischen SaaS-Designs unterscheidet. Statt lila Gradienten auf weißem Hintergrund verkörpert das System die Werte deutscher Ingenieurskunst: **Präzision, Klarheit und subtile Raffinesse**.

Die visuelle Identität basiert auf dem Konzept **"Industrial Precision"** – einer Symbiose aus der Sachlichkeit des Schweizer Stils und der experimentellen Energie des Bauhaus. Jedes Interface-Element kommuniziert Zuverlässigkeit und technische Kompetenz, während dezente Animationen und durchdachte Micro-Interactions ein Gefühl von Lebendigkeit erzeugen.

### Distinctive Typography: Clash Display + Satoshi

**VERBOTEN** sind generische System-Fonts wie Inter, Roboto, Arial oder San Francisco. Das Ablage-System verwendet charaktervolle, einzigartige Font-Pairings:

**Display Font: Clash Display** (Indian Type Foundry via Fontshare)
- Neo-grotesk Display-Typeface für Headlines und große Zahlen
- Verfügbare Weights: Extralight bis Bold mit Variable Font
- Hoher Stroke-Contrast mit "pinched" Verbindungen in schweren Gewichten
- Kostenlos für kommerzielle Nutzung (ITF Free Font License)

**Body Font: Satoshi** (Indian Type Foundry via Fontshare)
- Swiss-style modernist Sans-Serif für Fließtext und UI-Elemente
- 10 Styles (Light bis Black mit Italics) plus Variable Font
- Elegante Balance zwischen runden und scharfwinkligen Details
- 506 Glyphen mit vollständiger deutscher Sprachunterstützung

**Data/Tables: Plus Jakarta Sans** (Google Fonts, SIL OFL)
- Geometrischer Sans-Serif mit excellenten Tabular Figures
- Variable Font für Performance-Optimierung

```css
/* Typography Scale (Major Second 1.125 Ratio) */
:root {
  --font-display: 'Clash Display', sans-serif;
  --font-body: 'Satoshi', sans-serif;
  --font-data: 'Plus Jakarta Sans', sans-serif;

  --text-xs: 0.625rem;    /* 10px */
  --text-sm: 0.75rem;     /* 12px */
  --text-base: 0.875rem;  /* 14px */
  --text-md: 1rem;        /* 16px */
  --text-lg: 1.125rem;    /* 18px */
  --text-xl: 1.25rem;     /* 20px */
  --text-2xl: 1.5rem;     /* 24px */
  --text-3xl: 1.875rem;   /* 30px */
  --text-4xl: 2.25rem;    /* 36px */
  --text-5xl: 3rem;       /* 48px */
}
```

---

## Design System Spezifikation

### CSS Variable Definitionen (OKLCH Color Space)

```css
@layer base {
  :root {
    --radius: 0.5rem;

    /* Core Palette - German Industrial */
    --background: oklch(0.985 0.002 250);
    --foreground: oklch(0.145 0.004 250);

    /* Primary - Deep Industrial Blue */
    --primary: oklch(0.35 0.08 250);
    --primary-foreground: oklch(0.985 0 0);

    /* Accent - Precision Yellow */
    --accent: oklch(0.88 0.16 85);
    --accent-foreground: oklch(0.25 0.04 85);

    /* Semantic Colors */
    --destructive: oklch(0.55 0.22 25);
    --warning: oklch(0.82 0.15 75);
    --success: oklch(0.72 0.17 145);

    /* Chart Colors */
    --chart-1: oklch(0.55 0.18 250);
    --chart-2: oklch(0.72 0.17 145);
    --chart-3: oklch(0.82 0.15 75);
    --chart-4: oklch(0.55 0.22 25);
    --chart-5: oklch(0.65 0.12 320);

    /* Sidebar - Dark Theme */
    --sidebar: oklch(0.12 0.02 250);
    --sidebar-foreground: oklch(0.92 0.01 250);
    --sidebar-primary: oklch(0.88 0.16 85);
  }

  .dark {
    --background: oklch(0.12 0.02 250);
    --foreground: oklch(0.92 0.01 250);
    --primary: oklch(0.88 0.16 85);
    --primary-foreground: oklch(0.12 0.02 250);
  }
}
```

### Animation Timing Tokens

```typescript
// src/lib/motion-tokens.ts
export const motionTokens = {
  duration: {
    instant: 0,
    faster: 0.1,
    fast: 0.15,
    normal: 0.3,
    slow: 0.5,
    slower: 0.8
  },

  easing: {
    standard: [0.4, 0, 0.2, 1],
    emphasized: [0.2, 0, 0, 1],
    industrial: [0.25, 0.1, 0.25, 1],
    bauhaus: [0.61, 1, 0.88, 1]
  },

  spring: {
    snappy: { stiffness: 400, damping: 30 },
    gentle: { stiffness: 100, damping: 15, mass: 0.5 },
    smooth: { stiffness: 200, damping: 20 },
    responsive: { stiffness: 500, damping: 25, mass: 0.5 }
  },

  stagger: {
    fast: 0.05,
    normal: 0.1,
    slow: 0.15
  }
} as const;
```

### Visual Effects: Noise Textures &amp; Glassmorphism

```css
.noise-overlay::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.03;
  pointer-events: none;
}

.glass-card {
  background: oklch(1 0 0 / 0.7);
  backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid oklch(1 0 0 / 0.2);
}
```

---

## Phase 2: Core Features (Monat 3-4)

### 2.1 Dokumentenliste &amp; Grid View

Die Dokumentenliste kombiniert **virtualisiertes Rendering** mit **orchestrierten Animationen**.

```typescript
// src/features/documents/components/DocumentGrid.tsx
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion, AnimatePresence } from 'framer-motion';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 200, damping: 20 }
  }
};

export function DocumentGrid({ documents, viewMode, selectedIds, onSelect }) {
  const parentRef = useRef(null);
  const columnCount = viewMode === 'grid' ? 4 : 1;

  const rowVirtualizer = useVirtualizer({
    count: Math.ceil(documents.length / columnCount),
    getScrollElement: () => parentRef.current,
    estimateSize: () => viewMode === 'grid' ? 280 : 72,
    overscan: 3
  });

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        style={{ height: rowVirtualizer.getTotalSize() }}
      >
        <AnimatePresence mode="popLayout">
          {rowVirtualizer.getVirtualItems().map(virtualRow => (
            <motion.div
              key={virtualRow.key}
              variants={itemVariants}
              className={viewMode === 'grid' ? 'grid grid-cols-4 gap-4' : 'flex flex-col'}
              style={{ transform: `translateY(${virtualRow.start}px)` }}
            >
              {/* Document cards rendered here */}
            </motion.div>
          ))}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
```

### Document Card mit Hover-Effekten

```typescript
// src/features/documents/components/DocumentCard.tsx
const cardVariants = {
  idle: { scale: 1, boxShadow: 'var(--shadow-sm)', y: 0 },
  hover: {
    scale: 1.02,
    boxShadow: 'var(--shadow-lg)',
    y: -4,
    transition: { type: 'spring', stiffness: 400, damping: 25 }
  },
  tap: { scale: 0.98 },
  selected: { boxShadow: '0 0 0 2px var(--primary)' }
};

export function DocumentCard({ document, isSelected, onClick, onDoubleClick }) {
  return (
    <motion.div
      variants={cardVariants}
      initial="idle"
      whileHover="hover"
      whileTap="tap"
      animate={isSelected ? 'selected' : 'idle'}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className="relative group cursor-pointer rounded-lg overflow-hidden bg-card border"
    >
      <div className="absolute top-3 left-3 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
        <Checkbox checked={isSelected} />
      </div>

      <div className="aspect-[4/3] bg-muted overflow-hidden">
        {document.thumbnail ? (
          <img src={document.thumbnail} loading="lazy" className="w-full h-full object-cover" />
        ) : (
          <DocumentTypeIcon mimeType={document.mimeType} />
        )}
      </div>

      <div className="p-3">
        <h3 className="font-medium text-sm truncate">{document.name}</h3>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{formatDate(document.createdAt)}</span>
          <OCRStatusBadge status={document.ocrStatus} confidence={document.ocrConfidence} />
        </div>
      </div>
    </motion.div>
  );
}
```

### 2.2 Smart Upload Workflow

Multi-Step Wizard mit Drag-and-Drop und OCR-Backend-Auswahl.

```typescript
// src/features/upload/components/UploadDropzone.tsx
import { useDropzone } from 'react-dropzone';
import { motion } from 'framer-motion';

const dropzoneVariants = {
  idle: { borderColor: 'var(--border)', scale: 1 },
  active: {
    borderColor: 'var(--primary)',
    backgroundColor: 'oklch(0.35 0.08 250 / 0.05)',
    scale: 1.01
  },
  reject: { borderColor: 'var(--destructive)' }
};

export function UploadDropzone({ files, onFilesAdd, onFileRemove }) {
  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop: onFilesAdd,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg']
    },
    maxSize: 50 * 1024 * 1024
  });

  return (
    <motion.div
      {...getRootProps()}
      variants={dropzoneVariants}
      animate={isDragReject ? 'reject' : isDragActive ? 'active' : 'idle'}
      className="border-2 border-dashed rounded-xl p-12 cursor-pointer flex flex-col items-center"
    >
      <input {...getInputProps()} />
      <Upload className="w-16 h-16 text-primary mb-4" />
      <p className="text-lg font-medium">
        {isDragActive ? 'Dateien hier ablegen' : 'Dateien hierher ziehen oder klicken'}
      </p>
      <p className="text-sm text-muted-foreground">PDF, PNG, JPG • Max. 50MB</p>
    </motion.div>
  );
}
```

### OCR Backend Selector (Visual Cards)

```typescript
// src/features/upload/components/OCRBackendSelector.tsx
const backends = [
  {
    id: 'got-ocr',
    name: 'GOT-OCR 2.0',
    description: 'State-of-the-art unified OCR mit Layout-Erkennung',
    features: ['LaTeX-Formeln', 'Tabellen', 'Bounding Boxes'],
    accuracy: 98,
    languages: 25,
    recommended: true,
    gpuRequired: true
  },
  {
    id: 'surya-docling',
    name: 'Surya + Docling',
    description: 'Multilingual OCR mit Document Understanding',
    features: ['90+ Sprachen', 'Tabellen-Extraktion'],
    accuracy: 96,
    languages: 90,
    gpuRequired: true
  },
  {
    id: 'deepseek-janus',
    name: 'DeepSeek Janus',
    description: 'Vision-Language Model für komplexe Dokumente',
    features: ['Kontextverständnis', 'Reasoning'],
    accuracy: 94,
    gpuRequired: true
  }
];

export function OCRBackendSelector({ selectedId, onSelect, gpuAvailable }) {
  return (
    <div className="grid grid-cols-2 gap-4">
      {backends.map((backend) => (
        <motion.button
          key={backend.id}
          whileHover={{ scale: 1.02 }}
          animate={selectedId === backend.id ? { boxShadow: '0 0 0 2px var(--primary)' } : {}}
          onClick={() => onSelect(backend.id)}
          disabled={backend.gpuRequired &amp;&amp; !gpuAvailable}
          className="relative text-left p-4 rounded-xl border bg-card"
        >
          {backend.recommended &amp;&amp; <Badge className="absolute top-3 left-3">Empfohlen</Badge>}
          <div className="pt-6 space-y-3">
            <h3 className="font-semibold">{backend.name}</h3>
            <p className="text-xs text-muted-foreground">{backend.description}</p>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="p-2 rounded-lg bg-muted/50">
                <div className="text-lg font-bold">{backend.accuracy}%</div>
                <div className="text-xs">Genauigkeit</div>
              </div>
            </div>
          </div>
        </motion.button>
      ))}
    </div>
  );
}
```

### 2.3 Split-Screen Document Viewer

PDF.js Integration mit synchronisiertem Scrollen und OCR-Bounding-Box-Overlay.

```typescript
// src/features/viewer/components/SplitDocumentViewer.tsx
import { Document, Page, pdfjs } from 'react-pdf';
import { ScrollSync, ScrollSyncPane } from 'react-scroll-sync';
import SplitPane from 'react-split-pane';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString();

export function SplitDocumentViewer({ documentId, ocrResults }) {
  const [numPages, setNumPages] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [selectedBox, setSelectedBox] = useState(null);

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <ViewerToolbar
        currentPage={currentPage}
        numPages={numPages}
        scale={scale}
        onPageChange={setCurrentPage}
        onZoomIn={() => setScale(s => Math.min(s + 0.25, 3))}
        onZoomOut={() => setScale(s => Math.max(s - 0.25, 0.5))}
      />

      {/* Split View */}
      <ScrollSync>
        <SplitPane split="vertical" minSize={300} defaultSize="50%">
          {/* PDF Panel */}
          <ScrollSyncPane>
            <div className="h-full overflow-auto bg-muted/30">
              <Document
                file={`/api/documents/${documentId}/file`}
                onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              >
                <div className="relative">
                  <Page
                    pageNumber={currentPage}
                    scale={scale}
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                  />
                  <BoundingBoxOverlay
                    boxes={ocrResults?.pages?.[currentPage - 1]?.boxes || []}
                    scale={scale}
                    selectedBox={selectedBox}
                    onBoxClick={setSelectedBox}
                  />
                </div>
              </Document>
            </div>
          </ScrollSyncPane>

          {/* OCR Text Panel */}
          <ScrollSyncPane>
            <div className="h-full overflow-auto p-6 bg-background">
              <OCRTextPanel
                ocrData={ocrResults?.pages?.[currentPage - 1]}
                selectedBox={selectedBox}
                onBoxSelect={setSelectedBox}
                onTextEdit={handleTextEdit}
              />
            </div>
          </ScrollSyncPane>
        </SplitPane>
      </ScrollSync>
    </div>
  );
}
```

### Bounding Box Overlay System

```typescript
// src/features/viewer/components/BoundingBoxOverlay.tsx
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.95) return 'oklch(0.72 0.17 145)'; // Green
  if (confidence >= 0.85) return 'oklch(0.82 0.15 75)';  // Yellow
  if (confidence >= 0.70) return 'oklch(0.75 0.18 50)';  // Orange
  return 'oklch(0.55 0.22 25)'; // Red
}

export function BoundingBoxOverlay({ boxes, scale, selectedBox, onBoxClick }) {
  return (
    <svg
      className="absolute top-0 left-0 pointer-events-none"
      style={{ width: '100%', height: '100%' }}
    >
      {boxes.map((box, idx) => (
        <g key={idx}>
          <motion.rect
            x={box.x * scale}
            y={box.y * scale}
            width={box.width * scale}
            height={box.height * scale}
            fill={getConfidenceColor(box.confidence)}
            fillOpacity={selectedBox?.id === box.id ? 0.4 : 0.15}
            stroke={getConfidenceColor(box.confidence)}
            strokeWidth={selectedBox?.id === box.id ? 3 : 1}
            style={{ pointerEvents: 'all', cursor: 'pointer' }}
            onClick={() => onBoxClick(box)}
            whileHover={{ fillOpacity: 0.3, strokeWidth: 2 }}
          />
          {box.confidence &lt; 0.85 &amp;&amp; (
            <text
              x={box.x * scale}
              y={(box.y - 4) * scale}
              fontSize={10}
              fill={getConfidenceColor(box.confidence)}
            >
              {Math.round(box.confidence * 100)}% ⚠️
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
```

### 2.4 Job Queue Dashboard

Real-time WebSocket Updates mit Drag-to-Reorder.

```typescript
// src/features/jobs/components/JobQueueDashboard.tsx
import { DndContext, closestCenter } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import useWebSocket from 'react-use-websocket';

export function JobQueueDashboard() {
  const [jobs, setJobs] = useState([]);

  const { lastJsonMessage } = useWebSocket('ws://api/jobs/stream', {
    shouldReconnect: () => true,
    reconnectInterval: 3000,
    onMessage: (event) => {
      const update = JSON.parse(event.data);
      setJobs(prev => updateJobsWithMessage(prev, update));
    }
  });

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (active.id !== over.id) {
      const oldIndex = jobs.findIndex(j => j.id === active.id);
      const newIndex = jobs.findIndex(j => j.id === over.id);
      const newJobs = arrayMove(jobs, oldIndex, newIndex);
      setJobs(newJobs);
      api.reorderJobs(newJobs.map(j => j.id));
    }
  };

  return (
    <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={jobs} strategy={verticalListSortingStrategy}>
        <motion.div
          variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
          initial="hidden"
          animate="visible"
        >
          {jobs.map(job => (
            <SortableJobItem key={job.id} job={job} />
          ))}
        </motion.div>
      </SortableContext>
    </DndContext>
  );
}

function SortableJobItem({ job }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: job.id });
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      variants={{ hidden: { opacity: 0, x: -20 }, visible: { opacity: 1, x: 0 } }}
      className="border rounded-lg mb-2 bg-card"
    >
      <div className="flex items-center gap-3 p-4" {...attributes} {...listeners}>
        <GripVertical className="w-5 h-5 text-muted-foreground cursor-grab" />
        <StatusIndicator status={job.status} />
        <div className="flex-1">
          <h4 className="font-medium">{job.name}</h4>
          <p className="text-sm text-muted-foreground">{job.documentName}</p>
        </div>
        <Progress value={job.progress} className="w-24" />
        <span className="text-sm">{job.progress}%</span>
        <Button variant="ghost" size="icon" onClick={() => setExpanded(!expanded)}>
          <ChevronDown className={cn("transition-transform", expanded &amp;&amp; "rotate-180")} />
        </Button>
      </div>

      <AnimatePresence>
        {expanded &amp;&amp; (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="px-4 pb-4 border-t"
          >
            <JobDetailsPanel job={job} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
```

---

## Phase 3: Advanced Features (Monat 5-6)

### 3.1 GPU Monitoring Dashboard

Live Gauge Components mit Recharts Time Series.

```typescript
// src/features/monitoring/components/GPUMonitoringDashboard.tsx
import GaugeComponent from 'react-gauge-component';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export function GPUMonitoringDashboard() {
  const { data: gpuMetrics } = useWebSocket('ws://api/gpu/metrics');
  const [history, setHistory] = useState([]);

  useEffect(() => {
    if (gpuMetrics) {
      setHistory(prev => [...prev.slice(-60), { ...gpuMetrics, time: Date.now() }]);
    }
  }, [gpuMetrics]);

  return (
    <div className="grid grid-cols-3 gap-6">
      {/* GPU Utilization Gauge */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">GPU Auslastung</h3>
        <GaugeComponent
          type="semicircle"
          value={gpuMetrics?.utilization || 0}
          minValue={0}
          maxValue={100}
          arc={{
            subArcs: [
              { limit: 50, color: 'oklch(0.72 0.17 145)' },
              { limit: 80, color: 'oklch(0.82 0.15 75)' },
              { limit: 100, color: 'oklch(0.55 0.22 25)' }
            ]
          }}
          pointer={{ type: 'needle', animate: true }}
          labels={{ valueLabel: { formatTextValue: v => `${v}%` } }}
        />
      </Card>

      {/* VRAM Gauge */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">VRAM</h3>
        <GaugeComponent
          type="semicircle"
          value={gpuMetrics?.vramUsed || 0}
          minValue={0}
          maxValue={gpuMetrics?.vramTotal || 24}
          arc={{
            subArcs: [
              { limit: 16, color: 'oklch(0.72 0.17 145)' },
              { limit: 20, color: 'oklch(0.82 0.15 75)' },
              { limit: 24, color: 'oklch(0.55 0.22 25)' }
            ]
          }}
          labels={{ valueLabel: { formatTextValue: v => `${v}GB` } }}
        />
      </Card>

      {/* Temperature Gauge */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">Temperatur</h3>
        <GaugeComponent
          type="semicircle"
          value={gpuMetrics?.temperature || 0}
          minValue={30}
          maxValue={100}
          arc={{
            subArcs: [
              { limit: 60, color: 'oklch(0.72 0.17 145)' },
              { limit: 80, color: 'oklch(0.82 0.15 75)' },
              { limit: 100, color: 'oklch(0.55 0.22 25)' }
            ]
          }}
          labels={{ valueLabel: { formatTextValue: v => `${v}°C` } }}
        />
      </Card>

      {/* Time Series Chart */}
      <Card className="col-span-3 p-6">
        <h3 className="text-lg font-semibold mb-4">Verlauf (letzte 60 Sekunden)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={history}>
            <XAxis dataKey="time" tickFormatter={t => new Date(t).toLocaleTimeString()} />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Area type="monotone" dataKey="utilization" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.3} name="GPU %" />
            <Area type="monotone" dataKey="vramPercent" stroke="var(--chart-2)" fill="var(--chart-2)" fillOpacity={0.3} name="VRAM %" />
          </AreaChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
```

### 3.2 Automation Rules Engine

Visual Rule Builder mit React Flow.

```typescript
// src/features/automation/components/RuleBuilder.tsx
import { ReactFlow, MiniMap, Controls, Background, useNodesState, useEdgesState, addEdge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

const nodeTypes = {
  trigger: TriggerNode,
  condition: ConditionNode,
  action: ActionNode
};

export function RuleBuilder({ rule, onSave }) {
  const [nodes, setNodes, onNodesChange] = useNodesState(rule?.nodes || []);
  const [edges, setEdges, onEdgesChange] = useEdgesState(rule?.edges || []);

  const onConnect = useCallback((params) => {
    setEdges(eds => addEdge({ ...params, animated: true, style: { stroke: 'var(--primary)' } }, eds));
  }, [setEdges]);

  const onDrop = useCallback((event) => {
    event.preventDefault();
    const type = event.dataTransfer.getData('application/reactflow');
    const position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY });

    const newNode = {
      id: `${type}-${Date.now()}`,
      type,
      position,
      data: { label: getNodeLabel(type), config: {} }
    };
    setNodes(nds => nds.concat(newNode));
  }, []);

  return (
    <div className="flex h-full">
      {/* Node Palette */}
      <div className="w-64 p-4 border-r bg-muted/30">
        <h3 className="font-semibold mb-4">Bausteine</h3>
        <div className="space-y-2">
          <DraggableNode type="trigger" icon={Zap} label="Trigger" />
          <DraggableNode type="condition" icon={GitBranch} label="Bedingung" />
          <DraggableNode type="action" icon={Play} label="Aktion" />
        </div>
      </div>

      {/* Flow Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background variant="dots" gap={20} size={1} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  );
}

function TriggerNode({ data, selected }) {
  return (
    <div className={cn("p-4 rounded-lg border-2 bg-card min-w-[200px]", selected &amp;&amp; "border-primary")}>
      <Handle type="source" position={Position.Bottom} />
      <div className="flex items-center gap-2 mb-2">
        <Zap className="w-4 h-4 text-amber-500" />
        <span className="font-medium">Trigger</span>
      </div>
      <Select value={data.config?.event} onValueChange={(v) => data.onConfigChange({ event: v })}>
        <SelectTrigger><SelectValue placeholder="Event wählen" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="document_uploaded">Dokument hochgeladen</SelectItem>
          <SelectItem value="ocr_completed">OCR abgeschlossen</SelectItem>
          <SelectItem value="schedule">Zeitplan</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
}
```

### 3.3 Search &amp; Filter System

Kombinierte Volltext + Semantische Suche mit Faceted Filters.

```typescript
// src/features/search/components/SearchPanel.tsx
export function SearchPanel({ onSearch, filters, onFiltersChange }) {
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState('hybrid');
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery) onSearch({ query: debouncedQuery, mode: searchMode, filters });
  }, [debouncedQuery, searchMode, filters]);

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Dokumente durchsuchen..."
          className="pl-10 pr-20"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2">
          <ToggleGroup type="single" value={searchMode} onValueChange={setSearchMode}>
            <ToggleGroupItem value="fulltext" size="sm">Text</ToggleGroupItem>
            <ToggleGroupItem value="semantic" size="sm">KI</ToggleGroupItem>
            <ToggleGroupItem value="hybrid" size="sm">Hybrid</ToggleGroupItem>
          </ToggleGroup>
        </div>
      </div>

      {/* Faceted Filters */}
      <div className="flex gap-2 flex-wrap">
        <FilterDropdown
          label="Dokumenttyp"
          options={['PDF', 'Bild', 'Office']}
          selected={filters.type}
          onChange={(v) => onFiltersChange({ ...filters, type: v })}
        />
        <FilterDropdown
          label="OCR-Status"
          options={['Ausstehend', 'Verarbeitet', 'Fehler']}
          selected={filters.ocrStatus}
          onChange={(v) => onFiltersChange({ ...filters, ocrStatus: v })}
        />
        <FilterDropdown
          label="Zeitraum"
          options={['Heute', 'Diese Woche', 'Dieser Monat', 'Dieses Jahr']}
          selected={filters.dateRange}
          onChange={(v) => onFiltersChange({ ...filters, dateRange: v })}
        />
      </div>
    </div>
  );
}
```

### 3.4 Admin Panel mit RBAC

User Management und Audit Logs.

```typescript
// src/features/admin/components/UserManagement.tsx
export function UserManagement() {
  const { data: users, isLoading } = useQuery(['users'], api.getUsers);
  const { can } = usePermissions();

  const columns = [
    { accessorKey: 'email', header: 'E-Mail' },
    { accessorKey: 'name', header: 'Name' },
    { accessorKey: 'role', header: 'Rolle', cell: ({ getValue }) => <RoleBadge role={getValue()} /> },
    { accessorKey: 'lastLogin', header: 'Letzter Login', cell: ({ getValue }) => formatDate(getValue()) },
    {
      id: 'actions',
      cell: ({ row }) => can('edit', 'users') &amp;&amp; (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon"><MoreHorizontal /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onClick={() => openEditDialog(row.original)}>Bearbeiten</DropdownMenuItem>
            {can('delete', 'users') &amp;&amp; (
              <DropdownMenuItem className="text-destructive" onClick={() => confirmDelete(row.original)}>
                Löschen
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )
    }
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Benutzerverwaltung</CardTitle>
        {can('create', 'users') &amp;&amp; <Button onClick={openCreateDialog}><Plus /> Benutzer hinzufügen</Button>}
      </CardHeader>
      <CardContent>
        <DataTable columns={columns} data={users || []} isLoading={isLoading} />
      </CardContent>
    </Card>
  );
}

// RBAC Hook
export function usePermissions() {
  const { user } = useAuth();

  const can = useCallback((action, resource) => {
    if (!user?.permissions) return false;
    return user.permissions.some(p =>
      (p.resource === resource || p.resource === '*') &amp;&amp;
      (p.action === action || p.action === '*' || p.action.includes(action))
    );
  }, [user]);

  return { can };
}
```

---

## App Shell mit Sidebar

```typescript
// src/components/layout/AppShell.tsx
import { motion, AnimatePresence } from 'framer-motion';

const sidebarVariants = {
  expanded: { width: 280, transition: { type: 'spring', stiffness: 300, damping: 30 } },
  collapsed: { width: 72, transition: { type: 'spring', stiffness: 300, damping: 30 } }
};

export function AppShell({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <motion.aside
        variants={sidebarVariants}
        animate={collapsed ? 'collapsed' : 'expanded'}
        className="flex flex-col bg-sidebar text-sidebar-foreground border-r overflow-hidden"
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-sidebar-border">
          <motion.span
            animate={{ opacity: collapsed ? 0 : 1 }}
            className="text-xl font-display font-bold text-sidebar-primary"
          >
            Ablage
          </motion.span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavItem
              key={item.href}
              item={item}
              collapsed={collapsed}
              isActive={pathname === item.href}
            />
          ))}
        </nav>

        {/* Collapse Toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="h-12 flex items-center justify-center border-t border-sidebar-border hover:bg-sidebar-accent transition-colors"
        >
          <motion.div animate={{ rotate: collapsed ? 180 : 0 }}>
            <ChevronLeft className="w-5 h-5" />
          </motion.div>
        </button>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <AnimatePresence mode="wait">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="flex-1 overflow-auto"
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}
```

---

## Testing &amp; Qualität

### Vitest Component Tests

```typescript
// src/features/documents/__tests__/DocumentCard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DocumentCard } from '../components/DocumentCard';

describe('DocumentCard', () => {
  const mockDocument = {
    id: '1',
    name: 'Test Document.pdf',
    mimeType: 'application/pdf',
    createdAt: new Date(),
    ocrStatus: 'complete',
    ocrConfidence: 98
  };

  it('renders document name', () => {
    render(<DocumentCard document={mockDocument} isSelected={false} onClick={vi.fn()} onDoubleClick={vi.fn()} />);
    expect(screen.getByText('Test Document.pdf')).toBeInTheDocument();
  });

  it('shows selected state', () => {
    const { container } = render(<DocumentCard document={mockDocument} isSelected={true} onClick={vi.fn()} onDoubleClick={vi.fn()} />);
    expect(container.firstChild).toHaveClass('ring-2');
  });

  it('calls onClick on click', () => {
    const onClick = vi.fn();
    render(<DocumentCard document={mockDocument} isSelected={false} onClick={onClick} onDoubleClick={vi.fn()} />);
    fireEvent.click(screen.getByText('Test Document.pdf'));
    expect(onClick).toHaveBeenCalled();
  });
});
```

### Playwright E2E Tests

```typescript
// e2e/upload.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Document Upload', () => {
  test('should upload a PDF document', async ({ page }) => {
    await page.goto('/upload');

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('./fixtures/test-document.pdf');

    await expect(page.locator('text=test-document.pdf')).toBeVisible();
    await expect(page.locator('text=Bereit')).toBeVisible();

    await page.click('button:has-text("Weiter")');
    await expect(page.locator('text=OCR-Backend auswählen')).toBeVisible();
  });

  test('should reject invalid file types', async ({ page }) => {
    await page.goto('/upload');

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('./fixtures/invalid.exe');

    await expect(page.locator('text=abgelehnt')).toBeVisible();
  });
});
```

---

## Deployment

### Docker Multi-Stage Build

```dockerfile
# Dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable pnpm &amp;&amp; pnpm install --frozen-lockfile

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED 1
RUN npm run build

FROM nginx:alpine AS runner
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Nginx Configuration

```nginx
# nginx.conf
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    gzip on;
    gzip_types text/plain application/javascript text/css application/json;
}
```

### GitHub Actions CI/CD

```yaml
# .github/workflows/deploy.yml
name: Deploy Frontend

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v2
        with:
          version: 8

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile
      - run: pnpm test
      - run: pnpm build

      - name: Build Docker Image
        run: docker build -t ablage-frontend:${{ github.sha }} .

      - name: Push to Registry
        run: |
          docker tag ablage-frontend:${{ github.sha }} ${{ secrets.REGISTRY }}/ablage-frontend:latest
          docker push ${{ secrets.REGISTRY }}/ablage-frontend:latest
```

---

## Zusammenfassung der Kernkomponenten

| Komponente | Technologie | Status |
|------------|-------------|--------|
| Dokumentenliste | TanStack Virtual + Framer Motion | Phase 2 |
| Upload Wizard | react-dropzone + Multi-Step | Phase 2 |
| Document Viewer | react-pdf + ScrollSync | Phase 2 |
| Job Queue | @dnd-kit + WebSocket | Phase 2 |
| GPU Monitoring | react-gauge-component + Recharts | Phase 3 |
| Rule Builder | React Flow | Phase 3 |
| Search System | Debounced + Faceted Filters | Phase 3 |
| Admin Panel | TanStack Table + RBAC | Phase 3 |

**Empfohlene NPM Packages:**
- `@tanstack/react-virtual` - Virtualisierung
- `@tanstack/react-table` - Data Tables
- `@tanstack/react-query` - Server State
- `framer-motion` / `motion` - Animationen
- `react-pdf` - PDF Rendering
- `@xyflow/react` - Workflow Canvas
- `@dnd-kit/core` - Drag and Drop
- `recharts` - Charts
- `react-gauge-component` - Gauges
- `react-dropzone` - File Upload

Dieses Dokument bietet eine vollständige Entwickler-Referenz für die Enterprise-Grade Frontend-Implementierung des Ablage-Systems mit produktionsreifen Code-Beispielen, einer unverwechselbaren visuellen Identität und detaillierten Spezifikationen für alle Komponenten der Phasen 2 und 3.
