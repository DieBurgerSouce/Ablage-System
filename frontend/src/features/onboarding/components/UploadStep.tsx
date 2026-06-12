/**
 * Schritt 3: Erstes Dokument hochladen
 *
 * - Drag & Drop Zone
 * - Upload-Fortschritt
 * - OCR-Verarbeitung mit animierter Erklaerung
 */

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { useMutation } from '@tanstack/react-query'
import { Upload, AlertCircle, CheckCircle2, Loader2, FileText, Cpu, ScanSearch, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Progress } from '@/components/ui/progress'
import { documentsService } from '@/lib/api/services/documents'

interface UploadedDoc {
  id: string
  name: string
  ocrStatus: 'pending' | 'processing' | 'completed' | 'failed'
  ocrConfidence?: number
  extractedText?: string
}

interface UploadStepProps {
  onDocumentReady: (doc: UploadedDoc) => void
}

type UploadPhase = 'idle' | 'uploading' | 'processing' | 'done' | 'error'

const PROCESSING_STEPS = [
  {
    icon: Upload,
    label: 'Dokument wird hochgeladen...',
    description: 'Ihre Datei wird sicher auf Ihren Server uebertragen.',
  },
  {
    icon: ScanSearch,
    label: 'Texterkennung laeuft...',
    description: 'Die KI analysiert Ihr Dokument und erkennt den Text.',
  },
  {
    icon: Cpu,
    label: 'Metadaten werden extrahiert...',
    description: 'Datum, Betrag und Geschaeftspartner werden automatisch erkannt.',
  },
  {
    icon: Sparkles,
    label: 'Dokument wird klassifiziert...',
    description: 'Eingangsrechnung, Ausgangsrechnung oder anderer Dokumenttyp.',
  },
]

