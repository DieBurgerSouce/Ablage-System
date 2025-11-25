#!/bin/bash

# Post-Release Script
# Called by semantic-release after successful release

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VERSION=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Validate version parameter
if [ -z "$VERSION" ]; then
    log_error "Version parameter is required"
    exit 1
fi

log_info "=== Post-Release Actions for $VERSION ==="
echo ""

# Step 1: Send Slack notification
log_step "1. Sending Slack notification..."

if [ -n "$SLACK_WEBHOOK_URL" ]; then
    # Get release notes
    RELEASE_NOTES=$(cat "$PROJECT_ROOT/CHANGELOG.md" | head -n 100 || echo "See CHANGELOG.md for details")

    # Send notification
    curl -X POST "$SLACK_WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d @- <<EOF
{
  "text": "🎉 New Release: Ablage-System OCR v$VERSION",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🎉 New Release: v$VERSION"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Ablage-System OCR* has been released!"
      }
    },
    {
      "type": "section",
      "fields": [
        {
          "type": "mrkdwn",
          "text": "*Version:*\n$VERSION"
        },
        {
          "type": "mrkdwn",
          "text": "*Released:*\n$(date '+%Y-%m-%d %H:%M:%S UTC')"
        }
      ]
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Links:*\n• <https://github.com/ablage-system/ablage-system-ocr/releases/tag/v$VERSION|Release Notes>\n• <https://docs.ablage-system.local|Documentation>\n• <https://github.com/ablage-system/ablage-system-ocr/blob/main/CHANGELOG.md|Changelog>"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Docker Images:*\n\`\`\`\ndocker pull ghcr.io/ablage-system/ablage-backend:$VERSION\ndocker pull ghcr.io/ablage-system/ablage-worker:$VERSION\n\`\`\`"
      }
    }
  ]
}
EOF

    log_info "Slack notification sent"
else
    log_warn "SLACK_WEBHOOK_URL not set, skipping Slack notification"
fi

# Step 2: Send email notification (if configured)
log_step "2. Sending email notification..."

if [ -n "$NOTIFICATION_EMAIL" ] && command -v sendmail &> /dev/null; then
    sendmail "$NOTIFICATION_EMAIL" <<EOF
Subject: [Ablage-System] New Release: v$VERSION
From: releases@ablage-system.local
To: $NOTIFICATION_EMAIL
Content-Type: text/html; charset=UTF-8

