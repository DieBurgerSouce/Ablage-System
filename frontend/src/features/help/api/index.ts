/**
 * Help System API Client
 */

import { apiClient } from '@/lib/api-client';
import type {
  HelpArticle,
  HelpCategory,
  HelpSearchResult,
  OnboardingStatus,
  Tooltip,
  UserHelpPreferences,
  VideoTutorial,
} from '../types';

const BASE_URL = '/api/v1/help';

// Help Articles
export const getHelpArticles = async (
  category?: HelpCategory
): Promise<HelpArticle[]> => {
  const params = category ? { category } : {};
  const response = await apiClient.get<HelpArticle[]>(`${BASE_URL}/articles`, {
    params,
  });
  return response.data;
};

export const getHelpArticle = async (id: string): Promise<HelpArticle> => {
  const response = await apiClient.get<HelpArticle>(
    `${BASE_URL}/articles/${id}`
  );
  return response.data;
};

export const getContextHelp = async (
  context: string
): Promise<HelpArticle[]> => {
  const response = await apiClient.get<HelpArticle[]>(
    `${BASE_URL}/articles/context/${context}`
  );
  return response.data;
};

export const searchHelp = async (query: string): Promise<HelpSearchResult[]> => {
  const response = await apiClient.get<HelpSearchResult[]>(
    `${BASE_URL}/search`,
    {
      params: { q: query },
    }
  );
  return response.data;
};

// Tooltips
export const getTooltip = async (featureId: string): Promise<Tooltip | null> => {
  try {
    const response = await apiClient.get<Tooltip>(
      `${BASE_URL}/tooltips/${featureId}`
    );
    return response.data;
  } catch (error) {
    // 404 ist OK - nicht jedes Feature hat ein Tooltip
    return null;
  }
};

// Onboarding
export const getOnboardingStatus = async (): Promise<OnboardingStatus> => {
  const response = await apiClient.get<OnboardingStatus>(
    `${BASE_URL}/onboarding/status`
  );
  return response.data;
};

export const completeOnboardingStep = async (
  stepId: string
): Promise<OnboardingStatus> => {
  const response = await apiClient.post<OnboardingStatus>(
    `${BASE_URL}/onboarding/steps/${stepId}/complete`
  );
  return response.data;
};

export const skipOnboarding = async (): Promise<void> => {
  await apiClient.post(`${BASE_URL}/onboarding/skip`);
};

export const resetOnboarding = async (): Promise<OnboardingStatus> => {
  const response = await apiClient.post<OnboardingStatus>(
    `${BASE_URL}/onboarding/reset`
  );
  return response.data;
};

// Video Tutorials
export const getVideoTutorials = async (
  category?: HelpCategory
): Promise<VideoTutorial[]> => {
  const params = category ? { category } : {};
  const response = await apiClient.get<VideoTutorial[]>(
    `${BASE_URL}/videos`,
    {
      params,
    }
  );
  return response.data;
};

// User Preferences
export const getHelpPreferences = async (): Promise<UserHelpPreferences> => {
  const response = await apiClient.get<UserHelpPreferences>(
    `${BASE_URL}/preferences`
  );
  return response.data;
};

export const updateHelpPreferences = async (
  preferences: Partial<UserHelpPreferences>
): Promise<UserHelpPreferences> => {
  const response = await apiClient.patch<UserHelpPreferences>(
    `${BASE_URL}/preferences`,
    preferences
  );
  return response.data;
};

export const dismissTooltip = async (tooltipId: string): Promise<void> => {
  await apiClient.post(`${BASE_URL}/tooltips/${tooltipId}/dismiss`);
};
