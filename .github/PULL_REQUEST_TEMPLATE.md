# Pull Request

## 📋 Beschreibung
<!-- Beschreibe deine Änderungen klar und präzise -->

## 🔗 Related Issues
<!-- Verlinke related Issues mit #IssueNumber -->
Closes #
Related to #

## 🎯 Typ der Änderung
<!-- Wähle zutreffende Option(en) -->
- [ ] 🐛 Bug Fix (non-breaking change)
- [ ] ✨ New Feature (non-breaking change)
- [ ] 💥 Breaking Change (fix or feature that causes existing functionality to not work as expected)
- [ ] 📝 Documentation Update
- [ ] 🎨 Code Style/Refactoring (no functional changes)
- [ ] ⚡ Performance Improvement
- [ ] ✅ Test Addition/Enhancement
- [ ] 🔧 Configuration Change

## 🧪 Tests
<!-- Beschreibe wie du getestet hast -->
- [ ] Unit Tests hinzugefügt/aktualisiert
- [ ] Integration Tests hinzugefügt/aktualisiert
- [ ] GPU Tests hinzugefügt (falls relevant)
- [ ] Alle Tests bestehen (`make test`)
- [ ] Coverage >= 80% (`make test-cov`)

### Test Commands
```bash
# Commands die du zum Testen genutzt hast
make test
./scripts/test.sh --coverage
```

## 📊 Code Quality Checks
<!-- Automatisch durch Git Hooks, manuell bestätigen -->
- [ ] Linting passed (`make lint`)
- [ ] Type checking passed (`mypy app/`)
- [ ] Code formatted (`ruff format .`)
- [ ] Pre-commit hooks passed
- [ ] No security issues (`bandit -r app/`)

## 📝 Documentation
<!-- Dokumentation aktualisiert? -->
- [ ] Code-Kommentare hinzugefügt/aktualisiert
- [ ] Docstrings hinzugefügt/aktualisiert (Google-Style)
- [ ] README.md aktualisiert (falls nötig)
- [ ] CLAUDE.md aktualisiert (falls nötig)
- [ ] API Dokumentation aktualisiert (falls nötig)
- [ ] CHANGELOG.md aktualisiert

## 🔒 Security Checklist
<!-- Sicherheitsaspekte berücksichtigt? -->
- [ ] No secrets in code
- [ ] No PII in logs
- [ ] Input validation implemented
- [ ] SQL injection prevented
- [ ] XSS prevention in place
- [ ] Authentication required (if applicable)

## 🇩🇪 German Language Compliance
<!-- Für user-facing Änderungen -->
- [ ] All user-facing text in German
- [ ] UTF-8 encoding preserved
- [ ] Umlaut handling correct (ä, ö, ü, ß)
- [ ] N/A - No user-facing changes

## ⚡ Performance Impact
<!-- Wie wirkt sich diese Änderung auf die Performance aus? -->
- [ ] No performance impact
- [ ] Performance improved
- [ ] Performance degraded (justified below)
- [ ] GPU memory impact (describe below)

**Performance Notes:**
<!-- Falls relevant, beschreibe Performance-Änderungen -->

## 🖼️ Screenshots (falls UI-Änderungen)
<!-- Füge Screenshots für UI-Änderungen hinzu -->

## 📦 Dependencies
<!-- Neue Dependencies hinzugefügt? -->
- [ ] No new dependencies
- [ ] New dependencies added (listed below)
- [ ] requirements.txt updated
- [ ] docker-compose.yml updated (if needed)

**New Dependencies:**
```
# Liste neue Dependencies mit Begründung
```

## 🚀 Deployment Notes
<!-- Besonderheiten beim Deployment? -->
- [ ] No special deployment steps required
- [ ] Database migration required
- [ ] Environment variables added/changed
- [ ] Configuration changes required

**Deployment Steps:**
```bash
# Spezielle Deployment-Schritte
```

## ✅ Final Checklist
<!-- Vor dem Submit durchgehen -->
- [ ] Branch ist up-to-date mit target branch
- [ ] Keine merge conflicts
- [ ] Commit messages follow Conventional Commits
- [ ] Code wurde selbst reviewed (mit `/review-pr`)
- [ ] Breaking changes dokumentiert
- [ ] Migration guide bereitgestellt (bei Breaking Changes)

## 👥 Reviewers
<!-- @ erwähne spezifische Reviewer falls nötig -->
@<!-- Reviewer-Username -->

## 🎓 Learning Notes (optional)
<!-- Was hast du bei dieser Implementierung gelernt? -->

---

**Philosophy Check:** Ist dieser Code "feinpoliert und durchdacht"? 🎯
