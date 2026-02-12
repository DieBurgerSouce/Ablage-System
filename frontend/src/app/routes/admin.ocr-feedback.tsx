/**
 * OCR Feedback Admin Route
 *
 * Route für das OCR Feedback Leaderboard Dashboard.
 */

import { createFileRoute } from '@tanstack/react-router';
import { OCRFeedbackPage } from '@/features/ocr-feedback';

export const Route = createFileRoute('/admin/ocr-feedback')({
  component: OCRFeedbackPage,
});
