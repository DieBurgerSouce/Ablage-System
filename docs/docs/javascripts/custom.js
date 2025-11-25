/**
 * Custom JavaScript for Ablage-System Documentation
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
  console.log('Ablage-System Docs loaded');

  // Initialize custom features
  initCopyCodeButtons();
  initExternalLinks();
  initSmoothScroll();
  initTableOfContents();
  initAPIExamples();
  initVersionSelector();
});

/**
 * Enhanced copy code button functionality
 */
function initCopyCodeButtons() {
  const codeBlocks = document.querySelectorAll('pre code');

  codeBlocks.forEach(function(block) {
    // Add language label
    const language = block.className.replace('language-', '');
    if (language && language !== 'text') {
      const label = document.createElement('span');
      label.className = 'code-language-label';
      label.textContent = language;
      block.parentElement.insertBefore(label, block);
    }
  });
}

/**
 * Open external links in new tab and add icon
 */
function initExternalLinks() {
  const links = document.querySelectorAll('a[href^="http"]');

  links.forEach(function(link) {
    // Skip if it's an internal link
    if (link.hostname === window.location.hostname) {
      return;
    }

    // Open in new tab
    link.setAttribute('target', '_blank');
    link.setAttribute('rel', 'noopener noreferrer');

    // Add external link icon
    if (!link.querySelector('.external-link-icon')) {
      const icon = document.createElement('span');
      icon.className = 'external-link-icon';
      icon.innerHTML = ' ↗';
      link.appendChild(icon);
    }
  });
}

/**
 * Smooth scroll for anchor links
 */
function initSmoothScroll() {
  const anchorLinks = document.querySelectorAll('a[href^="#"]');

  anchorLinks.forEach(function(link) {
    link.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;

      const targetElement = document.querySelector(targetId);
      if (targetElement) {
        e.preventDefault();
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });

        // Update URL without jumping
        history.pushState(null, null, targetId);
      }
    });
  });
}

/**
 * Enhanced table of contents with active section highlighting
 */
function initTableOfContents() {
  const headings = document.querySelectorAll('h2, h3');
  const tocLinks = document.querySelectorAll('.md-nav__link');

  if (headings.length === 0) return;

  // Highlight active section on scroll
  let ticking = false;
  window.addEventListener('scroll', function() {
    if (!ticking) {
      window.requestAnimationFrame(function() {
        updateActiveTocLink(headings);
        ticking = false;
      });
      ticking = true;
    }
  });
}

/**
 * Update active TOC link based on scroll position
 */
function updateActiveTocLink(headings) {
  const scrollPosition = window.scrollY + 100; // Offset for header

  for (let i = headings.length - 1; i >= 0; i--) {
    const heading = headings[i];
    if (heading.offsetTop <= scrollPosition) {
      const id = heading.getAttribute('id');
      if (id) {
        const activeLink = document.querySelector(`.md-nav__link[href="#${id}"]`);
        if (activeLink) {
          // Remove previous active
          document.querySelectorAll('.md-nav__link--active').forEach(function(link) {
            link.classList.remove('md-nav__link--active');
          });
          // Add new active
          activeLink.classList.add('md-nav__link--active');
        }
      }
      break;
    }
  }
}

/**
 * Interactive API examples with language switching
 */
function initAPIExamples() {
  const apiExamples = document.querySelectorAll('.api-example');

  apiExamples.forEach(function(example) {
    const tabs = example.querySelectorAll('.api-tab');
    const contents = example.querySelectorAll('.api-content');

    tabs.forEach(function(tab) {
      tab.addEventListener('click', function() {
        const language = this.getAttribute('data-language');

        // Update active tab
        tabs.forEach(t => t.classList.remove('active'));
        this.classList.add('active');

        // Show corresponding content
        contents.forEach(function(content) {
          if (content.getAttribute('data-language') === language) {
            content.style.display = 'block';
          } else {
            content.style.display = 'none';
          }
        });
      });
    });
  });
}

/**
 * Version selector functionality
 */
function initVersionSelector() {
  const versionSelector = document.querySelector('.version-selector');
  if (!versionSelector) return;

  versionSelector.addEventListener('change', function() {
    const selectedVersion = this.value;
    if (selectedVersion) {
      window.location.href = selectedVersion;
    }
  });
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function() {
      showCopyNotification('Copied to clipboard!');
    }).catch(function(err) {
      console.error('Failed to copy:', err);
    });
  } else {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      showCopyNotification('Copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy:', err);
    }
    document.body.removeChild(textarea);
  }
}

/**
 * Show copy notification
 */
function showCopyNotification(message) {
  const notification = document.createElement('div');
  notification.className = 'copy-notification';
  notification.textContent = message;
  notification.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: #26de81;
    color: white;
    padding: 1em 1.5em;
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    z-index: 9999;
    animation: slideIn 0.3s ease;
  `;

  document.body.appendChild(notification);

  setTimeout(function() {
    notification.style.animation = 'slideOut 0.3s ease';
    setTimeout(function() {
      document.body.removeChild(notification);
    }, 300);
  }, 2000);
}

/**
 * Add keyboard shortcuts
 */
document.addEventListener('keydown', function(e) {
  // Ctrl+K or Cmd+K: Focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.querySelector('.md-search__input');
    if (searchInput) {
      searchInput.focus();
    }
  }

  // Escape: Close search
  if (e.key === 'Escape') {
    const searchInput = document.querySelector('.md-search__input');
    if (searchInput && document.activeElement === searchInput) {
      searchInput.blur();
    }
  }
});

/**
 * Add CSS animations
 */
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from {
      transform: translateY(100%);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  @keyframes slideOut {
    from {
      transform: translateY(0);
      opacity: 1;
    }
    to {
      transform: translateY(100%);
      opacity: 0;
    }
  }

  .code-language-label {
    position: absolute;
    top: 0.5em;
    right: 3em;
    background: rgba(0,0,0,0.3);
    color: white;
    padding: 0.2em 0.6em;
    border-radius: 3px;
    font-size: 0.75em;
    text-transform: uppercase;
    font-weight: bold;
  }

  .external-link-icon {
    font-size: 0.8em;
    opacity: 0.7;
  }

  pre {
    position: relative;
  }
`;
document.head.appendChild(style);

/**
 * Analytics tracking (optional)
 */
function trackEvent(category, action, label) {
  // Implement your analytics tracking here
  // Example: Google Analytics, Matomo, etc.
  if (typeof gtag !== 'undefined') {
    gtag('event', action, {
      'event_category': category,
      'event_label': label
    });
  }
}

/**
 * Track page views
 */
window.addEventListener('load', function() {
  trackEvent('Page', 'view', window.location.pathname);
});

/**
 * Track external link clicks
 */
document.addEventListener('click', function(e) {
  const link = e.target.closest('a[href^="http"]');
  if (link && link.hostname !== window.location.hostname) {
    trackEvent('Link', 'external_click', link.href);
  }
});

/**
 * Service Worker for offline support (optional)
 */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    // Uncomment to enable service worker
    // navigator.serviceWorker.register('/sw.js');
  });
}

// Export functions for use in other scripts
window.AblageSystemDocs = {
  copyToClipboard: copyToClipboard,
  trackEvent: trackEvent
};
