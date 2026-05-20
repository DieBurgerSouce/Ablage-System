/**
 * Tour: Dokumente hochladen
 *
 * Fuehrt den Benutzer durch den Upload- und OCR-Prozess.
 */

import type { Tour } from '../types'

export const documentUploadTour: Tour = {
  id: 'dokument-hochladen',
  name: 'Dokument hochladen & verarbeiten',
  description: 'Erfahren Sie, wie Sie Dokumente hochladen und per OCR verarbeiten.',
  category: 'dokumente',
  estimatedMinutes: 3,
  badge: {
    id: 'archivar',
    name: 'Archivar',
    description: 'Sie wissen jetzt, wie man Dokumente hochlaedt und verarbeitet!',
    icon: 'Archive',
  },
  steps: [
    {
      id: 'upload-button-finden',
      title: 'Dokumente hochladen',
      description:
        'Der Upload-Button befindet sich oben in der Dokumentenliste. Sie koennen Dateien auch per Drag & Drop direkt auf die Seite ziehen.',
      targetSelector: '[data-tour="upload-button"]',
      position: 'bottom',
      order: 1,
      icon: 'Upload',
    },
    {
      id: 'upload-datei-auswaehlen',
      title: 'Dateiformate',
      description:
        'Unterstuetzte Formate: PDF, PNG, JPG und TIFF. Sie koennen einzelne Dateien oder ganze Ordner auswaehlen.',
      targetSelector: '[data-tour="upload-dropzone"]',
      position: 'bottom',
      order: 2,
      icon: 'File',
    },
    {
      id: 'upload-ocr-backend',
      title: 'OCR-Backend',
      description:
        'Waehlen Sie das passende OCR-Backend: DeepSeek fuer beste Qualitaet bei deutschen Texten, GOT-OCR fuer Tabellen oder Surya als schnelle Alternative. "Auto" waehlt automatisch das beste Backend.',
      targetSelector: '[data-tour="ocr-backend-select"]',
      position: 'bottom',
      order: 3,
      icon: 'Cpu',
    },
    {
      id: 'upload-batch',
      title: 'Batch-Upload',
      description:
        'Laden Sie mehrere Dokumente gleichzeitig hoch. Der Batch-Upload verarbeitet alle Dateien parallel und zeigt den Fortschritt in Echtzeit an.',
      targetSelector: '[data-tour="batch-upload"]',
      position: 'bottom',
      order: 4,
      icon: 'Files',
    },
    {
      id: 'upload-fertig',
      title: 'Fertig!',
      description:
        'Sie wissen jetzt, wie Sie Dokumente hochladen und verarbeiten. Als naechstes: Lernen Sie, wie Sie OCR-Ergebnisse pruefen und korrigieren.',
      position: 'center',
      order: 5,
      icon: 'CheckCircle',
    },
  ],
}
