import { useState, useCallback, useEffect, useRef } from 'react';
import { UploadDropzone } from './UploadDropzone';
import { UploadFileList } from './UploadFileList';
import { documentsService } from '@/lib/api/services/documents';
import { tasksService } from '@/lib/api/services/tasks';
import type { UploadingFile } from '../types';

export function UploadWizard() {
    const [files, setFiles] = useState<UploadingFile[]>([]);

    const uploadFile = useCallback(async (uploadingFile: UploadingFile) => {
        try {
            // Update status to uploading
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id ? { ...f, status: 'uploading' as const } : f
            ));

            // Upload the file with progress tracking
            const document = await documentsService.upload(
                uploadingFile.file,
                { ocrBackend: 'surya' },
                (progress) => {
                    setFiles(prev => prev.map(f =>
                        f.id === uploadingFile.id ? { ...f, progress } : f
                    ));
                }
            );

            // Update to processing (OCR is now running on backend)
            // Store taskId for progress polling
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id
                    ? {
                        ...f,
                        status: 'processing' as const,
                        progress: 100,
                        documentId: document.id,
                        taskId: document.taskId,
                        ocrProgress: 0,
                      }
                    : f
            ));

            // Check if document has completed OCR or still processing
            if (document.ocrStatus === 'completed') {
                setFiles(prev => prev.map(f =>
                    f.id === uploadingFile.id ? { ...f, status: 'completed' as const, ocrProgress: 100 } : f
                ));
            }
            // Otherwise keep 'processing' status - polling will update when done
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id
                    ? { ...f, status: 'failed' as const, error: errorMessage }
                    : f
            ));
        }
    }, []);

    const handleFilesAdd = useCallback(async (newFiles: File[]) => {
        // Create UploadingFile objects for each new file
        const newUploadingFiles: UploadingFile[] = newFiles.map(file => ({
            id: crypto.randomUUID(),
            file,
            status: 'pending' as const,
            progress: 0,
        }));

        // Add to state
        setFiles(prev => [...prev, ...newUploadingFiles]);

        // Start uploading each file
        for (const uploadingFile of newUploadingFiles) {
            uploadFile(uploadingFile);
        }
    }, [uploadFile]);

    const handleRemove = useCallback((id: string) => {
        setFiles(prev => prev.filter(f => f.id !== id));
    }, []);

    // Ref für files um stable reference im polling zu haben
    const filesRef = useRef(files);
    useEffect(() => {
        filesRef.current = files;
    }, [files]);

    // Poll for OCR status and progress updates on processing files
    // Verwendet filesRef um unnötige Interval-Neuerstellungen zu vermeiden
    useEffect(() => {
        const pollStatus = async () => {
            const currentFiles = filesRef.current;
            const processingFiles = currentFiles.filter(f => f.status === 'processing' && f.documentId);
            if (processingFiles.length === 0) return;

            for (const file of processingFiles) {
                try {
                    // Poll document status
                    const doc = await documentsService.getById(file.documentId!);

                    // Also poll task progress if we have a taskId
                    let taskProgress: number | undefined;
                    let taskMessage: string | undefined;
                    if (file.taskId) {
                        try {
                            const taskStatus = await tasksService.getStatus(file.taskId);
                            taskProgress = taskStatus.progress;
                            taskMessage = taskStatus.message;
                        } catch {
                            // Task might not exist yet or has completed
                        }
                    }

                    if (doc.ocrStatus === 'completed') {
                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? { ...f, status: 'completed' as const, ocrProgress: 100 }
                                : f
                        ));
                    } else if (doc.ocrStatus === 'failed') {
                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? { ...f, status: 'failed' as const, error: 'OCR fehlgeschlagen' }
                                : f
                        ));
                    } else if (taskProgress !== undefined) {
                        // Update progress while still processing
                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? { ...f, ocrProgress: taskProgress, ocrMessage: taskMessage }
                                : f
                        ));
                    }
                } catch (e) {
                    console.error('Status polling failed:', e);
                }
            }
        };

        // Starte polling nur einmal beim Mount, nicht bei jeder files-Änderung
        const interval = setInterval(pollStatus, 1000); // Poll every 1 second
        return () => clearInterval(interval);
    }, []); // Leere Dependencies - Interval wird nur einmal erstellt

    return (
        <div className="max-w-4xl mx-auto py-8 px-4">
            <div className="mb-8">
                <h1 className="text-3xl font-bold tracking-tight">Dokumente hochladen</h1>
                <p className="text-muted-foreground mt-2">
                    Laden Sie Ihre Dokumente hoch. Die OCR-Verarbeitung startet automatisch.
                </p>
            </div>

            <div className="space-y-8">
                {/* Upload Dropzone - always visible */}
                <div className="bg-background rounded-2xl border shadow-sm p-6">
                    <UploadDropzone onFilesAdd={handleFilesAdd} />
                </div>

                {/* File List */}
                {files.length > 0 && (
                    <div className="bg-background rounded-2xl border shadow-sm p-6">
                        <UploadFileList files={files} onRemove={handleRemove} />
                    </div>
                )}
            </div>
        </div>
    );
}