export function UploadStep({ onDocumentReady }: UploadStepProps) {
  const [phase, setPhase] = useState<UploadPhase>('idle')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [processingStep, setProcessingStep] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [uploadedFile, setUploadedFile] = useState<{ name: string; size: number } | null>(null)

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      setPhase('uploading')
      setUploadProgress(0)

      const result = await documentsService.upload(
        file,
        { ocrBackend: 'auto' },
        (progress) => setUploadProgress(progress),
      )

      return result
    },
    onSuccess: (doc) => {
      setPhase('processing')

      // Simulate processing steps animation
      let step = 0
      const interval = setInterval(() => {
        step++
        setProcessingStep(step)
        if (step >= PROCESSING_STEPS.length - 1) {
          clearInterval(interval)
          // Give a moment for the last step to show
          setTimeout(() => {
            setPhase('done')
            onDocumentReady({
              id: doc.id,
              name: doc.name,
              ocrStatus: doc.ocrStatus,
              ocrConfidence: doc.ocrConfidence,
              extractedText: doc.extractedText,
            })
          }, 1500)
        }
      }, 2000)
    },
    onError: () => {
      setPhase('error')
      setErrorMessage('Upload fehlgeschlagen. Bitte versuchen Sie es erneut.')
    },
  })

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return
      const file = acceptedFiles[0]
      setUploadedFile({ name: file.name, size: file.size })
      setErrorMessage('')
      uploadMutation.mutate(file)
    },
    [uploadMutation],
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/tiff': ['.tif', '.tiff'],
    },
    maxSize: 50 * 1024 * 1024,
    maxFiles: 1,
    disabled: phase !== 'idle' && phase !== 'error',
  })

  // Idle / Error state: show dropzone
  if (phase === 'idle' || phase === 'error') {
    return (
      <div className="space-y-6">
        <div className="text-center pb-2">
          <h2 className="text-lg font-semibold">Erstes Dokument hochladen</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Laden Sie ein Dokument hoch, um die OCR-Texterkennung live zu erleben.
          </p>
        </div>

        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-xl p-10 cursor-pointer flex flex-col items-center justify-center text-center transition-colors',
            'hover:border-primary/50 hover:bg-muted/30',
            isDragActive && 'border-primary bg-primary/5',
            isDragReject && 'border-destructive bg-destructive/5',
          )}
        >
          <input {...getInputProps()} aria-label="Datei zum Hochladen auswaehlen" />

          <div
            className={cn(
              'w-16 h-16 rounded-2xl flex items-center justify-center mb-4',
              isDragReject
                ? 'bg-destructive/10 text-destructive'
                : isDragActive
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground',
            )}
          >
            {isDragReject ? (
              <AlertCircle className="w-8 h-8" />
            ) : (
              <Upload className="w-8 h-8" />
            )}
          </div>

          <h3 className="text-base font-medium">
            {isDragReject
              ? 'Dateityp nicht unterstuetzt'
              : isDragActive
                ? 'Datei hier ablegen'
                : 'Drag & Drop oder klicken'}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {isDragReject
              ? 'Bitte nur PDF, PNG, JPG oder TIFF hochladen.'
              : 'PDF, PNG, JPG, TIFF - Max. 50MB'}
          </p>
        </div>

        {phase === 'error' && (
          <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>
    )
  }

  // Uploading state
  if (phase === 'uploading') {
    return (
      <div className="space-y-6 py-8">
        <div className="text-center">
          <div className="p-4 rounded-full bg-primary/10 border border-primary/20 inline-block mb-4">
            <Upload className="w-10 h-10 text-primary animate-pulse" aria-hidden="true" />
          </div>
          <h2 className="text-lg font-semibold">Wird hochgeladen...</h2>
          {uploadedFile && (
            <p className="text-sm text-muted-foreground mt-1">
              {uploadedFile.name} ({formatFileSize(uploadedFile.size)})
            </p>
          )}
        </div>

        <div className="space-y-2 max-w-xs mx-auto">
          <Progress value={uploadProgress} className="h-2" aria-label="Upload-Fortschritt" />
          <p className="text-xs text-muted-foreground text-center">{uploadProgress}%</p>
        </div>
      </div>
    )
  }

  // Processing state
  if (phase === 'processing') {
    const step = PROCESSING_STEPS[processingStep] ?? PROCESSING_STEPS[0]
    const StepIcon = step.icon

    return (
      <div className="space-y-6 py-8">
        <div className="text-center">
          <div className="p-4 rounded-full bg-primary/10 border border-primary/20 inline-block mb-4">
            <StepIcon className="w-10 h-10 text-primary animate-pulse" aria-hidden="true" />
          </div>
          <h2 className="text-lg font-semibold">{step.label}</h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-sm mx-auto">
            {step.description}
          </p>
        </div>

        {/* Processing steps progress */}
        <div className="max-w-sm mx-auto space-y-2">
          {PROCESSING_STEPS.map((s, i) => {
            const SIcon = s.icon
            const isDone = i < processingStep
            const isCurrent = i === processingStep

            return (
              <div
                key={s.label}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all',
                  isDone && 'text-green-600 bg-green-500/10',
                  isCurrent && 'text-primary bg-primary/10 font-medium',
                  !isDone && !isCurrent && 'text-muted-foreground',
                )}
              >
                {isDone ? (
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                ) : isCurrent ? (
                  <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
                ) : (
                  <SIcon className="w-4 h-4 flex-shrink-0 opacity-40" />
                )}
                <span>{s.label.replace('...', '')}</span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // Done state
  return (
    <div className="space-y-6 py-8">
      <div className="text-center">
        <div className="p-4 rounded-full bg-green-500/10 border border-green-500/20 inline-block mb-4">
          <CheckCircle2 className="w-10 h-10 text-green-500" aria-hidden="true" />
        </div>
        <h2 className="text-lg font-semibold">Dokument verarbeitet!</h2>
        {uploadedFile && (
          <div className="flex items-center justify-center gap-2 mt-2 text-sm text-muted-foreground">
            <FileText className="w-4 h-4" />
            <span>{uploadedFile.name}</span>
          </div>
        )}
        <p className="text-sm text-muted-foreground mt-2">
          Im naechsten Schritt sehen Sie die Ergebnisse.
        </p>
      </div>
    </div>
  )
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
