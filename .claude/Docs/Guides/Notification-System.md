# Notification System Guide

**Comprehensive Multi-Channel Notification System for Ablage System**

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Notification Channels](#notification-channels)
4. [Email Notifications](#email-notifications)
5. [Webhooks](#webhooks)
6. [Push Notifications](#push-notifications)
7. [In-App Notifications](#in-app-notifications)
8. [Template System](#template-system)
9. [User Preferences](#user-preferences)
10. [Delivery Management](#delivery-management)
11. [Rate Limiting & Throttling](#rate-limiting--throttling)
12. [Monitoring & Analytics](#monitoring--analytics)

---

## Overview

### Purpose

The notification system provides reliable, multi-channel communication with users for document processing events, system alerts, and user actions.

### Key Features

- **Multi-Channel**: Email, webhooks, push notifications, in-app
- **Template-Based**: Customizable templates with i18n support
- **Reliable Delivery**: Retry logic, dead letter queues, delivery tracking
- **User Preferences**: Per-channel, per-event type preferences
- **Rate Limiting**: Prevent notification spam
- **Analytics**: Delivery metrics, engagement tracking

### Notification Types

| Type | Channels | Priority | Example |
|------|----------|----------|---------|
| **Transactional** | Email, In-App | High | Document processed, upload complete |
| **System Alerts** | Email, Webhook, SMS | Critical | System down, security alert |
| **Marketing** | Email | Low | Feature announcements, newsletters |
| **Reminders** | Email, Push | Medium | Pending documents, expiring items |

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                     │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   FastAPI    │  │    Celery    │  │   Frontend   │  │
│  │  Endpoints   │  │    Tasks     │  │   (React)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
└─────────┼─────────────────┼──────────────────┼──────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│               NOTIFICATION ORCHESTRATOR                  │
├─────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────┐     │
│  │  Notification Service (notification_service.py)│     │
│  │  - Event routing                               │     │
│  │  - Channel selection                           │     │
│  │  - Template rendering                          │     │
│  │  - User preference filtering                   │     │
│  └────────┬───────────────────────────────────────┘     │
│           │                                             │
└───────────┼─────────────────────────────────────────────┘
            │
            ├──────────┬──────────┬──────────┬──────────┐
            ▼          ▼          ▼          ▼          ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│    Email     │ │ Webhook  │ │   Push   │ │  In-App  │
│   Channel    │ │ Channel  │ │ Channel  │ │ Channel  │
├──────────────┤ ├──────────┤ ├──────────┤ ├──────────┤
│   SMTP/      │ │   HTTP   │ │  FCM/    │ │ WebSocket│
│   SendGrid   │ │  Client  │ │  APNS    │ │  + DB    │
└──────┬───────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       │              │            │            │
       ▼              ▼            ▼            ▼
┌─────────────────────────────────────────────────────────┐
│                  DELIVERY TRACKING                       │
├─────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ PostgreSQL │  │   Redis    │  │   Celery   │        │
│  │(Delivery   │  │  (Queue)   │  │(Retry Jobs)│        │
│  │  Logs)     │  │            │  │            │        │
│  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
```

### Database Schema

```sql
-- Notification events
CREATE TABLE notification_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,  -- 'document_processed', 'upload_failed', etc.
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,  -- Event-specific data
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',  -- 'low', 'medium', 'high', 'critical'
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP
);

CREATE INDEX idx_notification_events_user_id ON notification_events(user_id);
CREATE INDEX idx_notification_events_event_type ON notification_events(event_type);
CREATE INDEX idx_notification_events_created_at ON notification_events(created_at);


-- Notification deliveries
CREATE TABLE notification_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES notification_events(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL,  -- 'email', 'webhook', 'push', 'in_app'
    recipient VARCHAR(500) NOT NULL,  -- Email address, webhook URL, device token, user_id
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- 'pending', 'sent', 'delivered', 'failed', 'bounced'
    template_id VARCHAR(100),
    rendered_content JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    failed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notification_deliveries_event_id ON notification_deliveries(event_id);
CREATE INDEX idx_notification_deliveries_status ON notification_deliveries(status);
CREATE INDEX idx_notification_deliveries_channel ON notification_deliveries(channel);
CREATE INDEX idx_notification_deliveries_created_at ON notification_deliveries(created_at);


-- User notification preferences
CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    channel VARCHAR(50) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    quiet_hours_start TIME,  -- e.g., '22:00:00'
    quiet_hours_end TIME,    -- e.g., '08:00:00'
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, event_type, channel)
);

CREATE INDEX idx_notification_preferences_user_id ON notification_preferences(user_id);


-- Webhook subscriptions
CREATE TABLE webhook_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url VARCHAR(500) NOT NULL,
    secret VARCHAR(100) NOT NULL,  -- For HMAC signature
    event_types TEXT[] NOT NULL,  -- Array of subscribed event types
    is_active BOOLEAN NOT NULL DEFAULT true,
    headers JSONB,  -- Custom headers
    timeout_seconds INTEGER DEFAULT 30,
    retry_policy JSONB,  -- Custom retry configuration
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_subscriptions_user_id ON webhook_subscriptions(user_id);
CREATE INDEX idx_webhook_subscriptions_is_active ON webhook_subscriptions(is_active);


-- In-app notifications
CREATE TABLE in_app_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'info', 'success', 'warning', 'error'
    action_url VARCHAR(500),
    action_label VARCHAR(100),
    is_read BOOLEAN NOT NULL DEFAULT false,
    read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP
);

CREATE INDEX idx_in_app_notifications_user_id ON in_app_notifications(user_id);
CREATE INDEX idx_in_app_notifications_is_read ON in_app_notifications(is_read);
CREATE INDEX idx_in_app_notifications_created_at ON in_app_notifications(created_at);


-- Push notification devices
CREATE TABLE push_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,  -- 'ios', 'android', 'web'
    device_token VARCHAR(500) NOT NULL UNIQUE,
    device_name VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_push_devices_user_id ON push_devices(user_id);
CREATE INDEX idx_push_devices_is_active ON push_devices(is_active);
```

---

## Notification Channels

### Channel Selection Logic

```python
# backend/services/notification_service.py
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from backend.models import User, NotificationEvent, NotificationPreference
from backend.services.email_service import EmailService
from backend.services.webhook_service import WebhookService
from backend.services.push_service import PushService
from backend.services.in_app_service import InAppService

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.email_service = EmailService()
        self.webhook_service = WebhookService()
        self.push_service = PushService()
        self.in_app_service = InAppService()

    def send_notification(
        self,
        user: User,
        event_type: str,
        payload: Dict[str, Any],
        priority: str = "medium"
    ):
        """
        Send notification through all enabled channels based on user preferences.

        Args:
            user: Target user
            event_type: Type of notification event
            payload: Event-specific data
            priority: Notification priority level
        """
        logger.info(
            f"Sending notification to user {user.id}",
            extra={"event_type": event_type, "priority": priority}
        )

        # Create notification event
        event = NotificationEvent(
            event_type=event_type,
            user_id=user.id,
            payload=payload,
            priority=priority
        )
        db.add(event)
        db.commit()

        # Get user preferences
        preferences = self._get_user_preferences(user.id, event_type)

        # Determine which channels to use
        channels = self._select_channels(event_type, priority, preferences)

        # Send through each channel
        for channel in channels:
            try:
                if channel == "email":
                    self.email_service.send(user, event_type, payload)

                elif channel == "webhook":
                    self.webhook_service.send(user, event_type, payload)

                elif channel == "push":
                    self.push_service.send(user, event_type, payload)

                elif channel == "in_app":
                    self.in_app_service.send(user, event_type, payload)

                logger.info(f"Notification sent via {channel}")

            except Exception as e:
                logger.error(
                    f"Failed to send notification via {channel}: {e}",
                    exc_info=True
                )

    def _get_user_preferences(
        self,
        user_id: str,
        event_type: str
    ) -> List[NotificationPreference]:
        """Get user's notification preferences for event type."""
        return db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_type == event_type
        ).all()

    def _select_channels(
        self,
        event_type: str,
        priority: str,
        preferences: List[NotificationPreference]
    ) -> List[str]:
        """
        Select appropriate channels based on event type, priority, and preferences.
        """
        # Default channels by priority
        default_channels = {
            "critical": ["email", "push", "webhook", "in_app"],
            "high": ["email", "in_app"],
            "medium": ["in_app"],
            "low": ["in_app"]
        }

        # Start with defaults
        channels = set(default_channels.get(priority, ["in_app"]))

        # Apply user preferences
        for pref in preferences:
            if pref.enabled:
                channels.add(pref.channel)
            else:
                channels.discard(pref.channel)

        # Check quiet hours for non-critical notifications
        if priority != "critical":
            channels = self._filter_quiet_hours(channels, preferences)

        return list(channels)

    def _filter_quiet_hours(
        self,
        channels: set,
        preferences: List[NotificationPreference]
    ) -> set:
        """Remove channels that are in quiet hours."""
        now = datetime.now()

        for pref in preferences:
            if pref.quiet_hours_start and pref.quiet_hours_end:
                # Check if current time is in quiet hours
                if self._is_quiet_hours(
                    now,
                    pref.quiet_hours_start,
                    pref.quiet_hours_end
                ):
                    channels.discard(pref.channel)

        return channels

    def _is_quiet_hours(
        self,
        current_time: datetime,
        start_time: datetime.time,
        end_time: datetime.time
    ) -> bool:
        """Check if current time is within quiet hours."""
        current = current_time.time()

        if start_time < end_time:
            # Same day (e.g., 09:00 - 17:00)
            return start_time <= current <= end_time
        else:
            # Across midnight (e.g., 22:00 - 08:00)
            return current >= start_time or current <= end_time
```

---

## Email Notifications

### Email Service Implementation

```python
# backend/services/email_service.py
from typing import Dict, Any, Optional, List
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import logging

from jinja2 import Environment, FileSystemLoader
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

from backend.core.config import settings
from backend.models import User, NotificationDelivery

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        # Initialize template engine
        self.template_env = Environment(
            loader=FileSystemLoader('backend/templates/emails')
        )

        # Initialize SendGrid client (if configured)
        if settings.SENDGRID_API_KEY:
            self.sendgrid = SendGridAPIClient(settings.SENDGRID_API_KEY)
            self.use_sendgrid = True
        else:
            self.use_sendgrid = False

    def send(
        self,
        user: User,
        event_type: str,
        payload: Dict[str, Any]
    ) -> NotificationDelivery:
        """
        Send email notification to user.

        Args:
            user: Target user
            event_type: Type of notification
            payload: Notification data

        Returns:
            NotificationDelivery record
        """
        logger.info(f"Sending email to {user.email} for event {event_type}")

        # Render email template
        subject, html_content, text_content = self._render_template(
            event_type,
            payload,
            user
        )

        # Create delivery record
        delivery = NotificationDelivery(
            event_id=payload.get('event_id'),
            channel='email',
            recipient=user.email,
            template_id=event_type,
            status='pending'
        )
        db.add(delivery)
        db.commit()

        try:
            if self.use_sendgrid:
                self._send_via_sendgrid(
                    to_email=user.email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )
            else:
                self._send_via_smtp(
                    to_email=user.email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content
                )

            # Update delivery status
            delivery.status = 'sent'
            delivery.sent_at = datetime.utcnow()
            db.commit()

            logger.info(f"Email sent successfully to {user.email}")

        except Exception as e:
            logger.error(f"Failed to send email: {e}", exc_info=True)

            delivery.status = 'failed'
            delivery.error_message = str(e)
            delivery.failed_at = datetime.utcnow()
            db.commit()

            # Schedule retry if retries remaining
            if delivery.retry_count < delivery.max_retries:
                self._schedule_retry(delivery)

        return delivery

    def _render_template(
        self,
        event_type: str,
        payload: Dict[str, Any],
        user: User
    ) -> tuple[str, str, str]:
        """
        Render email template.

        Returns:
            Tuple of (subject, html_content, text_content)
        """
        # Load template
        template = self.template_env.get_template(f'{event_type}.html')

        # Prepare context
        context = {
            'user': user,
            'payload': payload,
            'app_name': 'Ablage System',
            'app_url': settings.APP_URL,
            'year': datetime.now().year
        }

        # Render HTML
        html_content = template.render(**context)

        # Render text version
        text_template = self.template_env.get_template(f'{event_type}.txt')
        text_content = text_template.render(**context)

        # Get subject
        subject = self._get_subject(event_type, payload)

        return subject, html_content, text_content

    def _get_subject(self, event_type: str, payload: Dict[str, Any]) -> str:
        """Get email subject based on event type."""
        subjects = {
            'document_processed': 'Document Processing Complete',
            'document_failed': 'Document Processing Failed',
            'upload_complete': 'Upload Successful',
            'user_registered': 'Welcome to Ablage System',
            'password_reset': 'Password Reset Request',
            'account_activated': 'Account Activated',
            'security_alert': 'Security Alert - Unusual Activity Detected'
        }

        return subjects.get(event_type, 'Notification from Ablage System')

    def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str
    ):
        """Send email via SendGrid."""
        message = Mail(
            from_email=Email(settings.FROM_EMAIL, 'Ablage System'),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=Content("text/plain", text_content),
            html_content=Content("text/html", html_content)
        )

        response = self.sendgrid.send(message)

        if response.status_code not in [200, 201, 202]:
            raise Exception(f"SendGrid error: {response.body}")

    def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str
    ):
        """Send email via SMTP."""
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = to_email

        # Attach text and HTML versions
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')

        msg.attach(part1)
        msg.attach(part2)

        # Send via SMTP
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()

            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

            server.send_message(msg)

    def _schedule_retry(self, delivery: NotificationDelivery):
        """Schedule retry for failed delivery."""
        from backend.tasks.notifications import retry_email_delivery

        # Exponential backoff: 1min, 5min, 15min
        delay = 60 * (5 ** delivery.retry_count)

        retry_email_delivery.apply_async(
            args=[delivery.id],
            countdown=delay
        )

        logger.info(
            f"Scheduled email retry in {delay}s",
            extra={'delivery_id': delivery.id}
        )
```

### Email Templates

```html
<!-- backend/templates/emails/document_processed.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Processed</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            background-color: #4F46E5;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 8px 8px 0 0;
        }
        .content {
            background-color: #f9fafb;
            padding: 30px;
            border-radius: 0 0 8px 8px;
        }
        .button {
            display: inline-block;
            background-color: #4F46E5;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            margin: 20px 0;
        }
        .footer {
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 30px;
        }
        .stats {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
        }
        .stat-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }
        .stat-item:last-child {
            border-bottom: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ app_name }}</h1>
        <p>Document Processing Complete</p>
    </div>

    <div class="content">
        <h2>Hello {{ user.username }},</h2>

        <p>Good news! Your document has been successfully processed.</p>

        <div class="stats">
            <div class="stat-item">
                <span><strong>Document:</strong></span>
                <span>{{ payload.document.filename }}</span>
            </div>
            <div class="stat-item">
                <span><strong>Pages:</strong></span>
                <span>{{ payload.document.page_count }}</span>
            </div>
            <div class="stat-item">
                <span><strong>Processing Time:</strong></span>
                <span>{{ payload.processing_time }}s</span>
            </div>
            <div class="stat-item">
                <span><strong>Confidence Score:</strong></span>
                <span>{{ (payload.confidence * 100)|round(2) }}%</span>
            </div>
        </div>

        <p>You can now view and download your processed document.</p>

        <a href="{{ app_url }}/documents/{{ payload.document.id }}" class="button">
            View Document
        </a>

        <p>If you have any questions, please contact our support team.</p>

        <p>Best regards,<br>The {{ app_name }} Team</p>
    </div>

    <div class="footer">
        <p>&copy; {{ year }} {{ app_name }}. All rights reserved.</p>
        <p>
            <a href="{{ app_url }}/settings/notifications">Notification Settings</a> |
            <a href="{{ app_url }}/help">Help Center</a>
        </p>
    </div>
</body>
</html>
```

```text
<!-- backend/templates/emails/document_processed.txt -->
{{ app_name }} - Document Processing Complete

Hello {{ user.username }},

Good news! Your document has been successfully processed.

Document Details:
- Filename: {{ payload.document.filename }}
- Pages: {{ payload.document.page_count }}
- Processing Time: {{ payload.processing_time }}s
- Confidence Score: {{ (payload.confidence * 100)|round(2) }}%

View your document: {{ app_url }}/documents/{{ payload.document.id }}

If you have any questions, please contact our support team.

Best regards,
The {{ app_name }} Team

---
{{ app_name }} | {{ year }}
Manage notifications: {{ app_url }}/settings/notifications
```

---

## Webhooks

### Webhook Service Implementation

```python
# backend/services/webhook_service.py
import hmac
import hashlib
import json
import requests
from typing import Dict, Any, Optional
import logging

from backend.models import User, WebhookSubscription, NotificationDelivery

logger = logging.getLogger(__name__)


class WebhookService:
    def send(
        self,
        user: User,
        event_type: str,
        payload: Dict[str, Any]
    ) -> List[NotificationDelivery]:
        """
        Send webhook notifications to all user's active subscriptions.

        Args:
            user: Target user
            event_type: Type of event
            payload: Event data

        Returns:
            List of delivery records
        """
        logger.info(
            f"Sending webhooks to user {user.id}",
            extra={'event_type': event_type}
        )

        # Get active subscriptions for this event type
        subscriptions = db.query(WebhookSubscription).filter(
            WebhookSubscription.user_id == user.id,
            WebhookSubscription.is_active == True,
            WebhookSubscription.event_types.contains([event_type])
        ).all()

        deliveries = []

        for subscription in subscriptions:
            delivery = self._send_webhook(
                subscription=subscription,
                event_type=event_type,
                payload=payload
            )
            deliveries.append(delivery)

        return deliveries

    def _send_webhook(
        self,
        subscription: WebhookSubscription,
        event_type: str,
        payload: Dict[str, Any]
    ) -> NotificationDelivery:
        """Send single webhook delivery."""
        # Prepare webhook payload
        webhook_payload = {
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            'data': payload
        }

        # Create delivery record
        delivery = NotificationDelivery(
            event_id=payload.get('event_id'),
            channel='webhook',
            recipient=subscription.url,
            status='pending',
            rendered_content=webhook_payload
        )
        db.add(delivery)
        db.commit()

        try:
            # Generate HMAC signature
            signature = self._generate_signature(
                payload=webhook_payload,
                secret=subscription.secret
            )

            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Signature': signature,
                'X-Event-Type': event_type,
                'User-Agent': 'Ablage-Webhooks/1.0'
            }

            # Add custom headers
            if subscription.headers:
                headers.update(subscription.headers)

            # Send webhook
            response = requests.post(
                url=subscription.url,
                json=webhook_payload,
                headers=headers,
                timeout=subscription.timeout_seconds
            )

            # Check response
            if response.status_code in [200, 201, 202, 204]:
                delivery.status = 'delivered'
                delivery.delivered_at = datetime.utcnow()

                subscription.last_success_at = datetime.utcnow()
                subscription.failure_count = 0

                logger.info(
                    f"Webhook delivered successfully",
                    extra={'url': subscription.url}
                )

            else:
                raise Exception(
                    f"Webhook returned status {response.status_code}: "
                    f"{response.text}"
                )

        except Exception as e:
            logger.error(
                f"Webhook delivery failed: {e}",
                exc_info=True,
                extra={'url': subscription.url}
            )

            delivery.status = 'failed'
            delivery.error_message = str(e)
            delivery.failed_at = datetime.utcnow()

            subscription.last_failure_at = datetime.utcnow()
            subscription.failure_count += 1

            # Disable subscription after too many failures
            if subscription.failure_count >= 10:
                subscription.is_active = False
                logger.warning(
                    f"Webhook subscription disabled after 10 failures",
                    extra={'url': subscription.url}
                )

            # Schedule retry
            if delivery.retry_count < delivery.max_retries:
                self._schedule_retry(delivery, subscription)

        db.commit()
        return delivery

    def _generate_signature(
        self,
        payload: Dict[str, Any],
        secret: str
    ) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload.

        Args:
            payload: Webhook payload
            secret: Webhook secret

        Returns:
            Hex-encoded signature
        """
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            key=secret.encode('utf-8'),
            msg=payload_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()

        return signature

    def _schedule_retry(
        self,
        delivery: NotificationDelivery,
        subscription: WebhookSubscription
    ):
        """Schedule webhook retry."""
        from backend.tasks.notifications import retry_webhook_delivery

        # Get retry configuration
        retry_policy = subscription.retry_policy or {}
        delay = retry_policy.get('delay', 60 * (2 ** delivery.retry_count))

        retry_webhook_delivery.apply_async(
            args=[delivery.id],
            countdown=delay
        )

        logger.info(
            f"Scheduled webhook retry in {delay}s",
            extra={'delivery_id': delivery.id}
        )
```

### Webhook API Endpoints

```python
# backend/api/v1/webhooks.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import secrets

from backend.models import WebhookSubscription
from backend.schemas.webhook import (
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse
)
from backend.api.dependencies import get_db, get_current_user

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/", response_model=WebhookResponse)
async def create_webhook(
    webhook_data: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new webhook subscription.

    The webhook secret will be auto-generated and returned only once.
    Store it securely to verify webhook signatures.
    """
    # Generate secure secret
    secret = secrets.token_urlsafe(32)

    webhook = WebhookSubscription(
        user_id=current_user.id,
        url=webhook_data.url,
        secret=secret,
        event_types=webhook_data.event_types,
        headers=webhook_data.headers,
        timeout_seconds=webhook_data.timeout_seconds or 30
    )

    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    return {
        **webhook.__dict__,
        'secret': secret  # Only returned on creation
    }


