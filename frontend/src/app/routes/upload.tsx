import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { UploadDropzone } from '@/features/upload/components/UploadDropzone'
import { OCRBackendSelector } from '@/features/upload/components/OCRBackendSelector'
import { Button } from '@/components/ui/button'
import { ArrowRight } from 'lucide-react'

export const Route = createFileRoute('/upload')({
    component: UploadPage,
})

function UploadPage() {
    const [files, setFiles] = useState<File[]>([])
    const [backendId, setBackendId] = useState('got-ocr')

    const handleFilesAdd = (newFiles: File[]) => {
        setFiles(prev => [...prev, ...newFiles])
    }

    const handleUpload = () => {
        console.log('Uploading', files.length, 'files with backend', backendId)
        // Implement upload logic here
    }

    return (
        <div className="max-w-5xl mx-auto p-8 space-y-8">
            <div>
                <h1 className="text-3xl font-bold tracking-tight">Dokument Upload</h1>
                <p className="text-muted-foreground mt-2">
                    Laden Sie Ihre Dokumente hoch und wählen Sie die passende OCR-Engine.
                </p>
            </div>

            <div className="space-y-4">
                <h2 className="text-xl font-semibold">1. Dateien auswählen</h2>
                <UploadDropzone onFilesAdd={handleFilesAdd} />
                {files.length > 0 && (
                    <div className="bg-muted/30 p-4 rounded-lg">
                        <p className="font-medium">{files.length} Dateien ausgewählt</p>
                        <ul className="mt-2 text-sm text-muted-foreground list-disc list-inside">
                            {files.map((f, i) => (
                                <li key={i}>{f.name} ({Math.round(f.size / 1024)} KB)</li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>

            <div className="h-px bg-border" />

            <div className="space-y-4">
                <h2 className="text-xl font-semibold">2. OCR Backend wählen</h2>
                <OCRBackendSelector
                    selectedId={backendId}
                    onSelect={setBackendId}
                    gpuAvailable={true}
                />
            </div>

            <div className="flex justify-end pt-4">
                <Button
                    size="lg"
                    onClick={handleUpload}
                    disabled={files.length === 0}
                    className="gap-2"
                >
                    Upload starten
                    <ArrowRight className="w-4 h-4" />
                </Button>
            </div>
        </div>
    )
}
