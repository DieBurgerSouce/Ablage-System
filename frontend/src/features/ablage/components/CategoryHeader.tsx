/**
 * CategoryHeader - Breadcrumb und Titel für Kategorie-Seiten
 */

import { Link } from '@tanstack/react-router';
import { ArrowLeft, FolderOpen, Upload } from 'lucide-react';
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

export function CategoryHeader({
  entityType,
  entityId,
  entityName,
  folderId,
  folderName,
  categoryInfo,
  onUploadClick,
}: CategoryHeaderProps) {
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
    <div className="flex items-center gap-4">
      <Link to={folderPath} params={folderParams}>
        <Button variant="ghost" size="icon" aria-label="Zurück zur Ordner-Übersicht">
          <ArrowLeft className="w-5 h-5" />
        </Button>
      </Link>
      <div>
        <nav aria-label="Breadcrumb">
          <ol className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <li>
              <Link to={basePath} className="hover:text-foreground transition-colors">
                {isCustomer ? 'Kunden' : 'Lieferanten'}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li>
              <Link to={entityPath} params={entityParams} className="hover:text-foreground transition-colors">
                {entityName}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li>
              <Link to={folderPath} params={folderParams} className="hover:text-foreground transition-colors">
                {folderName}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li aria-current="page" className="text-foreground font-medium">
              {categoryInfo?.label}
            </li>
          </ol>
        </nav>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <FolderOpen className={`w-8 h-8 ${colorClass}`} aria-hidden="true" />
          {categoryInfo?.label}
          {categoryInfo?.shortCode && (
            <span className="text-lg text-muted-foreground">
              ({categoryInfo.shortCode})
            </span>
          )}
        </h1>
      </div>
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