@router.get("/", response_model=List[WebhookResponse])
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all webhook subscriptions for current user."""
    webhooks = db.query(WebhookSubscription).filter(
        WebhookSubscription.user_id == current_user.id
    ).all()

    return webhooks


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    webhook_data: WebhookUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update webhook subscription."""
    webhook = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id
    ).first()

    if not webhook:
        raise HTTPException(404, "Webhook not found")

    # Update fields
    for field, value in webhook_data.dict(exclude_unset=True).items():
        setattr(webhook, field, value)

    db.commit()
    db.refresh(webhook)

    return webhook


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete webhook subscription."""
    webhook = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id
    ).first()

    if not webhook:
        raise HTTPException(404, "Webhook not found")

    db.delete(webhook)
    db.commit()

    return {"message": "Webhook deleted"}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send test webhook delivery."""
    webhook = db.query(WebhookSubscription).filter(
        WebhookSubscription.id == webhook_id,
        WebhookSubscription.user_id == current_user.id
    ).first()

    if not webhook:
        raise HTTPException(404, "Webhook not found")

    # Send test webhook
    from backend.services.webhook_service import WebhookService

    service = WebhookService()
    delivery = service._send_webhook(
        subscription=webhook,
        event_type='webhook_test',
        payload={'message': 'This is a test webhook'}
    )

    return {
        'status': delivery.status,
        'message': 'Test webhook sent'
    }
