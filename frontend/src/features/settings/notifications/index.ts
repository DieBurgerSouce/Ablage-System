/**
 * Notification Preferences Feature - Exports
 */

// Pages
export { NotificationPreferencesPage } from './NotificationPreferencesPage';

// Components
export { ChannelToggle } from './components/ChannelToggle';
export { ChannelPriorityEditor } from './components/ChannelPriorityEditor';
export { NotificationTypeToggle, NotificationTypesList } from './components/NotificationTypeToggle';
export { SeverityMatrix } from './components/SeverityMatrix';
export { QuietHoursForm } from './components/QuietHoursForm';
export { TestNotificationButton } from './components/TestNotificationButton';
export { EscalationChainView } from './components/EscalationChainView';
export { GdprConsentBanner } from './components/GdprConsentBanner';

// Hooks
export * from './hooks';
export { useNotificationPreferencesHook } from './hooks/useNotificationPreferences';

// Types and API
export * from './types';
export * from './api';
