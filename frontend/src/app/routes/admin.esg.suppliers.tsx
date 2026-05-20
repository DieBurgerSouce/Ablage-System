/**
 * ESG Lieferanten-Bewertung - Supplier Ratings Page
 *
 * Verwaltet ESG-Bewertungen und Ratings von Lieferanten.
 */

import { createFileRoute } from '@tanstack/react-router';
import { SupplierRatingsPage } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/suppliers')({
    component: SupplierRatingsPage,
});