```

---

## Push Notifications

### Push Service Implementation

```python
# backend/services/push_service.py
from typing import Dict, Any, List
import logging

from firebase_admin import messaging
import firebase_admin
from firebase_admin import credentials

from backend.models import User, PushDevice, NotificationDelivery

logger = logging.getLogger(__name__)


class PushService:
    def __init__(self):
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            cred = credentials.Certificate('path/to/serviceAccountKey.json')
            firebase_admin.initialize_app(cred)

    def send(
        self,
        user: User,
        event_type: str,
        payload: Dict[str, Any]
    ) -> List[NotificationDelivery]:
        """
        Send push notifications to all user's devices.

        Args:
            user: Target user
            event_type: Type of notification
            payload: Notification data

        Returns:
            List of delivery records
        """
        logger.info(
            f"Sending push notifications to user {user.id}",
            extra={'event_type': event_type}
        )

        # Get user's active devices
        devices = db.query(PushDevice).filter(
            PushDevice.user_id == user.id,
            PushDevice.is_active == True
        ).all()

        if not devices:
            logger.info(f"No active push devices for user {user.id}")
            return []

        deliveries = []

        for device in devices:
            delivery = self._send_to_device(
                device=device,
                event_type=event_type,
                payload=payload
            )
            deliveries.append(delivery)

        return deliveries

    def _send_to_device(
        self,
        device: PushDevice,
        event_type: str,
        payload: Dict[str, Any]
    ) -> NotificationDelivery:
        """Send push notification to single device."""
        # Prepare notification
        title, body = self._get_notification_content(event_type, payload)

        # Create delivery record
        delivery = NotificationDelivery(
            event_id=payload.get('event_id'),
            channel='push',
            recipient=device.device_token,
            status='pending'
        )
        db.add(delivery)
        db.commit()

        try:
            # Build message
            if device.platform == 'ios':
                message = self._build_ios_message(
                    device_token=device.device_token,
                    title=title,
                    body=body,
                    data=payload
                )
            elif device.platform == 'android':
                message = self._build_android_message(
                    device_token=device.device_token,
                    title=title,
                    body=body,
                    data=payload
                )
            else:  # web
                message = self._build_web_message(
                    device_token=device.device_token,
                    title=title,
                    body=body,
                    data=payload
                )

            # Send via FCM
            response = messaging.send(message)

            # Update delivery
            delivery.status = 'delivered'
            delivery.delivered_at = datetime.utcnow()

            # Update device last used
            device.last_used_at = datetime.utcnow()

            logger.info(f"Push notification delivered: {response}")

        except messaging.UnregisteredError:
            # Device token is invalid - deactivate device
            logger.warning(f"Invalid device token, deactivating: {device.id}")
            device.is_active = False
            delivery.status = 'failed'
            delivery.error_message = 'Invalid device token'

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}", exc_info=True)
            delivery.status = 'failed'
            delivery.error_message = str(e)

            if delivery.retry_count < delivery.max_retries:
                self._schedule_retry(delivery)

        db.commit()
        return delivery

    def _build_ios_message(
        self,
        device_token: str,
        title: str,
        body: str,
        data: Dict[str, Any]
    ) -> messaging.Message:
        """Build iOS-specific push notification."""
        return messaging.Message(
            token=device_token,
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            apns=messaging.APNSConfig(
                headers={'apns-priority': '10'},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=title,
                            body=body
                        ),
                        badge=1,
                        sound='default',
                        category='document_notification'
                    )
                )
            ),
            data={k: str(v) for k, v in data.items()}
        )

    def _build_android_message(
        self,
        device_token: str,
        title: str,
        body: str,
        data: Dict[str, Any]
    ) -> messaging.Message:
        """Build Android-specific push notification."""
        return messaging.Message(
            token=device_token,
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    title=title,
                    body=body,
                    icon='notification_icon',
                    color='#4F46E5',
                    sound='default',
                    channel_id='document_notifications'
                )
            ),
            data={k: str(v) for k, v in data.items()}
        )

    def _build_web_message(
        self,
        device_token: str,
        title: str,
        body: str,
        data: Dict[str, Any]
    ) -> messaging.Message:
        """Build web push notification."""
        return messaging.Message(
            token=device_token,
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title,
                    body=body,
                    icon='/icon-192.png',
                    badge='/badge-72.png',
                    vibrate=[200, 100, 200]
                ),
                fcm_options=messaging.WebpushFCMOptions(
                    link='https://app.ablage-system.com'
                )
            ),
            data={k: str(v) for k, v in data.items()}
        )

    def _get_notification_content(
        self,
        event_type: str,
        payload: Dict[str, Any]
    ) -> tuple[str, str]:
        """Get notification title and body."""
        content = {
            'document_processed': (
                'Document Processed',
                f'{payload.get("filename")} is ready'
            ),
            'document_failed': (
                'Processing Failed',
                f'{payload.get("filename")} could not be processed'
            ),
            'upload_complete': (
                'Upload Complete',
                'Your document has been uploaded successfully'
            )
        }

        return content.get(
            event_type,
            ('Notification', 'You have a new notification')
        )
