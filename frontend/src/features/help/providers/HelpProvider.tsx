/**
 * Help Provider - Context Provider für globale Help-State
 */

import { createContext, useContext, useEffect, useState } from 'react';
import { useLocation } from '@tanstack/react-router';
import { useContextHelp, useHelpPreferences, useOnboardingStatus } from '../hooks/useHelp';
import type { HelpArticle } from '../types';

interface HelpContextType {
  currentContext: string;
  contextualArticles: HelpArticle[];
  isOnboardingActive: boolean;
  setOnboardingActive: (active: boolean) => void;
  showHints: boolean;
}

const HelpContext = createContext<HelpContextType | undefined>(undefined);

export function HelpProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [isOnboardingActive, setOnboardingActive] = useState(false);

  // Aktueller Kontext basierend auf Route
  const currentContext = location.pathname;

  // Kontextuelle Hilfe-Artikel für aktuelle Seite
  const { data: contextualArticles = [] } = useContextHelp(currentContext);

  // User-Präferenzen
  const { data: preferences } = useHelpPreferences();

  // Onboarding-Status
  const { data: onboardingStatus } = useOnboardingStatus();

  // Auto-Start Onboarding wenn noch nicht abgeschlossen
  useEffect(() => {
    if (
      onboardingStatus &&
      !onboardingStatus.completed &&
      preferences?.onboarding_completed === false
    ) {
      setOnboardingActive(true);
    }
  }, [onboardingStatus, preferences]);

  const value: HelpContextType = {
    currentContext,
    contextualArticles,
    isOnboardingActive,
    setOnboardingActive,
    showHints: preferences?.show_hints ?? true,
  };

  return <HelpContext.Provider value={value}>{children}</HelpContext.Provider>;
}

export function useHelpContext() {
  const context = useContext(HelpContext);
  if (context === undefined) {
    throw new Error('useHelpContext must be used within a HelpProvider');
  }
  return context;
}
