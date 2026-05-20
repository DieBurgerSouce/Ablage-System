/**
 * Document Components Index
 *
 * Exportiert alle Dokument-Komponenten:
 * - DocumentCard - Einzelne Dokument-Karte
 * - DocumentGrid - Grid-Ansicht
 * - DocumentBadges - Status-Badges
 * - DraggableDocument - Drag-fähige Dokument-Karte
 * - DroppableFolder - Drop-fähiger Ordner
 */

export { DocumentCard } from "./DocumentCard"
export { DocumentGrid } from "./DocumentGrid"
export { DocumentTypeIcon, OCRStatusBadge } from "./DocumentBadges"
export { LanguageBadge, type LanguageBadgeProps } from "./LanguageBadge"
export { LanguageOverrideDialog, type LanguageOverrideDialogProps } from "./LanguageOverrideDialog"

// Drag & Drop Components
export {
  DraggableDocument,
  DragOverlayDocument,
  type DraggableDocumentProps,
  type DragOverlayDocumentProps,
} from "./DraggableDocument"

export {
  DroppableFolder,
  FolderDropZone,
  type FolderData,
  type DroppableFolderProps,
  type FolderDropZoneProps,
} from "./DroppableFolder"

// Bulk Operations - re-export from bulk module
export {
  DocumentBulkActionsBar,
  type DocumentBulkActionsBarProps,
  type Folder as BulkActionFolder,
} from "../bulk"
