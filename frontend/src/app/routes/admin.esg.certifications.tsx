/**
 * ESG Zertifizierungen - Certifications Page
 *
 * Verwaltet ESG-Zertifizierungen und deren Gültigkeit.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CertificationsPage } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/certifications')({
    component: CertificationsPage,
});
