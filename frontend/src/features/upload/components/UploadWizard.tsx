import { useState, useCallback, useEffect, useRef } from 'react';
import { UploadDropzone } from './UploadDropzone';
import { UploadFileList } from './UploadFileList';
import { documentsService } from '@/lib/api/services/documents';
import { tasksService } from '@/lib/api/services/tasks';
import { toast } from '@/components/ui/use-toast';
import type { UploadingFile } from '../types';

export function UploadWizard() {
    const [files, setFiles] = useState<UploadingFile[]>([]);
    const [renameLoadingIds, setRenameLoadingIds] = useState<string[]>([]);

    const uploadFile = useCallback(async (uploadingFile: UploadingFile) => {
        try {
            // Update status to uploading
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id ? { ...f, status: 'uploading' as const } : f
            ));

            // Upload the file with progress tracking
            const document = await documentsService.upload(
                uploadingFile.file,
                { ocrBackend: 'auto' },
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
                // Fetch classification data
                await fetchClassificationAndUpdate(uploadingFile.id, document.id);
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

    /**
     * Lädt die Klassifizierungsdaten und aktualisiert den File-Status
     */
    const fetchClassificationAndUpdate = useCallback(async (fileId: string, documentId: string) => {
        try {
            const extractedData = await documentsService.getExtractedData(documentId);

            setFiles(prev => prev.map(f =>
                f.id === fileId
                    ? {
                        ...f,
                        status: 'awaiting_confirmation' as const,
                        ocrProgress: 100,
                        classification: extractedData?.invoice ? {
                            invoiceDirection: extractedData.invoice.invoice_direction || 'unknown',
                            confidence: extractedData.invoice.invoice_direction_confidence || 0,
                            reason: extractedData.invoice.invoice_direction_reason,
                        } : {
                            invoiceDirection: 'unknown',
                            confidence: 0,
                        }
                    }
                    : f
            ));
        } catch {
            // Falls keine Daten verfügbar, trotzdem als awaiting_confirmation markieren
            setFiles(prev => prev.map(f =>
                f.id === fileId
                    ? {
                        ...f,
                        status: 'awaiting_confirmation' as const,
                        ocrProgress: 100,
                        classification: {
                            invoiceDirection: 'unknown',
                            confidence: 0,
                        }
                    }
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

    /**
     * Handler für Änderung der Dokumentenrichtung (Eingangs-/Ausgangsrechnung)
     */
    const handleChangeDirection = useCallback(async (
        fileId: string,
        direction: 'incoming' | 'outgoing'
    ) => {
        const file = files.find(f => f.id === fileId);
        if (!file?.documentId) return;

        const currentDirection = file.confirmedDirection || file.classification?.invoiceDirection;
        const isOverridden = direction !== file.classification?.invoiceDirection;

        try {
            await documentsService.confirmClassification(file.documentId, {
                invoice_direction: direction,
                user_overridden: isOverridden
            });

            setFiles(prev => prev.map(f =>
                f.id === fileId
                    ? {
                        ...f,
                        confirmedDirection: direction,
                        status: 'completed' as const
                    }
                    : f
            ));

            const tagName = direction === 'incoming' ? 'Eingangsrechnung' : 'Ausgangsrechnung';
            if (currentDirection !== direction) {
                toast({
                    title: 'Klassifizierung geändert',
                    description: `Dokument als ${tagName} markiert`,
                    variant: 'success'
                });
            }
        } catch (error) {
            console.error('Classification change failed:', error);
            toast({
                title: 'Fehler',
                description: 'Klassifizierung konnte nicht geändert werden',
                variant: 'destructive'
            });
        }
    }, [files]);

    /**
     * Handler fuer Bestaetigung des Rename-Vorschlags
     */
    const handleConfirmRename = useCallback(async (fileId: string) => {
        const file = files.find(f => f.id === fileId);
        if (!file?.documentId || !file.classification?.renameSuggestion) return;

        const suggestion = file.classification.renameSuggestion;

        // Loading state setzen
        setRenameLoadingIds(prev => [...prev, fileId]);

        try {
            const result = await documentsService.confirmRename(
                file.documentId,
                suggestion.suggestedFilename
            );

            // File-State aktualisieren
            setFiles(prev => prev.map(f =>
                f.id === fileId
                    ? { ...f, renameConfirmed: true }
                    : f
            ));

            toast({
                title: 'Dokument umbenannt',
                description: `Neuer Name: ${result.new_filename}`,
                variant: 'success'
            });
        } catch (error) {
            console.error('Rename confirmation failed:', error);
            toast({
                title: 'Fehler',
                description: 'Umbenennung konnte nicht durchgeführt werden',
                variant: 'destructive'
            });
        } finally {
            // Loading state entfernen
            setRenameLoadingIds(prev => prev.filter(id => id !== fileId));
        }
    }, [files]);

    // Ref für files um stable reference im polling zu haben
    const filesRef = useRef(files);
    useEffect(() => {
        filesRef.current = files;
    }, [files]);

    // Poll for Quick Classification AND OCR status
    // Quick Classification ist in 2-5 Sekunden fertig, OCR dauert 30-120 Sekunden
    // Verwendet filesRef um unnötige Interval-Neuerstellungen zu vermeiden
    useEffect(() => {
        const pollStatus = async () => {
            const currentFiles = filesRef.current;
            // Auch awaiting_confirmation Dateien mit 'unknown' Classification weiter pollen
            // (Quick Classification kann nach OCR-Completion fertig werden)
            const processingFiles = currentFiles.filter(f =>
                (f.status === 'processing' && f.documentId) ||
                (f.status === 'awaiting_confirmation' && f.documentId &&
                 (!f.classification || f.classification.invoiceDirection === 'unknown'))
            );
            if (processingFiles.length === 0) return;

            for (const file of processingFiles) {
                try {
                    // Poll document status (includes quick_classification_status)
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

                    // 1. Check Quick Classification (erscheint innerhalb 2-5 Sekunden)
                    // Zeige Badge sobald Quick Classification fertig ist, auch wenn OCR noch laeuft
                    // WICHTIG: Quick Classification ueberschreibt auch 'unknown' Classifications
                    // FIX: Auch uebernehmen wenn renameSuggestion fehlt aber in QC vorhanden
                    const shouldUseQuickClassification =
                        doc.quickClassificationStatus === 'completed' &&
                        doc.quickClassificationResult &&
                        doc.quickClassificationResult.direction !== 'unknown' &&
                        (!file.classification ||
                         file.classification.invoiceDirection === 'unknown' ||
                         (!file.classification.renameSuggestion && doc.quickClassificationResult.renameSuggestion));

                    if (shouldUseQuickClassification) {
                        const qcResult = doc.quickClassificationResult!;
                        // documentsService.getById() transformiert bereits tag_assigned -> tagAssigned
                        const tagWasAssigned = qcResult.tagAssigned === true;

                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? {
                                    ...f,
                                    classification: {
                                        invoiceDirection: qcResult.direction || 'unknown',
                                        confidence: qcResult.confidence || 0,
                                        reason: qcResult.reason,
                                        // Business Entity Matching
                                        matchedEntityId: qcResult.matchedEntityId,
                                        matchedEntityName: qcResult.matchedEntityName,
                                        matchedEntityType: qcResult.matchedEntityType,
                                        entityMatchMethod: qcResult.entityMatchMethod,
                                        entityConfidence: qcResult.entityConfidence,
                                        entityAutoLinked: qcResult.entityAutoLinked,
                                        // Rename Suggestion (nur fuer Eingangsrechnungen)
                                        renameSuggestion: qcResult.renameSuggestion,
                                    },
                                    // Wenn Tag automatisch zugewiesen wurde, als completed markieren
                                    // Sonst bleibt processing bis OCR fertig
                                    status: tagWasAssigned ? 'completed' as const : f.status,
                                    confirmedDirection: tagWasAssigned ? qcResult.direction as 'incoming' | 'outgoing' : undefined,
                                }
                                : f
                        ));
                    }

                    // 2. Check OCR Status
                    if (doc.ocrStatus === 'completed') {
                        // OCR fertig - Falls noch keine Classification, aus extracted_data holen
                        const currentFile = filesRef.current.find(f => f.id === file.id);
                        if (!currentFile?.classification) {
                            const extractedData = await documentsService.getExtractedData(file.documentId!);
                            setFiles(prev => prev.map(f =>
                                f.id === file.id
                                    ? {
                                        ...f,
                                        status: 'awaiting_confirmation' as const,
                                        ocrProgress: 100,
                                        classification: extractedData?.invoice ? {
                                            invoiceDirection: extractedData.invoice.invoice_direction || 'unknown',
                                            confidence: extractedData.invoice.invoice_direction_confidence || 0,
                                            reason: extractedData.invoice.invoice_direction_reason,
                                        } : f.classification || {
                                            invoiceDirection: 'unknown',
                                            confidence: 0,
                                        }
                                    }
                                    : f
                            ));
                        } else if (currentFile.status === 'processing') {
                            // Classification schon da (von Quick Classification), nur Status updaten
                            setFiles(prev => prev.map(f =>
                                f.id === file.id
                                    ? {
                                        ...f,
                                        status: f.confirmedDirection ? 'completed' as const : 'awaiting_confirmation' as const,
                                        ocrProgress: 100,
                                    }
                                    : f
                            ));
                        }

                        // FIX: Nachtraeglich renameSuggestion aus Quick Classification holen
                        // falls OCR vor QC fertig wurde oder QC-Daten beim ersten Polling fehlten
                        const updatedFile = filesRef.current.find(f => f.id === file.id);
                        if (doc.quickClassificationStatus === 'completed' &&
                            doc.quickClassificationResult?.renameSuggestion &&
                            updatedFile?.classification &&
                            !updatedFile.classification.renameSuggestion) {
                            setFiles(prev => prev.map(f =>
                                f.id === file.id
                                    ? {
                                        ...f,
                                        classification: {
                                            ...f.classification!,
                                            renameSuggestion: doc.quickClassificationResult!.renameSuggestion,
                                        }
                                    }
                                    : f
                            ));
                        }
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
                        <UploadFileList
                            files={files}
                            onRemove={handleRemove}
                            onChangeDirection={handleChangeDirection}
                            onConfirmRename={handleConfirmRename}
                            renameLoadingIds={renameLoadingIds}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
