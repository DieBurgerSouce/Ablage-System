import { useState, useCallback, useEffect, useRef } from 'react';
import { emitChecklistComplete } from '@/features/product-tour';
import {
    DndContext,
    DragOverlay,
    closestCenter,
    PointerSensor,
    useSensor,
    useSensors,
    type DragStartEvent,
    type DragEndEvent,
    type DragOverEvent,
} from '@dnd-kit/core';
import { logger } from '@/lib/logger';
import { UploadDropzone } from './UploadDropzone';
import { UploadFileList } from './UploadFileList';
import { TransactionGroupCard } from './TransactionGroupCard';
import { documentsService } from '@/lib/api/services/documents';
import { groupsService } from '@/lib/api/services/groups';
import { tasksService } from '@/lib/api/services/tasks';
import { toast } from '@/components/ui/use-toast';
import { FileText, Layers } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { AnimatePresence } from 'framer-motion';
import { useRecentItems } from '@/hooks';
import { RecentlyUsedSection } from '@/components/shared/RecentlyUsedSection';
import type { UploadingFile, TransactionGroup } from '../types';
import {
    ContextMenu,
    ContextMenuContent,
    ContextMenuItem,
    ContextMenuSeparator,
    ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
    usePersistedUploadState,
    setupHardReloadDetection,
    deserializeFiles,
    serializeFiles,
    deserializeGroups,
    serializeGroups,
} from '../hooks/usePersistedUploadState';