```

---

## In-App Notifications

### In-App Service Implementation

```python
# backend/services/in_app_service.py
from typing import Dict, Any
import logging

from backend.models import User, InAppNotification
from backend.websocket import notification_manager

logger = logging.getLogger(__name__)


class InAppService:
    def send(
        self,
        user: User,
        event_type: str,
        payload: Dict[str, Any]
    ):
        """
        Create in-app notification and send via WebSocket.

        Args:
            user: Target user
            event_type: Type of notification
            payload: Notification data
        """
        logger.info(
            f"Creating in-app notification for user {user.id}",
            extra={'event_type': event_type}
        )

        # Determine notification type and content
        notif_type, title, message, action = self._get_notification_details(
            event_type,
            payload
        )

        # Create in-app notification
        notification = InAppNotification(
            user_id=user.id,
            title=title,
            message=message,
            type=notif_type,
            action_url=action.get('url') if action else None,
            action_label=action.get('label') if action else None
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        # Send via WebSocket if user is online
        notification_manager.send_to_user(
            user_id=str(user.id),
            message={
                'type': 'notification',
                'data': {
                    'id': str(notification.id),
                    'title': title,
                    'message': message,
                    'type': notif_type,
                    'action': action,
                    'created_at': notification.created_at.isoformat()
                }
            }
        )

        logger.info(f"In-app notification created: {notification.id}")

        return notification

    def _get_notification_details(
        self,
        event_type: str,
        payload: Dict[str, Any]
    ) -> tuple:
        """
        Get notification details based on event type.

        Returns:
            Tuple of (type, title, message, action)
        """
        details = {
            'document_processed': (
                'success',
                'Document Processed',
                f'{payload.get("filename")} has been successfully processed.',
                {
                    'url': f'/documents/{payload.get("document_id")}',
                    'label': 'View Document'
                }
            ),
            'document_failed': (
                'error',
                'Processing Failed',
                f'Failed to process {payload.get("filename")}. Please try again.',
                {
                    'url': f'/documents/{payload.get("document_id")}',
                    'label': 'View Details'
                }
            ),
            'upload_complete': (
                'info',
                'Upload Complete',
                f'{payload.get("filename")} uploaded successfully. Processing will begin shortly.',
                None
            ),
            'security_alert': (
                'warning',
                'Security Alert',
                'Unusual activity detected on your account. Please review.',
                {
                    'url': '/settings/security',
                    'label': 'Review Security'
                }
            )
        }

        return details.get(
            event_type,
            ('info', 'Notification', 'You have a new notification', None)
        )
```

### WebSocket Manager

```python
# backend/websocket.py
from typing import Dict, Set
from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self):
        # Active connections: user_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Register new WebSocket connection."""
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()

        self.active_connections[user_id].add(websocket)

        logger.info(f"User {user_id} connected via WebSocket")

        # Send connection confirmation
        await websocket.send_json({
            'type': 'connected',
            'message': 'Connected to notification stream'
        })

    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Unregister WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        logger.info(f"User {user_id} disconnected from WebSocket")

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to all user's active connections."""
        if user_id not in self.active_connections:
            logger.debug(f"User {user_id} not connected via WebSocket")
            return

        disconnected = set()

        for connection in self.active_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to WebSocket: {e}")
                disconnected.add(connection)

        # Clean up disconnected connections
        for connection in disconnected:
            await self.disconnect(connection, user_id)


