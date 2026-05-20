/**
 * PrivatPage - Dashboard für den Privat-Bereich
 *
 * Zeigt Übersicht mit Statistiken, Fristen und Quick-Links
 *
 * Refactored to use React Query for:
 * - Automatic caching
 * - Background refetching
 * - Error handling
 * - Loading states
 */

import * as React from 'react';
import { useNavigate } from '@tanstack/react-router';
import { PrivatDashboard } from '../components/PrivatDashboard';
import { PrivatSpaceList } from '../components/PrivatSpaceList';
import {
  CreateSpaceDialog,
  EditSpaceDialog,
  DeleteSpaceDialog,
} from '../components/dialogs';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  useDashboardStats,
  useSpaces,
  useFinancialSummary,
  useDeadlineWidget,
  useCreateSpace,
  useUpdateSpace,
  useDeleteSpace,
} from '../hooks/use-privat-queries';
import type { PrivatSpaceWithStats, PrivatSpaceCreate, PrivatSpaceUpdate } from '@/types/privat';

export function PrivatPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = React.useState('dashboard');

  // Dialog states
  const [createDialogOpen, setCreateDialogOpen] = React.useState(false);
  const [editDialogOpen, setEditDialogOpen] = React.useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [selectedSpace, setSelectedSpace] = React.useState<PrivatSpaceWithStats | null>(null);

  // React Query hooks - automatic caching and refetching
  const {
    data: spaces = [],
    isLoading: spacesLoading,
    error: spacesError,
  } = useSpaces();

  const {
    data: stats,
    isLoading: statsLoading,
    error: statsError,
  } = useDashboardStats();

  // Get first space ID for financial summary and deadlines
  const firstSpaceId = spaces[0]?.id;

  const {
    data: financial,
    isLoading: financialLoading,
  } = useFinancialSummary(firstSpaceId ?? '', {
    enabled: !!firstSpaceId,
  });

  const {
    data: deadlines,
    isLoading: deadlinesLoading,
  } = useDeadlineWidget(firstSpaceId ?? '', {
    enabled: !!firstSpaceId,
  });

  // Mutations
  const createSpaceMutation = useCreateSpace();
  const updateSpaceMutation = useUpdateSpace();
  const deleteSpaceMutation = useDeleteSpace();

  // Aggregate loading and error states
  const isLoading = spacesLoading || statsLoading || financialLoading || deadlinesLoading;
  const error = spacesError || statsError || null;

  // Dialog handlers
  const handleOpenCreateDialog = React.useCallback(() => {
    setCreateDialogOpen(true);
  }, []);

  const handleCreateSpace = React.useCallback(async (data: PrivatSpaceCreate) => {
    await createSpaceMutation.mutateAsync(data);
  }, [createSpaceMutation]);

  const handleOpenEditDialog = React.useCallback((space: PrivatSpaceWithStats) => {
    setSelectedSpace(space);
    setEditDialogOpen(true);
  }, []);

  const handleEditSpace = React.useCallback(async (spaceId: string, data: PrivatSpaceUpdate) => {
    await updateSpaceMutation.mutateAsync({ spaceId, data });
  }, [updateSpaceMutation]);

  const handleOpenDeleteDialog = React.useCallback((space: PrivatSpaceWithStats) => {
    setSelectedSpace(space);
    setDeleteDialogOpen(true);
  }, []);

  const handleDeleteSpace = React.useCallback(async (spaceId: string) => {
    await deleteSpaceMutation.mutateAsync(spaceId);
  }, [deleteSpaceMutation]);

  const handleSpaceSettings = React.useCallback((space: PrivatSpaceWithStats) => {
    navigate({
      to: '/privat/spaces/$spaceId/settings' as string,
      params: { spaceId: space.id },
    } as never);
  }, [navigate]);

  return (
    <div className="p-8">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="dashboard">Übersicht</TabsTrigger>
          <TabsTrigger value="spaces">Bereiche</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <PrivatDashboard
            stats={stats}
            financial={financial}
            deadlines={deadlines}
            isLoading={isLoading}
            error={error}
            spaceId={firstSpaceId}
          />
        </TabsContent>

        <TabsContent value="spaces">
          <PrivatSpaceList
            spaces={spaces}
            isLoading={spacesLoading}
            error={spacesError instanceof Error ? spacesError : null}
            onCreate={handleOpenCreateDialog}
            onEdit={handleOpenEditDialog}
            onDelete={handleOpenDeleteDialog}
            onSettings={handleSpaceSettings}
          />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <CreateSpaceDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onSubmit={handleCreateSpace}
        isLoading={createSpaceMutation.isPending}
      />

      <EditSpaceDialog
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
        space={selectedSpace}
        onSubmit={handleEditSpace}
        isLoading={updateSpaceMutation.isPending}
      />

      <DeleteSpaceDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        space={selectedSpace}
        onConfirm={handleDeleteSpace}
        isLoading={deleteSpaceMutation.isPending}
      />
    </div>
  );
}

export default PrivatPage;
