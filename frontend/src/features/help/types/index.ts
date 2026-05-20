/**
 * Help System Types
 */

export enum HelpCategory {
  GETTING_STARTED = 'getting_started',
  DOCUMENTS = 'documents',
  INVOICES = 'invoices',
  WORKFLOWS = 'workflows',
  REPORTS = 'reports',
  ADMIN = 'admin',
}

export const HELP_CATEGORY_LABELS: Record<HelpCategory, string> = {
  [HelpCategory.GETTING_STARTED]: 'Erste Schritte',
  [HelpCategory.DOCUMENTS]: 'Dokumente',
  [HelpCategory.INVOICES]: 'Rechnungen',
  [HelpCategory.WORKFLOWS]: 'Workflows',
  [HelpCategory.REPORTS]: 'Berichte',
  [HelpCategory.ADMIN]: 'Administration',
};

export type TooltipPosition = 'top' | 'bottom' | 'left' | 'right';

export interface HelpArticle {
  id: string;
  title: string;
  content: string;
  category: HelpCategory;
  context: string | null;
  tags: string[];
  video_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface Tooltip {
  id: string;
  feature_id: string;
  title: string;
  content: string;
  position: TooltipPosition;
  created_at: string;
  updated_at: string;
}

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  completed: boolean;
  order: number;
  target_element?: string;
  action?: string;
}

export interface OnboardingStatus {
  steps_completed: number;
  total_steps: number;
  current_step: number | null;
  completed: boolean;
}

export interface VideoTutorial {
  id: string;
  title: string;
  description: string;
  url: string;
  duration: number;
  category: HelpCategory;
  thumbnail_url?: string;
  created_at: string;
  updated_at: string;
}

export interface UserHelpPreferences {
  show_hints: boolean;
  onboarding_completed: boolean;
  dismissed_tooltips: string[];
}

export interface HelpSearchResult {
  article: HelpArticle;
  highlight: string;
  score: number;
}