# Global instance
notification_manager = NotificationManager()
```

### WebSocket Endpoint

```python
# backend/api/v1/notifications.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.websocket import notification_manager
from backend.api.dependencies import get_current_user_ws

router = APIRouter()


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    user_id: str = Depends(get_current_user_ws)
):
    """
    WebSocket endpoint for real-time notifications.

    Client should connect with authentication token in query params:
    ws://api.ablage-system.com/ws/notifications?token=<jwt_token>
    """
    await notification_manager.connect(websocket, user_id)

    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_text()

            # Handle ping/pong
            if data == 'ping':
                await websocket.send_text('pong')

    except WebSocketDisconnect:
        await notification_manager.disconnect(websocket, user_id)
```

---

## Template System

### Template Management

```python
# backend/services/template_service.py
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, Template
import yaml
import logging

logger = logging.getLogger(__name__)


class TemplateService:
    def __init__(self):
        self.env = Environment(
            loader=FileSystemLoader('backend/templates'),
            autoescape=True
        )

        # Load template metadata
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """Load template metadata from YAML files."""
        with open('backend/templates/metadata.yaml', 'r') as f:
            return yaml.safe_load(f)

    def render(
        self,
        template_id: str,
        context: Dict[str, Any],
        format: str = 'html'
    ) -> str:
        """
        Render template with context.

        Args:
            template_id: Template identifier
            context: Template context data
            format: Output format ('html', 'text', 'json')

        Returns:
            Rendered content
        """
        template_path = f'{template_id}.{format}.jinja2'

        try:
            template = self.env.get_template(template_path)
            return template.render(**context)

        except Exception as e:
            logger.error(f"Failed to render template {template_id}: {e}")
            raise

    def get_preview(self, template_id: str) -> Dict[str, str]:
        """Get template preview with sample data."""
        metadata = self.metadata.get(template_id, {})
        sample_data = metadata.get('sample_data', {})

        return {
            'html': self.render(template_id, sample_data, 'html'),
            'text': self.render(template_id, sample_data, 'text')
        }

    def list_templates(self) -> List[Dict]:
        """List all available templates."""
        return [
            {
                'id': template_id,
                'name': meta.get('name'),
                'description': meta.get('description'),
                'variables': meta.get('variables', [])
            }
            for template_id, meta in self.metadata.items()
        ]
```

### Template Metadata

```yaml
# backend/templates/metadata.yaml
document_processed:
  name: "Document Processed"
  description: "Sent when document processing completes successfully"
  variables:
    - name: user.username
      description: "Username"
      type: string
    - name: payload.document.filename
      description: "Document filename"
      type: string
    - name: payload.document.page_count
      description: "Number of pages"
      type: integer
    - name: payload.processing_time
      description: "Processing time in seconds"
      type: number
    - name: payload.confidence
      description: "OCR confidence score (0-1)"
      type: number
  sample_data:
    user:
      username: "john_doe"
      email: "john@example.com"
    payload:
      document:
        id: "123e4567-e89b-12d3-a456-426614174000"
        filename: "invoice_2025.pdf"
        page_count: 3
      processing_time: 2.5
      confidence: 0.96

