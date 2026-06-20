/**
 * PrivatFolderTree - Hierarchische Ordneransicht
 *
 * Zeigt die Ordnerstruktur als navigierbaren Baum
 */

import * as React from 'react';
import { Link } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible';
import {
  ChevronRight,
  ChevronDown,
  FolderOpen,
  Folder,
  FolderPlus,
  Edit2,
  Trash2,
  Plus,
  Search,
} from 'lucide-react';
import type { PrivatFolderTree as FolderTreeType } from '@/types/privat';
import { cn } from '@/lib/utils';

interface PrivatFolderTreeProps {
  folders: FolderTreeType[];
  isLoading?: boolean;
  selectedFolderId?: string;
  spaceId: string;
  onSelect?: (folder: FolderTreeType) => void;
  onCreate?: (parentId?: string) => void;
  onEdit?: (folder: FolderTreeType) => void;
  onDelete?: (folder: FolderTreeType) => void;
  className?: string;
}

export function PrivatFolderTree({
  folders,
  isLoading,
  selectedFolderId,
  spaceId,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
  className,
}: PrivatFolderTreeProps) {
  const [searchQuery, setSearchQuery] = React.useState('');
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set());

  // Auto-expand folders to show selected folder
  React.useEffect(() => {
    if (selectedFolderId) {
      const findParentIds = (
        folders: FolderTreeType[],
        targetId: string,
        parentIds: string[] = []
      ): string[] | null => {
        for (const folder of folders) {
          if (folder.id === targetId) {
            return parentIds;
          }
          if (folder.children.length > 0) {
            const result = findParentIds(folder.children, targetId, [
              ...parentIds,
              folder.id,
            ]);
            if (result) return result;
          }
        }
        return null;
      };

      const parentIds = findParentIds(folders, selectedFolderId);
      if (parentIds) {
        setExpandedIds((prev) => new Set([...prev, ...parentIds]));
      }
    }
  }, [selectedFolderId, folders]);

  const toggleExpanded = (folderId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
      return next;
    });
  };

  const filterFolders = (
    folders: FolderTreeType[],
    query: string
  ): FolderTreeType[] => {
    if (!query) return folders;

    const lowerQuery = query.toLowerCase();
    const filter = (folder: FolderTreeType): FolderTreeType | null => {
      const matchesQuery = folder.name.toLowerCase().includes(lowerQuery);
      const filteredChildren = folder.children
        .map(filter)
        .filter((c): c is FolderTreeType => c !== null);

      if (matchesQuery || filteredChildren.length > 0) {
        return {
          ...folder,
          children: filteredChildren,
        };
      }
      return null;
    };

    return folders.map(filter).filter((f): f is FolderTreeType => f !== null);
  };

  const filteredFolders = filterFolders(folders, searchQuery);

  if (isLoading) {
    return (
      <div className={cn('space-y-2 p-2', className)}>
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-8" />
        ))}
      </div>
    );
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Search */}
      <div className="p-2 border-b">
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Ordner suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      {/* Tree */}
      <ScrollArea className="flex-1">
        <div className="p-2">
          {folders.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Folder className="h-12 w-12 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Keine Ordner vorhanden</p>
              {onCreate && (
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => onCreate()}
                  className="mt-2"
                >
                  <Plus className="mr-1 h-3 w-3" />
                  Ordner erstellen
                </Button>
              )}
            </div>
          ) : filteredFolders.length === 0 ? (
            <div className="text-center py-4 text-muted-foreground text-sm">
              Keine Ordner gefunden
            </div>
          ) : (
            <div className="space-y-1">
              {filteredFolders.map((folder) => (
                <FolderNode
                  key={folder.id}
                  folder={folder}
                  spaceId={spaceId}
                  level={0}
                  selectedId={selectedFolderId}
                  expandedIds={expandedIds}
                  onToggle={toggleExpanded}
                  onSelect={onSelect}
                  onCreate={onCreate}
                  onEdit={onEdit}
                  onDelete={onDelete}
                />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Actions */}
      {onCreate && (
        <div className="p-2 border-t">
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => onCreate()}
          >
            <FolderPlus className="mr-2 h-4 w-4" />
            Neuer Ordner
          </Button>
        </div>
      )}
    </div>
  );
}

interface FolderNodeProps {
  folder: FolderTreeType;
  spaceId: string;
  level: number;
  selectedId?: string;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelect?: (folder: FolderTreeType) => void;
  onCreate?: (parentId?: string) => void;
  onEdit?: (folder: FolderTreeType) => void;
  onDelete?: (folder: FolderTreeType) => void;
}

function FolderNode({
  folder,
  spaceId,
  level,
  selectedId,
  expandedIds,
  onToggle,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
}: FolderNodeProps) {
  const hasChildren = folder.children.length > 0;
  const isExpanded = expandedIds.has(folder.id);
  const isSelected = folder.id === selectedId;

  return (
    <div>
      <ContextMenu>
        <ContextMenuTrigger>
          <div
            className={cn(
              'flex items-center gap-1 px-2 py-1.5 rounded-md cursor-pointer hover:bg-muted transition-colors',
              isSelected && 'bg-muted'
            )}
            style={{ paddingLeft: `${level * 16 + 8}px` }}
            onClick={() => onSelect?.(folder)}
          >
            {/* Expand/Collapse */}
            {hasChildren ? (
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 p-0"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggle(folder.id);
                }}
              >
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </Button>
            ) : (
              <span className="w-5" />
            )}

            {/* Icon */}
            {isExpanded ? (
              <FolderOpen
                className="h-4 w-4 flex-shrink-0"
                style={{ color: folder.color || undefined }}
              />
            ) : (
              <Folder
                className="h-4 w-4 flex-shrink-0"
                style={{ color: folder.color || undefined }}
              />
            )}

            {/* Name */}
            <Link
              to="/privat/spaces/$spaceId"
              params={{ spaceId }}
              className="flex-1 truncate text-sm hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {folder.name}
            </Link>

            {/* Count */}
            {folder.documentCount > 0 && (
              <span className="text-xs text-muted-foreground">
                {folder.documentCount}
              </span>
            )}
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem onClick={() => onSelect?.(folder)}>
            <FolderOpen className="mr-2 h-4 w-4" />
            Öffnen
          </ContextMenuItem>
          <ContextMenuItem onClick={() => onCreate?.(folder.id)}>
            <FolderPlus className="mr-2 h-4 w-4" />
            Unterordner erstellen
          </ContextMenuItem>
          <ContextMenuSeparator />
          <ContextMenuItem onClick={() => onEdit?.(folder)}>
            <Edit2 className="mr-2 h-4 w-4" />
            Umbenennen
          </ContextMenuItem>
          <ContextMenuItem
            onClick={() => onDelete?.(folder)}
            className="text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Löschen
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>

      {/* Children */}
      {hasChildren && (
        <Collapsible open={isExpanded}>
          <CollapsibleContent>
            {folder.children.map((child) => (
              <FolderNode
                key={child.id}
                folder={child}
                spaceId={spaceId}
                level={level + 1}
                selectedId={selectedId}
                expandedIds={expandedIds}
                onToggle={onToggle}
                onSelect={onSelect}
                onCreate={onCreate}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

export default PrivatFolderTree;
