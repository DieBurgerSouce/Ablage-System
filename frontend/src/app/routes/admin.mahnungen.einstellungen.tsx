/**
 * Admin Mahnungen - Einstellungen
 *
 * Konfiguration des Mahnwesens (Stufen, Gebuehren, Automatisierung)
 */

import { createFileRoute } from '@tanstack/react-router';
import { MahnwesenSettings } from '@/features/banking/components/MahnwesenSettings';

export const Route = createFileRoute('/admin/mahnungen/einstellungen')({
    component: EinstellungenPage,
});

function EinstellungenPage() {
    return <MahnwesenSettings />;
}