export function UploadWizard() {
    // Persistierte States - überleben normale Page-Reloads
    const [files, setFiles] = usePersistedUploadState<UploadingFile[]>(
        'files',
        [],
        { deserialize: deserializeFiles, serialize: serializeFiles }
    );
    const [transactionGroups, setTransactionGroups] = usePersistedUploadState<TransactionGroup[]>(
        'transaction-groups',
        [],
        { deserialize: deserializeGroups, serialize: serializeGroups }
    );
    const [localNumberCounters, setLocalNumberCounters] = usePersistedUploadState<Record<string, number>>(
        'number-counters',
        {}
    );

    const [renameLoadingIds, setRenameLoadingIds] = useState<string[]>([]);

    // Hard-Reload Detection einrichten
    useEffect(() => {
        const cleanup = setupHardReloadDetection();
        return cleanup;
    }, []);

    // Selection-State für Mehrfachauswahl
    const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());

    // DnD-State
    const [dragActiveId, setDragActiveId] = useState<string | null>(null);
    const [dragOverId, setDragOverId] = useState<string | null>(null);

    // Smart Defaults: Zuletzt verknüpfte Entitäten tracken
    const { items: recentEntities, addItem: addRecentEntity, clear: clearRecentEntities } = useRecentItems<{id: string; label: string}>({
        storageKey: 'ablage-upload-recent-entities',
        maxItems: 5,
    });

    // DnD Sensor mit Aktivierungsschwelle
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 8, // 8px Bewegung bevor Drag startet
            },
        })
    );

    // ========== FILE UPLOAD LOGIC ==========

    const uploadFile = useCallback(async (uploadingFile: UploadingFile) => {
        // Guard: File-Objekt muss vorhanden sein (bei wiederhergestellten Dateien ist es null)
        if (!uploadingFile.file) {
            logger.warn('uploadFile ohne File-Objekt aufgerufen, überspringe');
            return;
        }

        try {
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id ? { ...f, status: 'uploading' as const } : f
            ));

            const document = await documentsService.upload(
                uploadingFile.file,
                { ocrBackend: 'auto' },
                (progress) => {
                    setFiles(prev => prev.map(f =>
                        f.id === uploadingFile.id ? { ...f, progress } : f
                    ));
                }
            );

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

            emitChecklistComplete('upload_document');

            if (document.ocrStatus === 'completed') {
                await fetchClassificationAndUpdate(uploadingFile.id, document.id);
            }
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unbekannter Fehler';
            setFiles(prev => prev.map(f =>
                f.id === uploadingFile.id
                    ? { ...f, status: 'failed' as const, error: errorMessage }
                    : f
            ));
        }
    }, []);

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
        const newUploadingFiles: UploadingFile[] = newFiles.map(file => ({
            id: crypto.randomUUID(),
            file,
            originalFilename: file.name, // Für Persistenz nach Page-Reload
            status: 'pending' as const,
            progress: 0,
        }));

        setFiles(prev => [...prev, ...newUploadingFiles]);

        for (const uploadingFile of newUploadingFiles) {
            uploadFile(uploadingFile);
        }
    }, [uploadFile]);

    const handleRemove = useCallback((id: string) => {
        // Auch aus Selection und Gruppen entfernen
        setSelectedFileIds(prev => {
            const newSet = new Set(prev);
            newSet.delete(id);
            return newSet;
        });
        setTransactionGroups(prev => prev.map(g => ({
            ...g,
            documentIds: g.documentIds.filter(docId => docId !== id)
        })).filter(g => g.documentIds.length >= 2)); // Gruppen mit <2 Docs auflösen
        setFiles(prev => prev.filter(f => f.id !== id));
    }, []);

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

            // Smart Defaults: Entität für "Zuletzt verwendet" tracken
            const entityId = file.classification?.matchedEntityId;
            const entityName = file.classification?.matchedEntityName;
            if (entityId && entityName) {
                addRecentEntity({ id: entityId, label: entityName });
            }
        } catch (error) {
            logger.error('Klassifizierungsänderung fehlgeschlagen', error);
            toast({
                title: 'Fehler',
                description: 'Klassifizierung konnte nicht geändert werden',
                variant: 'destructive'
            });
        }
    }, [files, addRecentEntity]);

    const handleConfirmRename = useCallback(async (fileId: string) => {
        const file = files.find(f => f.id === fileId);
        if (!file?.documentId || !file.classification?.renameSuggestion) return;

        const suggestion = file.classification.renameSuggestion;
        setRenameLoadingIds(prev => [...prev, fileId]);

        try {
            const result = await documentsService.confirmRename(
                file.documentId,
                suggestion.suggestedFilename
            );

            setFiles(prev => prev.map(f =>
                f.id === fileId
                    ? { ...f, renameConfirmed: true, renamedFilename: result.new_filename }
                    : f
            ));

            toast({
                title: 'Dokument umbenannt',
                description: `Neuer Name: ${result.new_filename}`,
                variant: 'success'
            });
        } catch (error) {
            logger.error('Umbenennung fehlgeschlagen', error);
            toast({
                title: 'Fehler',
                description: 'Umbenennung konnte nicht durchgeführt werden',
                variant: 'destructive'
            });
        } finally {
            setRenameLoadingIds(prev => prev.filter(id => id !== fileId));
        }
    }, [files]);

    // ========== TRANSACTION GROUP LOGIC ==========

    /**
     * Holt den gemeinsamen Entity-Namen aus den Dateien
     */
    const getCommonEntityName = useCallback((documentIds: string[]): string | undefined => {
        const filesInGroup = files.filter(f => documentIds.includes(f.id));
        const entityNames = filesInGroup
            .map(f => f.classification?.matchedEntityName)
            .filter((name): name is string => !!name);

        // Ersten Entity-Namen zurückgeben (oder undefined)
        return entityNames[0];
    }, [files]);

    /**
     * Holt die nächste laufende Nummer für einen Entity-Namen
     */
    const getNextTransactionNumber = useCallback(async (entityName: string): Promise<number> => {
        // Versuche Backend abzufragen
        try {
            const nextNumber = await groupsService.getNextNumber(entityName);
            // Lokalen Counter aktualisieren falls höher
            if (!localNumberCounters[entityName] || nextNumber > localNumberCounters[entityName]) {
                setLocalNumberCounters(prev => ({
                    ...prev,
                    [entityName]: nextNumber
                }));
            }
            return nextNumber;
        } catch {
            // Fallback auf lokalen Counter
            const currentCount = localNumberCounters[entityName] || 0;
            const newCount = currentCount + 1;
            setLocalNumberCounters(prev => ({
                ...prev,
                [entityName]: newCount
            }));
            return newCount;
        }
    }, [localNumberCounters, setLocalNumberCounters]);

    /**
     * Erstellt einen neuen Vorgang aus den angegebenen Dokument-IDs
     */
    const createTransaction = useCallback(async (documentIds: string[]) => {
        if (documentIds.length < 2) {
            toast({
                title: 'Hinweis',
                description: 'Mindestens 2 Dokumente für einen Vorgang erforderlich',
                variant: 'default'
            });
            return;
        }

        // Prüfen ob Dokumente bereits in einer Gruppe sind
        const alreadyGrouped = documentIds.filter(id => {
            const file = files.find(f => f.id === id);
            return file?.transactionGroupId;
        });

        if (alreadyGrouped.length > 0) {
            toast({
                title: 'Hinweis',
                description: 'Einige Dokumente sind bereits in einem Vorgang',
                variant: 'default'
            });
            return;
        }

        // Entity-Namen und laufende Nummer ermitteln
        const entityName = getCommonEntityName(documentIds) || 'Vorgang';
        const nextNumber = await getNextTransactionNumber(entityName);
        const name = `${entityName}_${String(nextNumber).padStart(3, '0')}`;

        // Temporäre Gruppe im Frontend erstellen
        const tempGroup: TransactionGroup = {
            id: crypto.randomUUID(),
            name,
            documentIds,
            entityName: entityName !== 'Vorgang' ? entityName : undefined,
            createdAt: new Date(),
        };

        // State aktualisieren
        setTransactionGroups(prev => [...prev, tempGroup]);
        setFiles(prev => prev.map(f =>
            documentIds.includes(f.id)
                ? { ...f, transactionGroupId: tempGroup.id }
                : f
        ));
        setSelectedFileIds(new Set()); // Selection zurücksetzen

        // Backend-Sync (asynchron)
        try {
            const filesInGroup = files.filter(f => documentIds.includes(f.id));
            const backendDocIds = filesInGroup
                .map(f => f.documentId)
                .filter((id): id is string => !!id);

            if (backendDocIds.length >= 2) {
                // Entity-ID aus erstem Dokument mit Match
                const entityId = filesInGroup.find(f => f.classification?.matchedEntityId)
                    ?.classification?.matchedEntityId;

                const response = await groupsService.create({
                    name,
                    group_type: 'transaction',
                    document_ids: backendDocIds,
                    business_entity_id: entityId,
                });

                setTransactionGroups(prev => prev.map(g =>
                    g.id === tempGroup.id
                        ? { ...g, backendGroupId: response.id }
                        : g
                ));

                toast({
                    title: 'Vorgang erstellt',
                    description: `${name} mit ${backendDocIds.length} Dokumenten`,
                    variant: 'success'
                });
            }
        } catch (error) {
            logger.error('Backend-Gruppenerstellung fehlgeschlagen', error);
            toast({
                title: 'Hinweis',
                description: 'Vorgang lokal erstellt, Backend-Sync fehlgeschlagen',
                variant: 'default'
            });
        }
    }, [files, getCommonEntityName, getNextTransactionNumber]);

    /**
     * Fügt ein Dokument zu einem bestehenden Vorgang hinzu
     */
    const addToTransaction = useCallback(async (groupId: string, documentId: string) => {
        const group = transactionGroups.find(g => g.id === groupId);
        const file = files.find(f => f.id === documentId);
        if (!group || !file) return;

        // Prüfen ob bereits in einer Gruppe
        if (file.transactionGroupId) {
            if (file.transactionGroupId === groupId) return; // Schon in dieser Gruppe
            toast({
                title: 'Hinweis',
                description: 'Dokument ist bereits in einem anderen Vorgang',
                variant: 'default'
            });
            return;
        }

        // Frontend-State aktualisieren
        setTransactionGroups(prev => prev.map(g =>
            g.id === groupId
                ? { ...g, documentIds: [...g.documentIds, documentId] }
                : g
        ));
        setFiles(prev => prev.map(f =>
            f.id === documentId
                ? { ...f, transactionGroupId: groupId }
                : f
        ));

        // Backend-Sync
        if (group.backendGroupId && file.documentId) {
            try {
                await groupsService.addDocument(group.backendGroupId, file.documentId);
            } catch (error) {
                logger.error('Dokument zur Gruppe hinzufügen fehlgeschlagen', error);
            }
        }
    }, [transactionGroups, files]);

    /**
     * Entfernt ein Dokument aus einem Vorgang
     */
    const removeFromTransaction = useCallback(async (groupId: string, documentId: string) => {
        const group = transactionGroups.find(g => g.id === groupId);
        const file = files.find(f => f.id === documentId);
        if (!group) return;

        const newDocIds = group.documentIds.filter(id => id !== documentId);

        // Wenn nur noch 1 Dokument übrig, Gruppe auflösen
        if (newDocIds.length < 2) {
            await dissolveTransaction(groupId);
            return;
        }

        // Frontend-State aktualisieren
        setTransactionGroups(prev => prev.map(g =>
            g.id === groupId
                ? { ...g, documentIds: newDocIds }
                : g
        ));
        setFiles(prev => prev.map(f =>
            f.id === documentId
                ? { ...f, transactionGroupId: undefined }
                : f
        ));

        // Backend-Sync
        if (group.backendGroupId && file?.documentId) {
            try {
                await groupsService.removeDocument(group.backendGroupId, file.documentId);
            } catch (error) {
                logger.error('Dokument aus Gruppe entfernen fehlgeschlagen', error);
            }
        }
    }, [transactionGroups, files]);

    /**
     * Löst einen Vorgang auf (alle Dokumente werden wieder einzeln)
     */
    const dissolveTransaction = useCallback(async (groupId: string) => {
        const group = transactionGroups.find(g => g.id === groupId);
        if (!group) return;

        // Frontend-State aktualisieren
        setFiles(prev => prev.map(f =>
            group.documentIds.includes(f.id)
                ? { ...f, transactionGroupId: undefined }
                : f
        ));
        setTransactionGroups(prev => prev.filter(g => g.id !== groupId));

        // Backend-Sync
        if (group.backendGroupId) {
            try {
                await groupsService.delete(group.backendGroupId);
                toast({
                    title: 'Vorgang aufgelöst',
                    description: `${group.name} wurde aufgelöst`,
                    variant: 'default'
                });
            } catch (error) {
                logger.error('Gruppe löschen fehlgeschlagen', error);
            }
        }
    }, [transactionGroups]);

    /**
     * Benennt einen Vorgang um
     */
    const renameTransaction = useCallback(async (groupId: string, newName: string) => {
        const group = transactionGroups.find(g => g.id === groupId);
        if (!group) return;

        // Frontend-State aktualisieren
        setTransactionGroups(prev => prev.map(g =>
            g.id === groupId
                ? { ...g, name: newName }
                : g
        ));

        // Backend-Sync
        if (group.backendGroupId) {
            try {
                await groupsService.update(group.backendGroupId, { name: newName });
            } catch (error) {
                logger.error('Gruppe umbenennen fehlgeschlagen', error);
            }
        }
    }, [transactionGroups]);

    /**
     * Generiert einen Rename-Vorschlag für einen Vorgang basierend auf den Dokumentnamen
     */
    const generateGroupNameSuggestion = useCallback((groupId: string): string | undefined => {
        const group = transactionGroups.find(g => g.id === groupId);
        if (!group) return undefined;

        const groupFiles = files.filter(f => group.documentIds.includes(f.id));

        // Gemeinsamen Lieferantennamen finden (für Vorgang-Benennung)
        const supplierNames = groupFiles
            .map(f => f.classification?.renameSuggestion?.supplierName)
            .filter((name): name is string => !!name);

        if (supplierNames.length === 0) return undefined;

        // Prüfen ob alle denselben Lieferanten haben
        const uniqueSuppliers = [...new Set(supplierNames)];
        if (uniqueSuppliers.length !== 1) return undefined;

        const supplierName = uniqueSuppliers[0];

        // Jahr-Monat aus dem aktuellen Datum
        const now = new Date();
        const yearMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

        return `${supplierName}_${yearMonth}`;
    }, [transactionGroups, files]);

    /**
     * Bestätigt den Rename-Vorschlag für einen Vorgang
     */
    const [groupRenameLoadingId, setGroupRenameLoadingId] = useState<string | null>(null);

    const handleConfirmGroupRename = useCallback(async (groupId: string) => {
        const group = transactionGroups.find(g => g.id === groupId);
        if (!group || !group.suggestedGroupName) return;

        setGroupRenameLoadingId(groupId);

        try {
            // Name übernehmen
            await renameTransaction(groupId, group.suggestedGroupName);

            // Als applied markieren
            setTransactionGroups(prev => prev.map(g =>
                g.id === groupId
                    ? { ...g, suggestedGroupNameApplied: true }
                    : g
            ));

            toast({
                title: 'Vorgang umbenannt',
                description: `Neuer Name: ${group.suggestedGroupName}`,
                variant: 'success'
            });
        } catch (error) {
            logger.error('Vorgangs-Umbenennung fehlgeschlagen', error);
            toast({
                title: 'Fehler',
                description: 'Vorgang konnte nicht umbenannt werden',
                variant: 'destructive'
            });
        } finally {
            setGroupRenameLoadingId(null);
        }
    }, [transactionGroups, renameTransaction]);

    // Effect: Aktualisiere suggestedGroupName wenn Dateien sich ändern
    useEffect(() => {
        setTransactionGroups(prev => prev.map(group => {
            // Nicht aktualisieren wenn bereits applied
            if (group.suggestedGroupNameApplied) return group;

            const suggestion = generateGroupNameSuggestion(group.id);
            if (suggestion && suggestion !== group.suggestedGroupName) {
                return { ...group, suggestedGroupName: suggestion };
            }
            return group;
        }));
    }, [files, generateGroupNameSuggestion]);

    // ========== SELECTION LOGIC ==========

    /**
     * Handler für Datei-Auswahl (Shift-Klick für Bereich)
     */
    const handleFileSelect = useCallback((fileId: string, isShiftKey: boolean) => {
        const file = files.find(f => f.id === fileId);
        // Nur fertige Dateien ohne Gruppe können ausgewählt werden
        if (!file || file.transactionGroupId) return;
        if (file.status !== 'completed' && file.status !== 'awaiting_confirmation') return;

        setSelectedFileIds(prev => {
            const newSet = new Set(prev);

            if (isShiftKey && prev.size > 0) {
                // Shift-Klick: Bereich auswählen
                const ungroupedFiles = files.filter(f =>
                    !f.transactionGroupId &&
                    (f.status === 'completed' || f.status === 'awaiting_confirmation')
                );
                const fileIds = ungroupedFiles.map(f => f.id);
                const lastSelected = Array.from(prev).pop()!;
                const lastIndex = fileIds.indexOf(lastSelected);
                const currentIndex = fileIds.indexOf(fileId);

                if (lastIndex !== -1 && currentIndex !== -1) {
                    const [start, end] = [Math.min(lastIndex, currentIndex), Math.max(lastIndex, currentIndex)];
                    for (let i = start; i <= end; i++) {
                        newSet.add(fileIds[i]);
                    }
                }
            } else {
                // Einfacher Klick: Toggle
                if (newSet.has(fileId)) {
                    newSet.delete(fileId);
                } else {
                    newSet.add(fileId);
                }
            }

            return newSet;
        });
    }, [files]);

    /**
     * Handler für "Als Vorgang zusammenfassen" aus Kontextmenü
     */
    const handleCreateTransactionFromSelection = useCallback(() => {
        if (selectedFileIds.size < 2) {
            toast({
                title: 'Hinweis',
                description: 'Mindestens 2 Dokumente auswählen',
                variant: 'default'
            });
            return;
        }
        createTransaction(Array.from(selectedFileIds));
    }, [selectedFileIds, createTransaction]);

    // ========== DRAG & DROP HANDLERS ==========

    const handleDragStart = (event: DragStartEvent) => {
        setDragActiveId(event.active.id as string);
    };

    const handleDragOver = (event: DragOverEvent) => {
        const overId = event.over?.id;
        if (typeof overId === 'string') {
            setDragOverId(overId);
        } else {
            setDragOverId(null);
        }
    };

    const handleDragEnd = async (event: DragEndEvent) => {
        const { active, over } = event;
        setDragActiveId(null);
        setDragOverId(null);

        if (!over || active.id === over.id) return;

        const draggedFileId = active.id as string;
        const targetId = over.id as string;

        // Prüfen ob auf TransactionGroup gedroppt
        if (targetId.startsWith('group-')) {
            const groupId = targetId.replace('group-', '');
            await addToTransaction(groupId, draggedFileId);
            return;
        }

        // Auf eine andere Datei gedroppt -> neuen Vorgang erstellen
        const draggedFile = files.find(f => f.id === draggedFileId);
        const targetFile = files.find(f => f.id === targetId);

        if (!draggedFile || !targetFile) return;

        // Beide dürfen nicht bereits in einer Gruppe sein
        if (draggedFile.transactionGroupId || targetFile.transactionGroupId) {
            toast({
                title: 'Hinweis',
                description: 'Eines der Dokumente ist bereits in einem Vorgang',
                variant: 'default'
            });
            return;
        }

        // Nur fertige Dateien
        const validStatuses = ['completed', 'awaiting_confirmation'];
        if (!validStatuses.includes(draggedFile.status) || !validStatuses.includes(targetFile.status)) {
            return;
        }

        // Neuen Vorgang erstellen
        await createTransaction([draggedFileId, targetId]);
    };

    // Dragoverlay-Content
    const draggedFile = dragActiveId ? files.find(f => f.id === dragActiveId) : null;

    // ========== POLLING ==========

    const filesRef = useRef(files);
    useEffect(() => {
        filesRef.current = files;
    }, [files]);

    useEffect(() => {
        // FIX: mounted flag für cleanup bei Unmount (verhindert state updates nach unmount)
        let isMounted = true;

        const pollStatus = async () => {
            // FIX: Early exit wenn unmounted
            if (!isMounted) return;

            const currentFiles = filesRef.current;
            const processingFiles = currentFiles.filter(f =>
                (f.status === 'processing' && f.documentId) ||
                (f.status === 'awaiting_confirmation' && f.documentId &&
                 (!f.classification || f.classification.invoiceDirection === 'unknown'))
            );
            // FIX: Early exit wenn keine processing files (verhindert unnötige API-Calls)
            if (processingFiles.length === 0) return;

            for (const file of processingFiles) {
                try {
                    const doc = await documentsService.getById(file.documentId!);

                    let taskProgress: number | undefined;
                    let taskMessage: string | undefined;
                    if (file.taskId) {
                        try {
                            const taskStatus = await tasksService.getStatus(file.taskId);
                            taskProgress = taskStatus.progress;
                            taskMessage = taskStatus.message;
                        } catch {
                            // Task might not exist yet
                        }
                    }

                    const shouldUseQuickClassification =
                        doc.quickClassificationStatus === 'completed' &&
                        doc.quickClassificationResult &&
                        doc.quickClassificationResult.direction !== 'unknown' &&
                        (!file.classification ||
                         file.classification.invoiceDirection === 'unknown' ||
                         (!file.classification.renameSuggestion && doc.quickClassificationResult.renameSuggestion));

                    if (shouldUseQuickClassification) {
                        const qcResult = doc.quickClassificationResult!;
                        const tagWasAssigned = qcResult.tagAssigned === true;

                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? {
                                    ...f,
                                    classification: {
                                        invoiceDirection: qcResult.direction || 'unknown',
                                        confidence: qcResult.confidence || 0,
                                        reason: qcResult.reason,
                                        matchedEntityId: qcResult.matchedEntityId,
                                        matchedEntityName: qcResult.matchedEntityName,
                                        matchedEntityType: qcResult.matchedEntityType,
                                        entityMatchMethod: qcResult.entityMatchMethod,
                                        entityConfidence: qcResult.entityConfidence,
                                        entityAutoLinked: qcResult.entityAutoLinked,
                                        renameSuggestion: qcResult.renameSuggestion,
                                    },
                                    status: tagWasAssigned ? 'completed' as const : f.status,
                                    confirmedDirection: tagWasAssigned ? qcResult.direction as 'incoming' | 'outgoing' : undefined,
                                }
                                : f
                        ));
                    }

                    if (doc.ocrStatus === 'completed') {
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
                        setFiles(prev => prev.map(f =>
                            f.id === file.id
                                ? { ...f, ocrProgress: taskProgress, ocrMessage: taskMessage }
                                : f
                        ));
                    }
                } catch (e) {
                    logger.error('Status-Polling fehlgeschlagen', e);
                }
            }
        };

        // FIX: 2000ms statt 1000ms - reduziert Backend-Last um 50%
        const interval = setInterval(pollStatus, 2000);
        return () => {
            // FIX: Cleanup - verhindert state updates nach unmount
            isMounted = false;
            clearInterval(interval);
        };
    }, []);

    // ========== RENDER ==========

    // Dateien die NICHT in einer Gruppe sind
    const ungroupedFiles = files.filter(f => !f.transactionGroupId);

    return (
        <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
        >
            <div className="max-w-4xl mx-auto py-8 px-4">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold tracking-tight">Dokumente hochladen</h1>
                    <p className="text-muted-foreground mt-2">
                        Laden Sie Ihre Dokumente hoch. Die OCR-Verarbeitung startet automatisch.
                    </p>
                </div>

                {recentEntities.length > 0 && (
                    <RecentlyUsedSection
                        items={recentEntities}
                        onItemClick={() => {}}
                        onClear={clearRecentEntities}
                        title="Zuletzt verknüpfte Entitäten"
                        maxDisplay={5}
                        className="mb-4"
                    />
                )}

                <div className="space-y-8">
                    {/* Upload Dropzone */}
                    <div className="bg-background rounded-2xl border shadow-sm p-6">
                        <UploadDropzone onFilesAdd={handleFilesAdd} />
                    </div>

                    {/* Transaction Groups (Vorgänge) */}
                    {transactionGroups.length > 0 && (
                        <div className="bg-background rounded-2xl border shadow-sm p-6 space-y-4">
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                <Layers className="w-5 h-5" />
                                Vorgänge
                            </h3>
                            <AnimatePresence>
                                {transactionGroups.map((group) => (
                                    <TransactionGroupCard
                                        key={group.id}
                                        group={group}
                                        files={files}
                                        onRemoveDocument={(docId) => removeFromTransaction(group.id, docId)}
                                        onDissolve={() => dissolveTransaction(group.id)}
                                        onRename={(newName) => renameTransaction(group.id, newName)}
                                        isDropTarget={dragOverId === `group-${group.id}`}
                                        onChangeDocumentDirection={handleChangeDirection}
                                        onConfirmDocumentRename={handleConfirmRename}
                                        renameLoadingIds={renameLoadingIds}
                                        onConfirmGroupRename={() => handleConfirmGroupRename(group.id)}
                                        isGroupRenameLoading={groupRenameLoadingId === group.id}
                                        onRemoveFile={handleRemove}
                                    />
                                ))}
                            </AnimatePresence>
                        </div>
                    )}

                    {/* File List (nur ungruppierte) */}
                    {ungroupedFiles.length > 0 && (
                        <ContextMenu>
                            <ContextMenuTrigger asChild>
                                <div className="bg-background rounded-2xl border shadow-sm p-6">
                                    <UploadFileList
                                        files={ungroupedFiles}
                                        onRemove={handleRemove}
                                        onChangeDirection={handleChangeDirection}
                                        onConfirmRename={handleConfirmRename}
                                        renameLoadingIds={renameLoadingIds}
                                        selectedFileIds={selectedFileIds}
                                        onFileSelect={handleFileSelect}
                                        dragOverId={dragOverId}
                                        dragActiveId={dragActiveId}
                                    />
                                </div>
                            </ContextMenuTrigger>
                            <ContextMenuContent>
                                <ContextMenuItem
                                    disabled={selectedFileIds.size < 2}
                                    onClick={handleCreateTransactionFromSelection}
                                    className="gap-2"
                                >
                                    <Layers className="w-4 h-4" />
                                    Als Vorgang zusammenfassen
                                    {selectedFileIds.size > 0 && (
                                        <Badge variant="secondary" className="ml-auto">
                                            {selectedFileIds.size}
                                        </Badge>
                                    )}
                                </ContextMenuItem>
                                <ContextMenuSeparator />
                                <ContextMenuItem
                                    disabled={selectedFileIds.size === 0}
                                    onClick={() => setSelectedFileIds(new Set())}
                                >
                                    Auswahl aufheben
                                </ContextMenuItem>
                            </ContextMenuContent>
                        </ContextMenu>
                    )}

                    {/* Hint für Mehrfachauswahl */}
                    {ungroupedFiles.length >= 2 && transactionGroups.length === 0 && (
                        <p className="text-sm text-muted-foreground text-center">
                            Tipp: Ziehen Sie Dokumente aufeinander oder wählen Sie mehrere mit Shift+Klick aus und nutzen Sie das Kontextmenü (Rechtsklick), um einen Vorgang zu erstellen.
                        </p>
                    )}
                </div>
            </div>

            {/* Drag Overlay */}
            <DragOverlay>
                {draggedFile && (
                    <div className="flex items-center gap-3 p-3 bg-card border rounded-lg shadow-xl">
                        <FileText className="w-5 h-5 text-primary" />
                        <span className="font-medium truncate max-w-[200px]">
                            {draggedFile.renamedFilename || draggedFile.originalFilename || draggedFile.file?.name || 'Dokument'}
                        </span>
                        <Badge variant="secondary">Zum Vorgang</Badge>
                    </div>
                )}
            </DragOverlay>
        </DndContext>
    );
}