document_failed:
  name: "Document Processing Failed"
  description: "Sent when document processing fails"
  variables:
    - name: payload.document.filename
      description: "Document filename"
      type: string
    - name: payload.error_message
      description: "Error description"
      type: string
  sample_data:
    user:
      username: "john_doe"
    payload:
      document:
        filename: "corrupted.pdf"
      error_message: "File is corrupted or unreadable"
```

---

## User Preferences

### Preference Management API

```python
# backend/api/v1/notification_preferences.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.models import NotificationPreference
from backend.schemas.notification import (
    PreferenceCreate,
    PreferenceUpdate,
    PreferenceResponse
)
from backend.api.dependencies import get_db, get_current_user

router = APIRouter(prefix="/notification-preferences", tags=["preferences"])


@router.get("/", response_model=List[PreferenceResponse])
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all notification preferences for current user."""
    preferences = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id
    ).all()

    # Include defaults for event types without explicit preferences
    event_types = [
        'document_processed',
        'document_failed',
        'upload_complete',
        'security_alert',
        'system_maintenance'
    ]

    existing_prefs = {
        (p.event_type, p.channel): p
        for p in preferences
    }

    all_preferences = []

    for event_type in event_types:
        for channel in ['email', 'push', 'in_app']:
            key = (event_type, channel)

            if key in existing_prefs:
                all_preferences.append(existing_prefs[key])
            else:
                # Create default preference
                default_enabled = (
                    channel == 'in_app' or
                    (channel == 'email' and event_type in ['security_alert'])
                )

                all_preferences.append({
                    'event_type': event_type,
                    'channel': channel,
                    'enabled': default_enabled
                })

    return all_preferences


@router.put("/{event_type}/{channel}", response_model=PreferenceResponse)
async def update_preference(
    event_type: str,
    channel: str,
    preference_data: PreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update notification preference for specific event type and channel."""
    # Get or create preference
    preference = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == current_user.id,
        NotificationPreference.event_type == event_type,
        NotificationPreference.channel == channel
    ).first()

    if preference:
        # Update existing
        for field, value in preference_data.dict(exclude_unset=True).items():
            setattr(preference, field, value)
    else:
        # Create new
        preference = NotificationPreference(
            user_id=current_user.id,
            event_type=event_type,
            channel=channel,
            **preference_data.dict()
        )
        db.add(preference)

    db.commit()
    db.refresh(preference)

    return preference


