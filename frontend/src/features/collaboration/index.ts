/**
 * Collaboration Feature - Exports
 *
 * Stellt Kommentare, Aktivitaetsverlauf und Benachrichtigungen bereit.
 */

// Types
export type {
  Comment,
  Mention,
  Reaction,
  CreateCommentPayload,
  UpdateCommentPayload,
  Activity,
  ActivityType,
  Notification,
  NotificationType,
  UserSuggestion,
  CommentsResponse,
  ActivitiesResponse,
  NotificationsResponse,
} from './types/collaboration.types';

// Hooks
export {
  useComments,
  useCreateComment,
  useUpdateComment,
  useDeleteComment,
} from './hooks/use-comments';
export { useActivity } from './hooks/use-activity';
export {
  useNotifications,
  useMarkAsRead,
  useMarkAllAsRead,
  useDeleteNotification,
} from './hooks/use-notifications';

// Smart Escalation Hooks (Phase 2.3)
export {
  useAssignmentRecommendation,
  useAssignmentRecommendationQuery,
  useTeamWorkload,
  useUserScores,
  useEscalationFactors,
  useInvalidateSmartEscalationQueries,
  usePrefetchTeamWorkload,
  usePrefetchFactors,
  smartEscalationQueryKeys,
} from './hooks/use-smart-escalation';

// Smart Escalation Types (Phase 2.3)
export type {
  AssignmentRequest,
  UserScoresFilter,
  AssignmentRecommendation,
  TeamWorkload,
  CandidateScore,
  FactorsResponse,
  FactorWeights,
  TeamMemberWorkload,
  FactorInfo,
  AssignmentFactor,
} from './hooks/use-smart-escalation';

// Realtime Hook (Feature 16)
export { useRealtime } from './hooks/use-realtime';
export type { ConnectionStatus, PresenceUser, RealtimeMessage } from './hooks/use-realtime';

// API - Presence & Activity Feed (Feature 16)
export {
  collaborationKeys,
  useDocumentPresence,
  useActivityFeed,
} from './api/collaboration-api';
export type { PresenceUser as ApiPresenceUser, DocumentPresenceResponse } from './api/collaboration-api';

// Components
export { CommentItem } from './components/CommentItem';
export { MentionInput } from './components/MentionInput';
export { CommentsPanel } from './components/CommentsPanel';
export { ActivityStream } from './components/ActivityStream';
export { SmartEscalationPanel } from './components/SmartEscalationPanel';
export type { SmartEscalationPanelProps } from './components/SmartEscalationPanel';

// New Components (Feature 16)
export { CommentThread } from './components/CommentThread';
export { DocumentPresence } from './components/DocumentPresence';
export { ActivityFeed } from './components/ActivityFeed';
export { CollabWebSocketStatusIndicator } from './components/WebSocketStatusIndicator';
