/**
 * Slack Integration Types.
 *
 * TypeScript-Typen für die Slack-Integration.
 */

// =============================================================================
// CHANNEL TYPES
// =============================================================================

export type SlackChannelType = 'public' | 'private' | 'dm';

export type SlackMessagePriority = 'low' | 'normal' | 'high' | 'urgent';

export type SlackMessageStatus = 'pending' | 'sent' | 'failed' | 'rate_limited';

export interface SlackChannel {
    id: string;
    channel_id: string;
    channel_name: string;
    channel_type: SlackChannelType;
    company_id: string | null;
    notification_types: string[];
    min_priority: SlackMessagePriority;
    is_default: boolean;
    is_active: boolean;
    include_context: boolean;
    mention_users: string[];
    custom_icon: string | null;
    message_count: number;
    last_message_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface SlackChannelCreate {
    channel_id: string;
    channel_name: string;
    channel_type?: SlackChannelType;
    company_id?: string | null;
    notification_types?: string[];
    min_priority?: SlackMessagePriority;
    is_default?: boolean;
    include_context?: boolean;
    mention_users?: string[];
    custom_icon?: string | null;
}

export interface SlackChannelUpdate {
    channel_name?: string;
    notification_types?: string[];
    min_priority?: SlackMessagePriority;
    is_default?: boolean;
    is_active?: boolean;
    include_context?: boolean;
    mention_users?: string[];
    custom_icon?: string | null;
}

export interface SlackChannelListResponse {
    items: SlackChannel[];
    total: number;
}

// =============================================================================
// MESSAGE TYPES
// =============================================================================

export interface SlackMessageLog {
    id: string;
    slack_channel_id: string;
    message_ts: string | null;
    notification_type: string;
    title: string;
    message_preview: string | null;
    priority: SlackMessagePriority;
    status: SlackMessageStatus;
    error_message: string | null;
    retry_count: number;
    reference_type: string | null;
    reference_id: string | null;
    created_at: string;
    sent_at: string | null;
}

export interface SlackMessageListResponse {
    items: SlackMessageLog[];
    total: number;
}

// =============================================================================
// USER MAPPING TYPES
// =============================================================================

export interface SlackUserMapping {
    id: string;
    user_id: string;
    slack_user_id: string;
    slack_username: string | null;
    dm_enabled: boolean;
    dm_notification_types: string[];
    mention_on_approval: boolean;
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
    is_verified: boolean;
    verified_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface SlackUserMappingCreate {
    slack_user_id: string;
    slack_username?: string | null;
    dm_enabled?: boolean;
    dm_notification_types?: string[];
    mention_on_approval?: boolean;
    quiet_hours_start?: string | null;
    quiet_hours_end?: string | null;
}

// =============================================================================
// STATUS & STATISTICS TYPES
// =============================================================================

export interface SlackConnectionStatus {
    enabled: boolean;
    webhook_configured: boolean;
    bot_token_configured: boolean;
    default_channel: string;
    webhook_test: string | null;
    bot_test: {
        status: string;
        team?: string;
        user?: string;
        error?: string;
    } | null;
}

export interface SlackStatistics {
    total_channels: number;
    active_channels: number;
    total_messages_sent: number;
    messages_last_24h: number;
    messages_last_7d: number;
    failed_messages: number;
    user_mappings: number;
}

// =============================================================================
// TEST MESSAGE TYPES
// =============================================================================

export interface SlackTestMessageRequest {
    channel_id?: string | null;
    message?: string;
    notification_type?: string;
    priority?: SlackMessagePriority;
}

export interface SlackTestMessageResponse {
    success: boolean;
    message_ts?: string | null;
    error?: string | null;
}

// =============================================================================
// NOTIFICATION TYPE INFO
// =============================================================================

export interface SlackNotificationTypeInfo {
    type: string;
    name: string;
    description: string;
    icon: string;
}
