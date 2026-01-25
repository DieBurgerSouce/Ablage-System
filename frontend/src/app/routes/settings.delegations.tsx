/**
 * Settings Delegations Route
 *
 * Vertretungsregelungen - Manage your delegations
 */

import { createFileRoute } from '@tanstack/react-router';
import { DelegationPortal } from '@/features/settings/delegations';

export const Route = createFileRoute('/settings/delegations')({
  component: DelegationPortal,
});
