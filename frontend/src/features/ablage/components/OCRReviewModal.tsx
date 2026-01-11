/**
 * OCRReviewModal - SplitView fuer OCR-Review Workflow
 *
 * Layout:
 * ┌────────────────────────────────────────────────────────────────────┐
 * │  OCR-Ergebnis pruefen                                         [X] │
 * ├─────────────────────────────┬──────────────────────────────────────┤
 * │                             │  Ziel: Kunden > Folie > Rechnungen  │
 * │   PDF/Bild Preview          │  ────────────────────────────────── │
 * │   (mit Zoom)                │  Dateiname: [Mueller_RG-001.pdf]    │
 * │                             │  Dokumenttyp: [Eingangsrechnung ▼]  │
 * │                             │  Belegnummer: [RG-2024-001]         │
 * │                             │  Betrag: [1.234,56] [EUR ▼]         │
 * │                             │  Partner: [Mueller GmbH] [95%]      │
 * │                             │  Tags: [Rechnung] [Mueller] [+]     │
 * ├─────────────────────────────┴──────────────────────────────────────┤
 * │                [Abbrechen]   [Speichern & Ablegen]                 │
 * └────────────────────────────────────────────────────────────────────┘
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Loader2,
  Save,
  X,
  FileText,
  CheckCircle2,
  FileWarning,
  Calendar,
  DollarSign,
  Hash,
  Tag,
  Building2,
  Sparkles,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ArrowDownLeft,
  ArrowUpRight,
  CreditCard,
  Building,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type {
  QuickClassificationResult,
  RenameSuggestion,
  UploadCompleteRequest,
  InvoiceDirection,
} from '../types'
import {
  getEntityMatchLevel,
  CUSTOMER_DOCUMENT_TYPES,
  SUPPLIER_DOCUMENT_TYPES,
} from '../types'

// ==================== Types ====================

interface OCRReviewModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void

  // File Info
  file: File | null
  fileUrl: string | null

  // OCR Result
  ocrResult: {
    text: string
    confidence: number
    pageCount: number
  } | null

  // Quick Classification
  quickClassification: QuickClassificationResult | null
  renameSuggestion: RenameSuggestion | null

  // Context
  entityId: string
  entityName: string
  entityType: 'customer' | 'supplier'
  folderId: string
  folderName: string
  category: string
  categoryName: string

  // State
  isSaving: boolean

  // Callbacks
  onSave: (data: Partial<UploadCompleteRequest>) => Promise<void>
  onCancel: () => void
}

// ==================== Helper Components ====================

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const level = getEntityMatchLevel(confidence)
  const percentage = Math.round(confidence * 100)

  return (
    <Badge
      variant="outline"
      className={cn(
        'ml-2 text-xs',
        level === 'high' && 'border-green-500 text-green-700 bg-green-50',
        level === 'medium' && 'border-yellow-500 text-yellow-700 bg-yellow-50',
        level === 'low' && 'border-red-500 text-red-700 bg-red-50'
      )}
    >
      {percentage}%
    </Badge>
  )
}

function OCRConfidenceBar({ confidence }: { confidence: number }) {
  const percentage = Math.round(confidence)

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all',
            percentage >= 80 ? 'bg-green-500' : percentage >= 60 ? 'bg-yellow-500' : 'bg-red-500'
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-10">{percentage}%</span>
    </div>
  )
}

// ==================== Document Preview ====================

function DocumentPreview({
  fileUrl,
  mimeType,
  fileName,
}: {
  fileUrl: string | null
  mimeType: string
  fileName?: string
}) {
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)

  // Fallback MIME-Type basierend auf Dateiendung wenn mimeType leer oder ungueltig
  const effectiveMimeType = (() => {
    if (mimeType && mimeType !== '') return mimeType

    // Fallback: Dateiendung pruefen
    const ext = fileName?.split('.').pop()?.toLowerCase()
    switch (ext) {
      case 'pdf':
        return 'application/pdf'
      case 'png':
        return 'image/png'
      case 'jpg':
      case 'jpeg':
        return 'image/jpeg'
      case 'gif':
        return 'image/gif'
      case 'webp':
        return 'image/webp'
      case 'tiff':
      case 'tif':
        return 'image/tiff'
      case 'bmp':
        return 'image/bmp'
      default:
        return 'application/pdf' // Default-Fallback auf PDF
    }
  })()

  const isPDF = effectiveMimeType === 'application/pdf'
  const isImage = effectiveMimeType.startsWith('image/')

  // TIFF und BMP werden von den meisten Browsern nicht nativ unterstuetzt
  const isUnsupportedFormat = effectiveMimeType === 'image/tiff' || effectiveMimeType === 'image/bmp'

  // Browser-unterstuetzte Bildformate
  const isSupportedImage = isImage && !isUnsupportedFormat

  const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.25, 3))
  const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.25, 0.5))
  const handleResetZoom = () => {
    setZoom(1)
    setRotation(0)
  }

  if (!fileUrl) {
    return (
      <div className="flex items-center justify-center h-full bg-muted/50 rounded-lg">
        <div className="text-center text-muted-foreground">
          <FileWarning className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>Keine Vorschau verfuegbar</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-1 p-2 border-b bg-muted/30">
        <Button variant="ghost" size="icon" onClick={handleZoomOut} title="Verkleinern">
          <ZoomOut className="w-4 h-4" />
        </Button>
        <span className="text-xs text-muted-foreground px-2">{Math.round(zoom * 100)}%</span>
        <Button variant="ghost" size="icon" onClick={handleZoomIn} title="Vergroessern">
          <ZoomIn className="w-4 h-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={handleResetZoom} title="Zuruecksetzen">
          <RotateCcw className="w-4 h-4" />
        </Button>
      </div>

      {/* Preview Area */}
      <div className="flex-1 overflow-auto p-4 bg-muted/20">
        <div
          className="transition-transform origin-top-left"
          style={{
            transform: `scale(${zoom}) rotate(${rotation}deg)`,
          }}
        >
          {isPDF ? (
            <iframe
              src={`${fileUrl}#toolbar=0&navpanes=0`}
              className="w-full min-h-[600px] border-0 rounded"
              title="PDF-Vorschau"
            />
          ) : isSupportedImage ? (
            <img
              src={fileUrl}
              alt="Dokumentvorschau"
              className="max-w-full h-auto rounded shadow-sm"
            />
          ) : isUnsupportedFormat ? (
            <div className="flex items-center justify-center h-[400px] bg-amber-50 border border-amber-200 rounded-lg">
              <div className="text-center text-amber-800">
                <FileWarning className="w-12 h-12 mx-auto mb-2 text-amber-500" />
                <p className="font-medium">TIFF/BMP-Vorschau nicht moeglich</p>
                <p className="text-sm mt-1 text-amber-600">
                  Browser unterstuetzen dieses Format nicht direkt.
                  <br />
                  Die OCR-Verarbeitung wurde trotzdem durchgefuehrt.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-[400px] bg-muted rounded-lg">
              <div className="text-center text-muted-foreground">
                <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Vorschau fuer diesen Dateityp nicht verfuegbar</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ==================== Main Component ====================

export function OCRReviewModal({
  open,
  onOpenChange,
  file,
  fileUrl,
  ocrResult,
  quickClassification,
  renameSuggestion,
  entityId,
  entityName,
  entityType,
  folderId,
  folderName,
  category,
  categoryName,
  isSaving,
  onSave,
  onCancel,
}: OCRReviewModalProps) {
  // ==================== Form State ====================

  const [useRenameSuggestion, setUseRenameSuggestion] = useState(true)
  const [customFilename, setCustomFilename] = useState('')
  const [documentType, setDocumentType] = useState(
    quickClassification?.suggestedDocumentType || 'document'
  )
  const [documentNumber, setDocumentNumber] = useState(
    quickClassification?.extractedData?.documentNumber || ''
  )
  const [documentDate, setDocumentDate] = useState(
    quickClassification?.extractedData?.documentDate || ''
  )
  const [totalAmount, setTotalAmount] = useState(
    quickClassification?.extractedData?.totalAmount?.toString() || ''
  )
  const [currency, setCurrency] = useState(
    quickClassification?.extractedData?.currency || 'EUR'
  )
  const [dueDate, setDueDate] = useState(
    quickClassification?.extractedData?.dueDate || ''
  )
  const [tags, setTags] = useState<string[]>(
    quickClassification?.suggestedTags || []
  )
  const [newTag, setNewTag] = useState('')

  // NEU: Direction, IBAN, VAT-ID State
  const [direction, setDirection] = useState<InvoiceDirection>(
    quickClassification?.direction || null
  )
  const [ibanFound] = useState(
    quickClassification?.extractedData?.ibanFound || ''
  )
  const [vatIdFound] = useState(
    quickClassification?.extractedData?.vatIdFound || ''
  )

  // Sync direction state when quickClassification changes (e.g., after async load)
  useEffect(() => {
    if (quickClassification?.direction) {
      setDirection(quickClassification.direction)
    }
  }, [quickClassification])

  // Derived values
  const finalFilename = useMemo(() => {
    if (useRenameSuggestion && renameSuggestion?.suggestedFilename) {
      return renameSuggestion.suggestedFilename
    }
    return customFilename || file?.name || 'dokument.pdf'
  }, [useRenameSuggestion, renameSuggestion, customFilename, file])

  const documentTypes = entityType === 'customer'
    ? CUSTOMER_DOCUMENT_TYPES
    : SUPPLIER_DOCUMENT_TYPES

  // ==================== Handlers ====================

  const handleAddTag = useCallback(() => {
    if (newTag.trim() && !tags.includes(newTag.trim())) {
      setTags(prev => [...prev, newTag.trim()])
      setNewTag('')
    }
  }, [newTag, tags])

  const handleRemoveTag = useCallback((tagToRemove: string) => {
    setTags(prev => prev.filter(t => t !== tagToRemove))
  }, [])

  const handleSave = useCallback(async () => {
    const data: Partial<UploadCompleteRequest> = {
      finalFilename,
      documentType,
      documentNumber: documentNumber || undefined,
      documentDate: documentDate || undefined,
      totalAmount: totalAmount ? parseFloat(totalAmount) : undefined,
      currency,
      dueDate: dueDate || undefined,
      tags,
      entityType,
      folderId,
      category,
      businessEntityId: entityId || undefined,
      // NEU: Direction, IBAN, VAT-ID
      direction: direction || null,
      ibanFound: ibanFound || null,
      vatIdFound: vatIdFound || null,
    }

    await onSave(data)
  }, [
    finalFilename,
    documentType,
    documentNumber,
    documentDate,
    totalAmount,
    currency,
    dueDate,
    tags,
    entityType,
    folderId,
    category,
    entityId,
    direction,
    ibanFound,
    vatIdFound,
    onSave,
  ])

  // ==================== Render ====================

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl h-[90vh] flex flex-col p-0">
        <DialogHeader className="px-6 py-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5" />
            OCR-Ergebnis pruefen
          </DialogTitle>
        </DialogHeader>

        {/* Split View Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Document Preview */}
          <div className="w-1/2 border-r overflow-hidden">
            <DocumentPreview
              fileUrl={fileUrl}
              mimeType={file?.type || ''}
              fileName={file?.name}
            />
          </div>

          {/* Right: Metadata Form */}
          <div className="w-1/2 overflow-auto">
            <div className="p-6 space-y-6">
              {/* Target Path */}
              <div className="p-3 bg-muted/50 rounded-lg">
                <p className="text-sm text-muted-foreground">
                  Ziel: <span className="font-medium text-foreground">{entityName}</span>
                  {' > '}
                  <span className="font-medium text-foreground">{folderName}</span>
                  {' > '}
                  <span className="font-medium text-foreground">{categoryName}</span>
                </p>
              </div>

              {/* Filename Section */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-yellow-500" />
                  <Label className="font-semibold">Dateiname</Label>
                </div>

                {renameSuggestion && (
                  <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                    <Checkbox
                      id="use-suggestion"
                      checked={useRenameSuggestion}
                      onCheckedChange={(checked) => setUseRenameSuggestion(!!checked)}
                    />
                    <label
                      htmlFor="use-suggestion"
                      className="flex-1 cursor-pointer"
                    >
                      <span className="font-medium text-green-800">
                        {renameSuggestion.suggestedFilename}
                      </span>
                      <ConfidenceBadge confidence={renameSuggestion.confidence} />
                    </label>
                  </div>
                )}

                {(!renameSuggestion || !useRenameSuggestion) && (
                  <Input
                    value={customFilename || file?.name || ''}
                    onChange={(e) => setCustomFilename(e.target.value)}
                    placeholder="Dateiname eingeben..."
                  />
                )}

                {file && (
                  <p className="text-xs text-muted-foreground">
                    Original: {file.name}
                  </p>
                )}
              </div>

              {/* Invoice Direction Toggle */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <ArrowDownLeft className="w-4 h-4" />
                  Rechnungsrichtung
                </Label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={direction === 'incoming' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setDirection('incoming')}
                    className="flex-1"
                  >
                    <ArrowDownLeft className="w-4 h-4 mr-1" />
                    Eingang
                  </Button>
                  <Button
                    type="button"
                    variant={direction === 'outgoing' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setDirection('outgoing')}
                    className="flex-1"
                  >
                    <ArrowUpRight className="w-4 h-4 mr-1" />
                    Ausgang
                  </Button>
                </div>
              </div>

              {/* Document Type */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Dokumenttyp
                </Label>
                <Select value={documentType} onValueChange={setDocumentType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Dokumenttyp waehlen..." />
                  </SelectTrigger>
                  <SelectContent>
                    {documentTypes.map((type) => (
                      <SelectItem key={type.value} value={type.value}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Document Number */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Hash className="w-4 h-4" />
                  Belegnummer
                </Label>
                <Input
                  value={documentNumber}
                  onChange={(e) => setDocumentNumber(e.target.value)}
                  placeholder="z.B. RG-2024-001"
                />
              </div>

              {/* Date Row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Calendar className="w-4 h-4" />
                    Dokumentdatum
                  </Label>
                  <Input
                    type="date"
                    value={documentDate}
                    onChange={(e) => setDocumentDate(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Calendar className="w-4 h-4" />
                    Faelligkeitsdatum
                  </Label>
                  <Input
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                  />
                </div>
              </div>

              {/* Amount Row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <DollarSign className="w-4 h-4" />
                    Betrag
                  </Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={totalAmount}
                    onChange={(e) => setTotalAmount(e.target.value)}
                    placeholder="0,00"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Waehrung</Label>
                  <Select value={currency} onValueChange={setCurrency}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="EUR">EUR</SelectItem>
                      <SelectItem value="USD">USD</SelectItem>
                      <SelectItem value="GBP">GBP</SelectItem>
                      <SelectItem value="CHF">CHF</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* IBAN (wenn erkannt) */}
              {(ibanFound || quickClassification?.extractedData?.ibanFound) && (
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <CreditCard className="w-4 h-4" />
                    IBAN
                  </Label>
                  <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <span className="font-mono text-sm">
                      {ibanFound || quickClassification?.extractedData?.ibanFound}
                    </span>
                    <Badge variant="outline" className="text-xs text-blue-700">
                      Auto-erkannt
                    </Badge>
                  </div>
                </div>
              )}

              {/* USt-ID (wenn erkannt) */}
              {(vatIdFound || quickClassification?.extractedData?.vatIdFound) && (
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Building className="w-4 h-4" />
                    USt-ID
                  </Label>
                  <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                    <span className="font-mono text-sm">
                      {vatIdFound || quickClassification?.extractedData?.vatIdFound}
                    </span>
                    <Badge variant="outline" className="text-xs text-green-700">
                      Auto-erkannt
                    </Badge>
                  </div>
                </div>
              )}

              {/* Matched Entity */}
              {quickClassification?.matchedEntityId && (
                <div className="space-y-2">
                  <Label className="flex items-center gap-2">
                    <Building2 className="w-4 h-4" />
                    Erkannter Partner
                  </Label>
                  <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <CheckCircle2 className="w-5 h-5 text-blue-600" />
                    <span className="font-medium text-blue-800">
                      {quickClassification.matchedEntityName}
                    </span>
                    <ConfidenceBadge confidence={quickClassification.matchedEntityConfidence} />
                  </div>
                </div>
              )}

              {/* Tags */}
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Tag className="w-4 h-4" />
                  Tags
                </Label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {tags.map((tag) => (
                    <Badge
                      key={tag}
                      variant="secondary"
                      className="cursor-pointer hover:bg-destructive hover:text-destructive-foreground"
                      onClick={() => handleRemoveTag(tag)}
                    >
                      {tag}
                      <X className="w-3 h-3 ml-1" />
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    value={newTag}
                    onChange={(e) => setNewTag(e.target.value)}
                    placeholder="Neuer Tag..."
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddTag()
                      }
                    }}
                  />
                  <Button variant="outline" onClick={handleAddTag}>
                    Hinzufuegen
                  </Button>
                </div>
              </div>

              {/* OCR Confidence */}
              {ocrResult && (
                <div className="space-y-2 pt-4 border-t">
                  <Label className="text-muted-foreground">OCR-Konfidenz</Label>
                  <OCRConfidenceBar confidence={ocrResult.confidence} />
                  <p className="text-xs text-muted-foreground">
                    {ocrResult.pageCount} Seite{ocrResult.pageCount !== 1 ? 'n' : ''} verarbeitet
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <DialogFooter className="px-6 py-4 border-t bg-muted/30">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isSaving}
          >
            Abbrechen
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving}
            className="gap-2"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Speichere...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Speichern & Ablegen
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default OCRReviewModal
