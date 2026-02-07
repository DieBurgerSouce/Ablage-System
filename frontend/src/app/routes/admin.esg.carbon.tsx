/**
 * ESG CO2-Fussabdruck - Carbon Footprint Page
 *
 * Verwaltet CO2-Emissionen und Umweltkennzahlen.
 */

import { createFileRoute } from '@tanstack/react-router';
import { CarbonFootprintPage } from '@/features/esg';

export const Route = createFileRoute('/admin/esg/carbon')({
    component: CarbonFootprintPage,
});
