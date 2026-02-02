/**
 * Document Components Index
 *
 * Exportiert alle Dokument-Komponenten:
 * - DocumentCard - Einzelne Dokument-Karte
 * - DocumentGrid - Grid-Ansicht
 * - DocumentBadges - Status-Badges
 * - DraggableDocument - Drag-faehige Dokument-Karte
 * - DroppableFolder - Drop-faehiger Ordner
 */

export { DocumentCard } from "./DocumentCard"
export { DocumentGrid } from "./DocumentGrid"
export { DocumentTypeIcon, OCRStatusBadge } from "./DocumentBadges"

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