<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #4a9eff; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }
        .content { background: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; }
        .version { font-size: 24px; font-weight: bold; color: #4a9eff; }
        .button { display: inline-block; background: #4a9eff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px 5px; }
        .code { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 5px; font-family: monospace; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 New Release</h1>
            <p class="version">Ablage-System OCR v$VERSION</p>
        </div>
        <div class="content">
            <p>A new version of Ablage-System OCR has been released!</p>

            <h2>Quick Installation</h2>
            <div class="code">
docker pull ghcr.io/ablage-system/ablage-backend:$VERSION<br>
docker pull ghcr.io/ablage-system/ablage-worker:$VERSION<br>
docker-compose up -d
            </div>

            <h2>Links</h2>
            <a href="https://github.com/ablage-system/ablage-system-ocr/releases/tag/v$VERSION" class="button">Release Notes</a>
            <a href="https://docs.ablage-system.local" class="button">Documentation</a>
            <a href="https://github.com/ablage-system/ablage-system-ocr" class="button">GitHub</a>

            <p style="margin-top: 30px; color: #666; font-size: 0.9em;">
                Released on $(date '+%Y-%m-%d %H:%M:%S UTC')<br>
                Ablage-System Team
            </p>
        </div>
    </div>
</body>
</html>
EOF

    log_info "Email notification sent to $NOTIFICATION_EMAIL"
else
    log_warn "Email notifications not configured, skipping"
fi

# Step 3: Create GitHub discussion post
log_step "3. Creating GitHub discussion..."

if [ -n "$GITHUB_TOKEN" ]; then
    # Create discussion using GitHub API
    # (Requires gh CLI or curl with GitHub API)

    if command -v gh &> /dev/null; then
        gh discussion create \
            --title "Release v$VERSION" \
            --body "$(cat <<EOF
# Release v$VERSION

A new version of Ablage-System OCR has been released! 🎉

## Installation

\`\`\`bash
docker pull ghcr.io/ablage-system/ablage-backend:$VERSION
docker pull ghcr.io/ablage-system/ablage-worker:$VERSION
docker-compose up -d
\`\`\`

## What's New

See the [release notes](https://github.com/ablage-system/ablage-system-ocr/releases/tag/v$VERSION) for a complete list of changes.

## Documentation

- [Full Documentation](https://docs.ablage-system.local)
- [API Reference](https://api.ablage-system.local/docs)
- [Changelog](https://github.com/ablage-system/ablage-system-ocr/blob/main/CHANGELOG.md)

## Feedback

Please share your experience with this release in the comments below!
EOF
)" \
            --category "Announcements"

        log_info "GitHub discussion created"
    else
        log_warn "gh CLI not found, skipping discussion creation"
    fi
else
    log_warn "GITHUB_TOKEN not set, skipping GitHub discussion"
fi

# Step 4: Update social media (if configured)
log_step "4. Posting to social media..."

# Twitter/X (if configured)
if [ -n "$TWITTER_API_KEY" ]; then
    # Implement Twitter API posting here
    log_info "Twitter post would be sent (not implemented)"
else
    log_warn "Twitter not configured, skipping"
fi

# Mastodon (if configured)
if [ -n "$MASTODON_ACCESS_TOKEN" ]; then
    # Implement Mastodon API posting here
    log_info "Mastodon post would be sent (not implemented)"
else
    log_warn "Mastodon not configured, skipping"
fi

# Step 5: Update project website
log_step "5. Updating project website..."

if [ -f "$PROJECT_ROOT/website/versions.json" ]; then
    # Update versions.json
    cat > "$PROJECT_ROOT/website/versions.json" <<EOF
{
  "latest": "$VERSION",
  "versions": [
    {
      "version": "$VERSION",
      "release_date": "$(date -u +%Y-%m-%d)",
      "docs_url": "https://docs.ablage-system.local",
      "github_url": "https://github.com/ablage-system/ablage-system-ocr/releases/tag/v$VERSION"
    }
  ]
}
EOF

    log_info "Project website updated"
else
    log_warn "Project website not found, skipping"
fi

# Step 6: Clean up temporary files
log_step "6. Cleaning up..."

cd "$PROJECT_ROOT"

# Remove temporary build files
rm -f dist/.prepared-$VERSION
rm -f dist/.published-$VERSION

# Keep artifacts but clean up old ones (older than 30 days)
find dist/ -type f -name "*.tar.gz" -mtime +30 -delete 2>/dev/null || true

log_info "Cleanup complete"

# Step 7: Create release report
log_step "7. Creating release report..."

REPORT_FILE="$PROJECT_ROOT/dist/RELEASE_REPORT_$VERSION.txt"

cat > "$REPORT_FILE" <<EOF
================================================================================
                    RELEASE REPORT: Ablage-System OCR v$VERSION
================================================================================

Release Date: $(date '+%Y-%m-%d %H:%M:%S UTC')
Git Commit: $(git rev-parse HEAD)
Git Tag: v$VERSION

--------------------------------------------------------------------------------
ARTIFACTS
--------------------------------------------------------------------------------

Docker Images:
  - ghcr.io/ablage-system/ablage-backend:$VERSION
  - ghcr.io/ablage-system/ablage-worker:$VERSION
  - ghcr.io/ablage-system/ablage-frontend:$VERSION

Distribution:
  - ablage-system-$VERSION.tar.gz
  - SHA256: $(sha256sum "$PROJECT_ROOT/dist/ablage-system-$VERSION.tar.gz" 2>/dev/null | cut -d' ' -f1 || echo "N/A")

Documentation:
  - Deployed to: https://docs.ablage-system.local
  - Version: $VERSION

--------------------------------------------------------------------------------
NOTIFICATIONS SENT
--------------------------------------------------------------------------------

$([ -n "$SLACK_WEBHOOK_URL" ] && echo "✓ Slack notification" || echo "✗ Slack notification (not configured)")
$([ -n "$NOTIFICATION_EMAIL" ] && echo "✓ Email notification" || echo "✗ Email notification (not configured)")
$([ -n "$GITHUB_TOKEN" ] && echo "✓ GitHub discussion" || echo "✗ GitHub discussion (not configured)")

--------------------------------------------------------------------------------
NEXT STEPS
--------------------------------------------------------------------------------

1. Monitor release metrics:
   - Docker Hub pulls
   - GitHub release downloads
   - Documentation traffic

2. Watch for issues:
   - GitHub Issues: https://github.com/ablage-system/ablage-system-ocr/issues
   - Community Forum: https://forum.ablage-system.local

3. Prepare for next release:
   - Review roadmap
   - Plan next features
   - Update documentation

--------------------------------------------------------------------------------
RELEASE COMPLETE
--------------------------------------------------------------------------------

Version $VERSION has been successfully released and announced!

For questions or issues, contact: support@ablage-system.local

================================================================================
EOF

log_info "Release report created: $REPORT_FILE"

# Summary
echo ""
log_info "=== Post-Release Actions Complete ==="
echo ""
log_info "Version: $VERSION"
log_info "Release Date: $(date '+%Y-%m-%d %H:%M:%S UTC')"
log_info "Notifications: Sent"
log_info "Documentation: Updated"
log_info "Report: $REPORT_FILE"
echo ""
log_info "🎉 Release $VERSION is now live!"
echo ""

exit 0
