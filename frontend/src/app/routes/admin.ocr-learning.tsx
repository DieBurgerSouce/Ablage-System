/**
 * OCR Self-Learning Admin Route
 *
 * Route für das selbstlernende OCR-System Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { OCRLearningDashboard } from '@/features/ocr-learning';

export const Route = createFileRoute('/admin/ocr-learning')({
  component: OCRLearningDashboard,
});
