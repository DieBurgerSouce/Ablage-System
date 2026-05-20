/**
 * Tour: OCR-Ergebnisse pruefen & korrigieren
 *
 * Fuehrt den Benutzer durch das Pruefen und Korrigieren von OCR-Ergebnissen.
 */

import type { Tour } from '../types'

export const ocrResultsTour: Tour = {
  id: 'ocr-korrektur',
  name: 'OCR-Ergebnisse korrigieren',
  description: 'Erfahren Sie, wie Sie OCR-Ergebnisse pruefen und korrigieren.',
  category: 'fortgeschritten',
  estimatedMinutes: 2,
  badge: {
    id: 'qualitaetssicherer',
    name: 'Qualitaetssicherer',
    description: 'Sie wissen, wie man OCR-Ergebnisse professionell korrigiert!',
    icon: 'ShieldCheck',
  },
  steps: [
    {
      id: 'ocr-ergebnis',
      title: 'OCR-Ergebnis',
      description:
        'Nach der Verarbeitung sehen Sie den erkannten Text neben dem Originaldokument. Die OCR-Texterkennung extrahiert automatisch alle Textinhalte.',
      targetSelector: '[data-tour="ocr-text-panel"]',
      position: 'left',
      order: 1,
      icon: 'FileText',
    },
    {
      id: 'ocr-konfidenz',
      title: 'Konfidenz-Anzeige',
      description:
        'Die farbige Konfidenz-Anzeige zeigt, wie sicher die Erkennung ist: Gruen (>95%) ist zuverlaessig, Gelb (70-95%) sollte geprueft werden, Rot (<70%) muss korrigiert werden.',
      targetSelector: '[data-tour="ocr-confidence"]',
      position: 'left',
      order: 2,
      icon: 'BarChart',
    },
    {
      id: 'ocr-felder-korrigieren',
      title: 'Felder korrigieren',
      description:
        'Klicken Sie auf einen Textabschnitt, um ihn zu bearbeiten. Korrigierte Felder werden automatisch gespeichert.',
      targetSelector: '[data-tour="ocr-correction"]',
      position: 'left',
      order: 3,
      icon: 'Edit',
    },
    {
      id: 'ocr-self-learning',
      title: 'Self-Learning',
      description:
        'Das System lernt aus Ihren Korrekturen. Je mehr Sie korrigieren, desto besser wird die Erkennung fuer aehnliche Dokumente in der Zukunft.',
      position: 'center',
      order: 4,
      icon: 'Brain',
    },
    {
      id: 'ocr-fertig',
      title: 'Fertig!',
      description:
        'Sie wissen jetzt, wie Sie OCR-Ergebnisse pruefen und verbessern. Ihre Korrekturen machen das System intelligenter!',
      position: 'center',
      order: 5,
      icon: 'CheckCircle',
    },
  ],
}
