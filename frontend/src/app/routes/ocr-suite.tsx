import { createFileRoute } from '@tanstack/react-router';
import { OcrSuitePage } from '@/features/ocr-suite';

export const Route = createFileRoute('/ocr-suite')({
  component: OcrSuitePageRoute,
});

function OcrSuitePageRoute() {
  return <OcrSuitePage />;
}
