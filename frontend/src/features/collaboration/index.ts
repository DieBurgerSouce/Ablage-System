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

// Components
export { CommentItem } from './components/CommentItem';
export { MentionInput } from './components/MentionInput';
export { CommentsPanel } from './components/CommentsPanel';
export { ActivityStream } from './components/ActivityStream';