@router.post("/batch", response_model=List[PreferenceResponse])
async def batch_update_preferences(
    preferences: List[PreferenceCreate],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Batch update multiple preferences at once."""
    updated = []

    for pref_data in preferences:
        # Get or create
        preference = db.query(NotificationPreference).filter(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.event_type == pref_data.event_type,
            NotificationPreference.channel == pref_data.channel
        ).first()

        if preference:
            for field, value in pref_data.dict(exclude_unset=True).items():
                setattr(preference, field, value)
        else:
            preference = NotificationPreference(
                user_id=current_user.id,
                **pref_data.dict()
            )
            db.add(preference)

        updated.append(preference)

    db.commit()

    return updated
```

### Frontend Preferences Component

```typescript
// frontend/src/components/NotificationPreferences.tsx
import { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';

interface Preference {
  event_type: string;
  channel: string;
  enabled: boolean;
  quiet_hours_start?: string;
  quiet_hours_end?: string;
}

export const NotificationPreferences: React.FC = () => {
  const [preferences, setPreferences] = useState<Preference[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ['notification-preferences'],
    queryFn: () => fetch('/api/v1/notification-preferences').then(r => r.json())
  });

  const { mutate: updatePreferences } = useMutation({
    mutationFn: (prefs: Preference[]) =>
      fetch('/api/v1/notification-preferences/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(prefs)
      }),
    onSuccess: () => {
      toast.success('Preferences updated');
    }
  });

  useEffect(() => {
    if (data) {
      setPreferences(data);
    }
  }, [data]);

  const togglePreference = (eventType: string, channel: string) => {
    const updated = preferences.map(p =>
      p.event_type === eventType && p.channel === channel
        ? { ...p, enabled: !p.enabled }
        : p
    );

    setPreferences(updated);
    updatePreferences(updated);
  };

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Notification Preferences</h2>

      <div className="space-y-4">
        {['document_processed', 'document_failed', 'security_alert'].map(eventType => (
          <div key={eventType} className="border rounded-lg p-4">
            <h3 className="font-semibold mb-3 capitalize">
              {eventType.replace(/_/g, ' ')}
            </h3>

            <div className="grid grid-cols-3 gap-4">
              {['email', 'push', 'in_app'].map(channel => {
                const pref = preferences.find(
                  p => p.event_type === eventType && p.channel === channel
                );

                return (
                  <label key={channel} className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={pref?.enabled || false}
                      onChange={() => togglePreference(eventType, channel)}
                      className="rounded"
                    />
                    <span className="capitalize">{channel}</span>
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
```

---

## Delivery Management

### Retry Logic

```python
# backend/tasks/notifications.py
from celery import Task
from backend.celery_app import celery_app
from backend.models import NotificationDelivery
from backend.services import (
    EmailService,
    WebhookService,
    PushService
)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60
)
def retry_email_delivery(self, delivery_id: str):
    """Retry failed email delivery."""
    delivery = db.query(NotificationDelivery).get(delivery_id)

    if not delivery or delivery.status == 'delivered':
        return

    # Increment retry count
    delivery.retry_count += 1
    db.commit()

    # Get user and event details
    event = delivery.event
    user = event.user

    # Retry delivery
    email_service = EmailService()

    try:
        email_service.send(user, event.event_type, event.payload)
    except Exception as exc:
        if delivery.retry_count < delivery.max_retries:
            # Schedule another retry
            raise self.retry(exc=exc, countdown=60 * (2 ** delivery.retry_count))
        else:
            # Max retries reached, give up
            delivery.status = 'failed'
            delivery.error_message = f"Max retries exceeded: {str(exc)}"
            db.commit()


@celery_app.task(bind=True, max_retries=3)
def retry_webhook_delivery(self, delivery_id: str):
    """Retry failed webhook delivery."""
    delivery = db.query(NotificationDelivery).get(delivery_id)

    if not delivery or delivery.status == 'delivered':
        return

    delivery.retry_count += 1
    db.commit()

    event = delivery.event
    user = event.user

    webhook_service = WebhookService()

    # Get subscription
    subscription = db.query(WebhookSubscription).filter(
        WebhookSubscription.url == delivery.recipient,
        WebhookSubscription.user_id == user.id
    ).first()

    if not subscription:
        delivery.status = 'failed'
        delivery.error_message = 'Subscription not found'
        db.commit()
        return

    try:
        webhook_service._send_webhook(
            subscription=subscription,
            event_type=event.event_type,
            payload=event.payload
        )
    except Exception as exc:
        if delivery.retry_count < delivery.max_retries:
            raise self.retry(exc=exc, countdown=60 * (3 ** delivery.retry_count))
```

### Dead Letter Queue

```python
# backend/services/dlq_service.py
from typing import List
import logging

from backend.models import NotificationDelivery

logger = logging.getLogger(__name__)


class DeadLetterQueueService:
    """Handle permanently failed notifications."""

    def process_failed_deliveries(self):
        """Process notifications that exceeded max retries."""
        # Get permanently failed deliveries
        failed = db.query(NotificationDelivery).filter(
            NotificationDelivery.status == 'failed',
            NotificationDelivery.retry_count >= NotificationDelivery.max_retries
        ).all()

        for delivery in failed:
            self._handle_failed_delivery(delivery)

    def _handle_failed_delivery(self, delivery: NotificationDelivery):
        """Handle single failed delivery."""
        logger.warning(
            f"Permanently failed delivery: {delivery.id}",
            extra={
                'delivery_id': delivery.id,
                'channel': delivery.channel,
                'recipient': delivery.recipient,
                'error': delivery.error_message
            }
        )

        # Log to monitoring system
        self._log_to_monitoring(delivery)

        # Notify administrators if critical
        if delivery.event.priority == 'critical':
            self._notify_admins(delivery)

        # Archive delivery
        self._archive_delivery(delivery)

    def _log_to_monitoring(self, delivery: NotificationDelivery):
        """Log failed delivery to monitoring system."""
        from backend.core.metrics import notification_delivery_failed

        notification_delivery_failed.labels(
            channel=delivery.channel,
            event_type=delivery.event.event_type
        ).inc()

    def _notify_admins(self, delivery: NotificationDelivery):
        """Notify administrators about critical delivery failure."""
        # Send email to admin team
        admin_email = "admin@ablage-system.com"

        message = f"""
        Critical notification delivery failed:

        Delivery ID: {delivery.id}
        Channel: {delivery.channel}
        Recipient: {delivery.recipient}
        Event Type: {delivery.event.event_type}
        Error: {delivery.error_message}

        Please investigate.
        """

        # Send via separate channel to avoid recursion
        import smtplib
        # ... send email

    def _archive_delivery(self, delivery: NotificationDelivery):
        """Archive failed delivery for later analysis."""
        # Move to archive table or cold storage
        pass
```

---

## Rate Limiting & Throttling

### Rate Limiter Implementation

```python
# backend/services/rate_limiter.py
from typing import Optional
import redis
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class NotificationRateLimiter:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)

        # Rate limit configurations (per user)
        self.limits = {
            'email': {
                'per_minute': 5,
                'per_hour': 50,
                'per_day': 200
            },
            'push': {
                'per_minute': 10,
                'per_hour': 100,
                'per_day': 500
            },
            'in_app': {
                'per_minute': 20,
                'per_hour': 500,
                'per_day': 2000
            }
        }

    def check_rate_limit(
        self,
        user_id: str,
        channel: str,
        event_type: str
    ) -> tuple[bool, Optional[int]]:
        """
        Check if user has exceeded rate limits for channel.

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        limits = self.limits.get(channel, {})

        for period, max_count in limits.items():
            key = f"rate_limit:{channel}:{user_id}:{period}"

            # Get current count
            count = self.redis.get(key)
            count = int(count) if count else 0

            if count >= max_count:
                # Rate limit exceeded
                ttl = self.redis.ttl(key)

                logger.warning(
                    f"Rate limit exceeded for user {user_id}",
                    extra={
                        'channel': channel,
                        'period': period,
                        'count': count,
                        'limit': max_count
                    }
                )

                return False, ttl

        # Increment counters
        self._increment_counters(user_id, channel)

        return True, None

    def _increment_counters(self, user_id: str, channel: str):
        """Increment rate limit counters."""
        now = datetime.utcnow()

        # Per minute
        key = f"rate_limit:{channel}:{user_id}:per_minute"
        self.redis.incr(key)
        self.redis.expire(key, 60)

        # Per hour
        key = f"rate_limit:{channel}:{user_id}:per_hour"
        self.redis.incr(key)
        self.redis.expire(key, 3600)

        # Per day
        key = f"rate_limit:{channel}:{user_id}:per_day"
        self.redis.incr(key)
        self.redis.expire(key, 86400)

    def get_remaining(
        self,
        user_id: str,
        channel: str
    ) -> dict:
        """Get remaining rate limit quota for user."""
        limits = self.limits.get(channel, {})
        remaining = {}

        for period, max_count in limits.items():
            key = f"rate_limit:{channel}:{user_id}:{period}"
            count = int(self.redis.get(key) or 0)

            remaining[period] = {
                'limit': max_count,
                'used': count,
                'remaining': max_count - count,
                'reset_in': self.redis.ttl(key)
            }

        return remaining
```

### Throttling Implementation

```python
# backend/services/throttler.py
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio


class NotificationThrottler:
    """
    Throttle notifications to prevent overwhelming users.
    Batch similar notifications together.
    """

    def __init__(self):
        # Pending notifications: user_id -> event_type -> list of payloads
        self.pending = defaultdict(lambda: defaultdict(list))

        # Throttle windows (in seconds)
        self.windows = {
            'document_processed': 300,  # 5 minutes
            'document_failed': 60,      # 1 minute
            'default': 180              # 3 minutes
        }

    async def add_notification(
        self,
        user_id: str,
        event_type: str,
        payload: dict
    ):
        """Add notification to throttle queue."""
        self.pending[user_id][event_type].append({
            'payload': payload,
            'timestamp': datetime.utcnow()
        })

        # Schedule flush if not already scheduled
        window = self.windows.get(event_type, self.windows['default'])

        asyncio.create_task(
            self._flush_after_delay(user_id, event_type, window)
        )

    async def _flush_after_delay(
        self,
        user_id: str,
        event_type: str,
        delay: int
    ):
        """Flush notifications after delay."""
        await asyncio.sleep(delay)

        notifications = self.pending[user_id][event_type]

        if not notifications:
            return

        # Batch notifications
        if len(notifications) > 1:
            # Send digest
            await self._send_digest(user_id, event_type, notifications)
        else:
            # Send single notification
            await self._send_single(user_id, event_type, notifications[0])

        # Clear pending
        self.pending[user_id][event_type] = []

    async def _send_digest(
        self,
        user_id: str,
        event_type: str,
        notifications: list
    ):
        """Send digest notification."""
        from backend.services.notification_service import NotificationService

        service = NotificationService()

        # Create digest payload
        digest_payload = {
            'count': len(notifications),
            'items': [n['payload'] for n in notifications],
            'first_timestamp': notifications[0]['timestamp'],
            'last_timestamp': notifications[-1]['timestamp']
        }

        user = db.query(User).get(user_id)

        service.send_notification(
            user=user,
            event_type=f'{event_type}_digest',
            payload=digest_payload,
            priority='low'
        )

    async def _send_single(
        self,
        user_id: str,
        event_type: str,
        notification: dict
    ):
        """Send single notification."""
        from backend.services.notification_service import NotificationService

        service = NotificationService()
        user = db.query(User).get(user_id)

        service.send_notification(
            user=user,
            event_type=event_type,
            payload=notification['payload']
        )
```

---

## Monitoring & Analytics

### Metrics Collection

```python
# backend/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Notification metrics
notifications_sent_total = Counter(
    'notifications_sent_total',
    'Total notifications sent',
    ['channel', 'event_type', 'status']
)

notification_delivery_duration = Histogram(
    'notification_delivery_duration_seconds',
    'Notification delivery duration',
    ['channel'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

notification_delivery_failed = Counter(
    'notification_delivery_failed_total',
    'Failed notification deliveries',
    ['channel', 'event_type', 'error_type']
)

notification_queue_size = Gauge(
    'notification_queue_size',
    'Current notification queue size',
    ['priority']
)

notification_rate_limit_exceeded = Counter(
    'notification_rate_limit_exceeded_total',
    'Rate limit exceeded events',
    ['user_id', 'channel']
)
```

### Analytics Dashboard

```python
# backend/api/v1/analytics.py
from fastapi import APIRouter, Depends
from sqlalchemy import func
from datetime import datetime, timedelta

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/notification-stats")
async def get_notification_stats(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notification statistics for user."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Deliveries by channel
    by_channel = db.query(
        NotificationDelivery.channel,
        NotificationDelivery.status,
        func.count(NotificationDelivery.id).label('count')
    ).filter(
        NotificationDelivery.created_at >= cutoff
    ).join(
        NotificationEvent
    ).filter(
        NotificationEvent.user_id == current_user.id
    ).group_by(
        NotificationDelivery.channel,
        NotificationDelivery.status
    ).all()

    # Deliveries by event type
    by_event_type = db.query(
        NotificationEvent.event_type,
        func.count(NotificationEvent.id).label('count')
    ).filter(
        NotificationEvent.user_id == current_user.id,
        NotificationEvent.created_at >= cutoff
    ).group_by(
        NotificationEvent.event_type
    ).all()

    # Delivery success rate
    total = db.query(
        func.count(NotificationDelivery.id)
    ).join(NotificationEvent).filter(
        NotificationEvent.user_id == current_user.id,
        NotificationDelivery.created_at >= cutoff
    ).scalar()

    delivered = db.query(
        func.count(NotificationDelivery.id)
    ).join(NotificationEvent).filter(
        NotificationEvent.user_id == current_user.id,
        NotificationDelivery.created_at >= cutoff,
        NotificationDelivery.status == 'delivered'
    ).scalar()

    success_rate = (delivered / total * 100) if total > 0 else 0

    return {
        'period_days': days,
        'by_channel': [
            {'channel': c, 'status': s, 'count': count}
            for c, s, count in by_channel
        ],
        'by_event_type': [
            {'event_type': et, 'count': count}
            for et, count in by_event_type
        ],
        'total_sent': total,
        'total_delivered': delivered,
        'success_rate': round(success_rate, 2)
    }
```

---

## Best Practices

### 1. Notification Design

- **Be Concise**: Clear, actionable messages
- **Provide Context**: Include relevant details
- **Add Actions**: Deep links to relevant pages
- **Respect Timing**: Use quiet hours for non-critical notifications
- **Personalize**: Use user's name and preferences

### 2. Delivery Optimization

- **Batch Similar Notifications**: Reduce notification fatigue
- **Prioritize Channels**: Use most reliable channel first
- **Implement Backoff**: Exponential retry delays
- **Monitor Delivery**: Track success rates per channel
- **Clean Invalid Tokens**: Remove bounced emails, invalid devices

### 3. User Experience

- **Provide Controls**: Let users customize preferences
- **Show History**: Allow users to view past notifications
- **Offer Digest Mode**: Daily/weekly summaries
- **Support Opt-Out**: Easy unsubscribe options
- **Test Templates**: Preview before sending

### 4. Security

- **Validate Recipients**: Verify email addresses, URLs
- **Sign Webhooks**: Use HMAC signatures
- **Sanitize Content**: Prevent XSS in notifications
- **Rate Limit**: Prevent abuse
- **Audit Logging**: Track all notification sends

---

## Troubleshooting

### Common Issues

#### Emails Not Delivered

**Symptoms**: Users not receiving emails

**Diagnosis**:
```bash
# Check SMTP connection
telnet smtp.example.com 587

# Check email delivery logs
tail -f /var/log/mail.log

# Check SendGrid dashboard for bounces
```

**Solutions**:
- Verify SMTP credentials
- Check SPF/DKIM records
- Review bounce reports
- Whitelist sender domain

#### Webhooks Failing

**Symptoms**: Webhook deliveries showing failed status

**Diagnosis**:
```python
# Check webhook subscription status
webhooks = db.query(WebhookSubscription).filter(
    WebhookSubscription.is_active == False
).all()

# Review recent failures
recent_failures = db.query(NotificationDelivery).filter(
    NotificationDelivery.channel == 'webhook',
    NotificationDelivery.status == 'failed',
    NotificationDelivery.created_at >= datetime.utcnow() - timedelta(hours=1)
).all()
```

**Solutions**:
- Verify webhook URL is accessible
- Check SSL certificate validity
- Increase timeout setting
- Review webhook secret configuration

#### Push Notifications Not Appearing

**Symptoms**: Push notifications not reaching devices

**Diagnosis**:
```python
# Check active devices
devices = db.query(PushDevice).filter(
    PushDevice.user_id == user_id,
    PushDevice.is_active == True
).all()

# Test FCM connection
from firebase_admin import messaging
try:
    messaging.send(test_message)
except Exception as e:
    print(f"FCM Error: {e}")
```

**Solutions**:
- Verify FCM/APNS credentials
- Check device tokens are valid
- Review app notification permissions
- Test with Firebase console

---

## Appendix

### Event Type Reference

| Event Type | Description | Default Channels | Priority |
|------------|-------------|------------------|----------|
| `document_processed` | Document processing completed | Email, In-App | Medium |
| `document_failed` | Document processing failed | Email, In-App | High |
| `upload_complete` | File upload successful | In-App | Low |
| `user_registered` | New user registration | Email | Medium |
| `password_reset` | Password reset requested | Email | High |
| `security_alert` | Unusual activity detected | Email, Push, In-App | Critical |
| `account_activated` | Account activation complete | Email | Medium |
| `system_maintenance` | Scheduled maintenance notice | Email, In-App | Low |

### Configuration Reference

```yaml
# config/notifications.yaml
channels:
  email:
    provider: sendgrid  # or smtp
    from_email: noreply@ablage-system.com
    from_name: Ablage System
    reply_to: support@ablage-system.com

  webhook:
    timeout_seconds: 30
    max_retries: 3
    retry_delay_seconds: 60

  push:
    provider: fcm
    batch_size: 500

  in_app:
    retention_days: 30
    max_per_user: 100

rate_limits:
  email:
    per_minute: 5
    per_hour: 50
    per_day: 200

  push:
    per_minute: 10
    per_hour: 100
    per_day: 500

throttling:
  enabled: true
  window_seconds: 300
  batch_threshold: 3
```

---

**Document Version**: 1.0.0
**Last Updated**: 2025-01-15
**Next Review**: 2025-04-15
**Owner**: Platform Team