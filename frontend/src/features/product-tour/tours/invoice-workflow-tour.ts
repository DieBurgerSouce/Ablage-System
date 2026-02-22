/**
 * Tour: Rechnungsworkflow
 *
 * Fuehrt den Benutzer durch den vollautomatischen Rechnungsverarbeitungsprozess.
 */

import type { Tour } from '../types'

export const invoiceWorkflowTour: Tour = {
  id: 'rechnungsworkflow',
  name: 'Rechnungsworkflow nutzen',
  description: 'Erfahren Sie, wie Rechnungen vollautomatisch verarbeitet werden.',
  category: 'fortgeschritten',
  estimatedMinutes: 3,
  badge: {
    id: 'buchhalter',
    name: 'Buchhalter',
    description: 'Sie kennen den automatischen Rechnungsworkflow!',
    icon: 'Receipt',
  },
  steps: [
    {
      id: 'workflow-rechnungsverarbeitung',
      title: 'Rechnungsverarbeitung',
      description:
        'Der Rechnungsworkflow automatisiert den gesamten Prozess: Von der OCR-Erkennung ueber die Lieferant-Zuordnung bis zur Zahlungsfreigabe.',
      targetSelector: '[data-tour="nav-invoice-workflow"]',
      position: 'right',
      order: 1,
      icon: 'Receipt',
    },
    {
      id: 'workflow-extrahierte-daten',
      title: 'Extrahierte Daten',
      description:
        'Die OCR-Erkennung extrahiert automatisch Rechnungsnummer, Datum, Betrag, USt-ID und Positionen. Pruefen Sie die markierten Felder.',
      targetSelector: '[data-tour="workflow-pipeline"]',
      position: 'bottom',
      order: 2,
      icon: 'FileText',
    },
    {
      id: 'workflow-lieferant',
      title: 'Lieferant zuordnen',
      description:
        'Das System erkennt bekannte Lieferanten automatisch per Entity Linking. Bei neuen Lieferanten koennen Sie die Zuordnung manuell vornehmen.',
      targetSelector: '[data-tour="workflow-approval"]',
      position: 'bottom',
      order: 3,
      icon: 'Link',
    },
    {
      id: 'workflow-freigabe',
      title: 'Freigabe-Workflow',
      description:
        'Bekannte Lieferanten mit gutem Track-Record werden automatisch genehmigt. Bei hohen Betraegen oder neuen Lieferanten erfolgt eine manuelle Pruefung.',
      targetSelector: '[data-tour="workflow-review"]',
      position: 'bottom',
      order: 4,
      icon: 'CheckCircle',
    },
    {
      id: 'workflow-datev',
      title: 'DATEV-Export',
      description:
        'Genehmigte Rechnungen koennen direkt im DATEV-Format exportiert werden. Der Export umfasst Buchungssaetze, Belegbilder und alle Metadaten.',
      targetSelector: '[data-tour="workflow-stats"]',
      position: 'top',
      order: 5,
      icon: 'Download',
    },
  ],
}
