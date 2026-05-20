/**
 * Help System React Query Hooks
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation } from '@tanstack/react-router';
import {
  completeOnboardingStep as apiCompleteStep,
  dismissTooltip as apiDismissTooltip,
  getContextHelp,
  getHelpArticle,
  getHelpArticles,
  getHelpPreferences,
  getOnboardingStatus,
  getTooltip,
  getVideoTutorials,
  resetOnboarding as apiResetOnboarding,
  searchHelp as apiSearchHelp,
  skipOnboarding as apiSkipOnboarding,
  updateHelpPreferences as apiUpdatePreferences,
} from '../api';
import type { HelpCategory, UserHelpPreferences } from '../types';

// Query Keys
const helpKeys = {
  all: ['help'] as const,
  articles: () => [...helpKeys.all, 'articles'] as const,
  articlesByCategory: (category?: HelpCategory) =>
    [...helpKeys.articles(), category] as const,
  article: (id: string) => [...helpKeys.articles(), id] as const,
  contextHelp: (context: string) =>
    [...helpKeys.all, 'context', context] as const,
  search: (query: string) => [...helpKeys.all, 'search', query] as const,
  tooltip: (featureId: string) =>
    [...helpKeys.all, 'tooltip', featureId] as const,
  onboarding: () => [...helpKeys.all, 'onboarding'] as const,
  videos: () => [...helpKeys.all, 'videos'] as const,
  videosByCategory: (category?: HelpCategory) =>
    [...helpKeys.videos(), category] as const,
  preferences: () => [...helpKeys.all, 'preferences'] as const,
};

// Help Articles
export const useHelpArticles = (category?: HelpCategory) => {
  return useQuery({
    queryKey: helpKeys.articlesByCategory(category),
    queryFn: () => getHelpArticles(category),
  });
};

export const useHelpArticle = (id: string) => {
  return useQuery({
    queryKey: helpKeys.article(id),
    queryFn: () => getHelpArticle(id),
    enabled: !!id,
  });
};

export const useContextHelp = (context?: string) => {
  const location = useLocation();
  const currentContext = context || location.pathname;

  return useQuery({
    queryKey: helpKeys.contextHelp(currentContext),
    queryFn: () => getContextHelp(currentContext),
    enabled: !!currentContext,
  });
};

export const useSearchHelp = (query: string) => {
  return useQuery({
    queryKey: helpKeys.search(query),
    queryFn: () => apiSearchHelp(query),
    enabled: query.length >= 3, // Minimum 3 Zeichen für Suche
  });
};

// Tooltips
export const useTooltip = (featureId: string) => {
  return useQuery({
    queryKey: helpKeys.tooltip(featureId),
    queryFn: () => getTooltip(featureId),
    enabled: !!featureId,
  });
};

export const useDismissTooltip = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiDismissTooltip,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: helpKeys.preferences() });
    },
  });
};

// Onboarding
export const useOnboardingStatus = () => {
  return useQuery({
    queryKey: helpKeys.onboarding(),
    queryFn: getOnboardingStatus,
  });
};

export const useCompleteOnboardingStep = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiCompleteStep,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: helpKeys.onboarding() });
    },
  });
};

export const useSkipOnboarding = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiSkipOnboarding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: helpKeys.onboarding() });
      queryClient.invalidateQueries({ queryKey: helpKeys.preferences() });
    },
  });
};

export const useResetOnboarding = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: apiResetOnboarding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: helpKeys.onboarding() });
      queryClient.invalidateQueries({ queryKey: helpKeys.preferences() });
    },
  });
};

// Video Tutorials
export const useVideoTutorials = (category?: HelpCategory) => {
  return useQuery({
    queryKey: helpKeys.videosByCategory(category),
    queryFn: () => getVideoTutorials(category),
  });
};

// User Preferences
export const useHelpPreferences = () => {
  return useQuery({
    queryKey: helpKeys.preferences(),
    queryFn: getHelpPreferences,
  });
};

export const useUpdatePreferences = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (preferences: Partial<UserHelpPreferences>) =>
      apiUpdatePreferences(preferences),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: helpKeys.preferences() });
    },
  });
};
