/**
 * Tour: Suche meistern
 *
 * Fuehrt den Benutzer durch Volltext-, Semantische und Hybrid-Suche.
 */

import type { Tour } from '../types'

export const searchTour: Tour = {
  id: 'schnellsuche',
  name: 'Schnellsuche meistern',
  description: 'Lernen Sie, wie Sie Dokumente blitzschnell finden.',
  category: 'grundlagen',
  estimatedMinutes: 1,
  badge: {
    id: 'suchprofi',
    name: 'Suchprofi',
    description: 'Sie beherrschen die Schnellsuche!',
    icon: 'Search',
  },
  steps: [
    {
      id: 'suche-oeffnen',
      title: 'Suche oeffnen',
      description:
        'Klicken Sie in die Suchleiste oder druecken Sie Strg+K, um die Schnellsuche zu oeffnen.',
      targetSelector: '[data-tour="search-bar"]',
      position: 'bottom',
      order: 1,
      icon: 'Search',
    },
    {
      id: 'suche-modi',
      title: 'Suchmodi',
      description:
        'Drei Suchmodi stehen zur Verfuegung: Volltext durchsucht exakte Woerter, Semantisch versteht Bedeutungen, und Hybrid kombiniert beide fuer beste Ergebnisse.',
      targetSelector: '[data-tour="search-input"]',
      position: 'bottom',
      order: 2,
      icon: 'Type',
    },
    {
      id: 'suche-facetten',
      title: 'Facetten',
      description:
        'Verfeinern Sie Ergebnisse mit den Seitenleisten-Filtern: Datumsbereich, Dokumenttyp, Geschaeftspartner oder OCR-Backend.',
      targetSelector: '[data-tour="search-filters"]',
      position: 'left',
      order: 3,
      icon: 'Filter',
    },
    {
      id: 'suche-gespeichert',
      title: 'Gespeicherte Suchen',
      description:
        'Speichern Sie haeufig genutzte Suchanfragen mit einem Klick auf das Lesezeichen-Symbol. Gespeicherte Suchen erscheinen in der Seitenleiste.',
      targetSelector: '[data-tour="search-save"]',
      position: 'bottom',
      order: 4,
      icon: 'Bookmark',
    },
    {
      id: 'suche-fertig',
      title: 'Fertig!',
      description:
        'Sie beherrschen jetzt die Schnellsuche. Tipp: Nutzen Sie die semantische Suche fuer natuerliche Fragen wie "Rechnungen von Mueller".',
      position: 'center',
      order: 5,
      icon: 'CheckCircle',
    },
  ],
}
