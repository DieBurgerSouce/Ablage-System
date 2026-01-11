/**
 * CategoryHeader - Breadcrumb und Titel für Kategorie-Seiten
 *
 * Besteht aus zwei getrennten Komponenten:
 * - CategoryBreadcrumb: Navigation-Pfad (ganz oben)
 * - CategoryTitle: Seitentitel mit Back-Button
 */

import { Link } from '@tanstack/react-router';
import { ArrowLeft, FolderOpen, Upload, Home, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { DocumentCategoryInfo } from '../types';

interface CategoryHeaderProps {
  entityType: 'customer' | 'supplier';
  entityId: string;
  entityName: string;
  folderId: string;
  folderName: string;
  categoryInfo: DocumentCategoryInfo | undefined;
  onUploadClick?: () => void;
}

/**
 * CategoryBreadcrumb - Nur der Breadcrumb-Pfad
 * Wird ganz oben auf der Seite angezeigt (wie auf anderen Seiten)
 */
export function CategoryBreadcrumb({
  entityType,
  entityId,
  entityName,
  folderId,
  folderName,
  categoryInfo,
}: Omit<CategoryHeaderProps, 'onUploadClick'>) {
  const isCustomer = entityType === 'customer';
  const basePath = isCustomer ? '/kunden' : '/lieferanten';
  const colorClass = isCustomer ? 'text-amber-500' : 'text-blue-500';

  // Pfade für Breadcrumb
  const folderPath = isCustomer
    ? '/kunden/$customerId/$folderId'
    : '/lieferanten/$supplierId/$folderId';
  const folderParams = isCustomer
    ? { customerId: entityId, folderId }
    : { supplierId: entityId, folderId };
  const entityPath = isCustomer ? '/kunden/$customerId' : '/lieferanten/$supplierId';
  const entityParams = isCustomer
    ? { customerId: entityId }
    : { supplierId: entityId };

  return (
    <nav aria-label="Breadcrumb" className="flex items-center text-sm text-muted-foreground">
      <ol className="flex items-center gap-1">
        <li className="flex items-center">
          <Link to="/" className="hover:text-foreground transition-colors flex items-center gap-1">
            <Home className="w-4 h-4" />
          </Link>
        </li>
        <ChevronRight className="w-4 h-4 mx-1 text-muted-foreground/50" />
        <li>
          <span className={`inline-block w-2 h-2 rounded-full mr-2 ${isCustomer ? 'bg-amber-500' : 'bg-blue-500'}`} />
          <Link to={basePath} className="hover:text-foreground transition-colors">
            {isCustomer ? 'Kunden' : 'Lieferanten'}
          </Link>
        </li>
        <ChevronRight className="w-4 h-4 mx-1 text-muted-foreground/50" />
        <li>
          <Link to={entityPath} params={entityParams} className="hover:text-foreground transition-colors">
            {entityName}
          </Link>
        </li>
        <ChevronRight className="w-4 h-4 mx-1 text-muted-foreground/50" />
        <li>
          <Link to={folderPath} params={folderParams} className="hover:text-foreground transition-colors">
            {folderName}
          </Link>
        </li>
        <ChevronRight className="w-4 h-4 mx-1 text-muted-foreground/50" />
        <li aria-current="page" className="text-foreground font-medium">
          {categoryInfo?.label}
        </li>
      </ol>
    </nav>
  );
}

/**
 * CategoryTitle - Seitentitel mit Back-Button und Upload
 */
export function CategoryTitle({
  entityType,
  entityId,
  folderId,
  categoryInfo,
  onUploadClick,
}: Pick<CategoryHeaderProps, 'entityType' | 'entityId' | 'folderId' | 'categoryInfo' | 'onUploadClick'>) {
  const isCustomer = entityType === 'customer';
  const colorClass = isCustomer ? 'text-amber-500' : 'text-blue-500';

  const folderPath = isCustomer
    ? '/kunden/$customerId/$folderId'
    : '/lieferanten/$supplierId/$folderId';
  const folderParams = isCustomer
    ? { customerId: entityId, folderId }
    : { supplierId: entityId, folderId };

  return (
    <div className="flex items-center gap-4">
      <Link to={folderPath} params={folderParams}>
        <Button variant="ghost" size="icon" aria-label="Zurück zur Ordner-Übersicht">
          <ArrowLeft className="w-5 h-5" />
        </Button>
      </Link>
      <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
        <FolderOpen className={`w-8 h-8 ${colorClass}`} aria-hidden="true" />
        {categoryInfo?.label}
        {categoryInfo?.shortCode && (
          <span className="text-lg text-muted-foreground">
            ({categoryInfo.shortCode})
          </span>
        )}
      </h1>
      {onUploadClick && (
        <div className="ml-auto">
          <Button className="gap-2" onClick={onUploadClick}>
            <Upload className="w-4 h-4" aria-hidden="true" />
            Dokument hochladen
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * CategoryHeader - Legacy-Komponente (kombiniert Breadcrumb + Title)
 * @deprecated Verwende CategoryBreadcrumb + CategoryTitle separat
 */
export function CategoryHeader(props: CategoryHeaderProps) {
  return (
    <div className="space-y-4">
      <CategoryBreadcrumb {...props} />
      <CategoryTitle {...props} />
    </div>
  );
}
