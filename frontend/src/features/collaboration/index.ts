/**
 * Collaboration Feature - Exports
 *
 * Stellt Kommentare, Aktivitätsverlauf und Benachrichtigungen bereit.
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

// User Search Hook (Feature 8)
export { useUserSearch } from './hooks/use-user-search';

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

// Document Tasks (Feature 7 - Aufgaben-Zuweisung)
export { DocumentTasksPanel } from './components/DocumentTasksPanel';
export { CreateTaskDialog } from './components/CreateTaskDialog';
export { TaskCard } from './components/TaskCard';
export {
  useDocumentTasks,
  useMyTasks,
  useOverdueTasks,
  useTaskStatistics,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
  useStartTask,
  useCompleteTask,
  useCancelTask,
  useBlockTask,
  useUnblockTask,
  useAssignTask,
  useUnassignTask,
  documentTaskKeys,
} from './hooks/use-document-tasks';
export type {
  DocumentTask,
  TaskCreate,
  TaskUpdate,
  TaskStatus,
  TaskPriority,
  TaskListResponse,
  TaskStatistics,
} from './api/document-tasks-api';

// Document Lock (Feature 17 - Collaboration Locks)
export {
  useDocumentLock,
  useDocumentLockStatus,
  useLockDocument,
  useUnlockDocument,
  lockKeys,
} from './hooks/useDocumentLock';
export type { DocumentLock, DocumentLockResponse } from './hooks/useDocumentLock';

// Presence (Feature 17 - Real-time Presence)
export { usePresence, presenceKeys } from './hooks/usePresence';
export type { PresenceUser as PresenceUserType, PresenceResponse } from './hooks/usePresence';

// Activity Feed (Feature 17 - Activity Tracking)
export {
  useDocumentActivity,
  useUserActivityFeed,
  useDocumentActivityRealtime,
  activityKeys,
} from './hooks/useActivityFeed';
export type { ActivityFeedParams } from './hooks/useActivityFeed';

// Mentions (Feature 17 - User Mentions)
export {
  useMentions,
  useUnreadMentionsCount,
  useCreateMentions,
  useMarkMentionAsRead,
  mentionsKeys,
} from './hooks/useMentions';
export type { MentionItem, MentionsResponse, CreateMentionPayload } from './hooks/useMentions';

// New Components (Feature 17)
export { PresenceIndicator } from './components/PresenceIndicator';
export { DocumentLockBanner } from './components/DocumentLockBanner';
export { ActivityTimeline } from './components/ActivityTimeline';
export { MentionsBadge } from './components/MentionsBadge';
