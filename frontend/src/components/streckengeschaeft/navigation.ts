/**
 * Streckengeschäft Navigation Configuration
 * 
 * Sidebar menu items for drop shipment classification module.
 * Import into main navigation configuration.
 */

import {
  Truck,
  LayoutDashboard,
  FileText,
  Globe,
  Settings,
  Building2,
} from 'lucide-react';

export const streckengeschaeftNavigation = {
  title: 'Streckengeschäft',
  icon: Truck,
  basePath: '/streckengeschaeft',
  items: [
    {
      title: 'Übersicht',
      href: '/streckengeschaeft',
      icon: LayoutDashboard,
      description: 'Dashboard und Klassifikationen',
    },
    {
      title: 'Zusammenfassende Meldung',
      href: '/streckengeschaeft/zm',
      icon: Globe,
      description: 'ZM-Übersicht und Export',
      badge: 'ZM',
    },
    {
      title: 'Belegprüfung',
      href: '/streckengeschaeft/proofs',
      icon: FileText,
      description: 'Gelangensbestätigungen prüfen',
    },
    {
      title: 'DATEV-Integration',
      href: '/streckengeschaeft/datev',
      icon: Building2,
      description: 'Kontenzuordnung und Export',
    },
    {
      title: 'Einstellungen',
      href: '/streckengeschaeft/settings',
      icon: Settings,
      description: 'Indikatoren und Schwellwerte',
    },
  ],
};

/**
 * Quick actions for command palette / spotlight search
 */
export const streckengeschaeftQuickActions = [
  {
    id: 'strecken-classify',
    title: 'Dokument klassifizieren',
    description: 'Streckengeschäft-Erkennung starten',
    keywords: ['strecke', 'dreieck', 'klassifizieren', 'drop ship'],
    action: '/streckengeschaeft?action=classify',
  },
  {
    id: 'strecken-zm',
    title: 'ZM-Meldung erstellen',
    description: 'Zusammenfassende Meldung vorbereiten',
    keywords: ['zm', 'meldung', 'elster', 'innergemeinschaftlich'],
    action: '/streckengeschaeft/zm',
  },
  {
    id: 'strecken-datev',
    title: 'DATEV Export',
    description: 'Streckengeschäfte nach DATEV exportieren',
    keywords: ['datev', 'export', 'buchhaltung'],
    action: '/streckengeschaeft/datev',
  },
];

export default streckengeschaeftNavigation;
