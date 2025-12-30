/**
 * Collaboration Types - Typen fuer Kommentare, Aktivitaeten und Benachrichtigungen
 */

// ==================== Comments ====================

export interface Comment {
  id: string;
  documentId: string;
  userId: string;
  userName: string;
  userAvatar?: string;
  content: string;
  mentions: Mention[];
  parentId?: string; // For replies
  createdAt: string;
  updatedAt?: string;
  isEdited: boolean;
  reactions?: Reaction[];
}

export interface Mention {
  userId: string;
  userName: string;
  startIndex: number;
  endIndex: number;
}

export interface Reaction {
  emoji: string;
  count: number;
  userIds: string[];
}

export interface CreateCommentPayload {
  documentId: string;
  content: string;
  mentions?: { userId: string; userName: string }[];
  parentId?: string;
}

export interface UpdateCommentPayload {
  content: string;
  mentions?: { userId: string; userName: string }[];
}

// ==================== Activity ====================

export type ActivityType =
  | 'document_created'
  | 'document_updated'
  | 'document_viewed'
  | 'document_downloaded'
  | 'comment_added'
  | 'comment_replied'
  | 'status_changed'
  | 'tags_changed'
  | 'metadata_updated'
  | 'document_shared';

export interface Activity {
  id: string;
  documentId: string;
  userId: string;
  userName: string;
  userAvatar?: string;
  type: ActivityType;
  description: string;
  metadata?: Record<string, unknown>;
  createdAt: string;
}

// ==================== Notifications ====================

export type NotificationType =
  | 'mention'
  | 'comment_reply'
  | 'document_shared'
  | 'task_assigned'
  | 'document_approved'
  | 'document_rejected';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  documentId?: string;
  documentName?: string;
  fromUserId: string;
  fromUserName: string;
  fromUserAvatar?: string;
  isRead: boolean;
  createdAt: string;
  actionUrl?: string;
}

// ==================== Users (for mentions) ====================

export interface UserSuggestion {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  department?: string;
}

// ==================== API Responses ====================

export interface CommentsResponse {
  comments: Comment[];
  total: number;
  hasMore: boolean;
}

export interface ActivitiesResponse {
  activities: Activity[];
  total: number;
  hasMore: boolean;
}

export interface NotificationsResponse {
  notifications: Notification[];
  unreadCount: number;
  total: number;
}
