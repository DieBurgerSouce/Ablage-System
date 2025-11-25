# Security Scanning

You are performing a comprehensive security audit of the codebase.

## Your Task

Run multiple security scanning tools and analyze results:

### 1. Python Security Scanners

#### Bandit (Already in pre-commit)
```bash
bandit -r app/ -f json -o reports/bandit.json
```

Scan for:
- Hardcoded passwords
- SQL injection vulnerabilities
- Insecure deserialization
- Weak cryptography
- Shell injection risks

#### Safety (Dependency Vulnerabilities)
```bash
safety check --json --output reports/safety.json
```

Check for known vulnerabilities in dependencies.

#### pip-audit (Alternative to Safety)
```bash
pip-audit --format json --output reports/pip-audit.json
```

### 2. Secret Detection

#### detect-secrets (Already configured)
```bash
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit .secrets.baseline
```

Verify no secrets in:
- Code
- Configuration files
- Documentation
- Git history

### 3. Dependency Analysis

#### List All Dependencies
```bash
pip list --format json > reports/dependencies.json
```

#### Check for Outdated Packages
```bash
pip list --outdated
```

#### License Compliance
```bash
pip-licenses --format json --output-file reports/licenses.json
```

Check for incompatible licenses.

### 4. Docker Security

#### Trivy (Container Scanning)
```bash
trivy image ablage-backend:latest --format json --output reports/trivy-backend.json
trivy image ablage-worker:latest --format json --output reports/trivy-worker.json
```

Scan for:
- OS vulnerabilities
- Library vulnerabilities
- Misconfigurations

#### Hadolint (Dockerfile Linting) - Already in pre-commit
```bash
hadolint Dockerfile --format json > reports/hadolint.json
```

### 5. Code Quality Security

#### Semgrep (SAST)
```bash
semgrep --config auto --json --output reports/semgrep.json app/
```

Find:
- Security anti-patterns
- Common vulnerabilities
- Best practice violations

### 6. API Security

Check for:
- [ ] HTTPS enforced
- [ ] CORS configured correctly
- [ ] Rate limiting enabled
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention
- [ ] CSRF protection
- [ ] Authentication on sensitive endpoints
- [ ] Authorization checks
- [ ] Proper error messages (no stack traces to users)

### 7. Environment Security

Check `.env.example` and documentation:
- [ ] No default passwords
- [ ] Strong password requirements documented
- [ ] Secrets rotation policy
- [ ] Principle of least privilege

### 8. Database Security

- [ ] Encrypted connections (TLS)
- [ ] Parameterized queries (no string concatenation)
- [ ] Input validation before database operations
- [ ] Database user has minimum required permissions
- [ ] Sensitive data encrypted at rest

### 9. German-Specific Security

- [ ] UTF-8 encoding everywhere (prevent encoding attacks)
- [ ] Proper handling of umlauts in input validation
- [ ] German error messages don't leak sensitive info

### 10. GPU Security

- [ ] Resource limits prevent DoS via GPU exhaustion
- [ ] Input size validation (prevent OOM)
- [ ] Cleanup after exceptions (prevent memory leaks)

## Execution

Run all scanners and generate a comprehensive security report:

### Report Structure

```markdown
# Security Audit Report

**Date:** YYYY-MM-DD
**Scanned By:** Claude Code
**Severity Levels:** Critical, High, Medium, Low, Info

## Executive Summary

- Total Issues: XX
- Critical: XX 🔴
- High: XX 🟠
- Medium: XX 🟡
- Low: XX 🟢

## Findings by Category

### 1. Code Security (Bandit + Semgrep)

#### 🔴 Critical: SQL Injection Risk
**File:** app/services/search.py:42
**Issue:** String concatenation in SQL query
**Remediation:** Use parameterized queries

#### 🟡 Medium: Weak Random
**File:** app/utils/tokens.py:15
**Issue:** Using random.random() for tokens
**Remediation:** Use secrets module

### 2. Dependencies (Safety + pip-audit)

#### 🟠 High: Vulnerable Package
**Package:** pillow==9.0.0
**CVE:** CVE-2023-1234
**Remediation:** Upgrade to pillow>=10.0.0

### 3. Secrets Detection

✅ No secrets found in codebase

### 4. Docker Security (Trivy)

#### 🟠 High: OS Vulnerability
**Image:** ablage-backend:latest
**CVE:** CVE-2023-5678
**Remediation:** Update base image

## Remediation Plan

### Immediate (Critical/High)
1. Fix SQL injection: app/services/search.py
2. Upgrade pillow to 10.0.0
3. ...

### Short-term (Medium)
1. Replace random with secrets module
2. ...

### Long-term (Low)
1. Update documentation
2. ...

## Compliance Checklist

- [ ] OWASP Top 10 addressed
- [ ] GDPR compliance (data encryption, deletion)
- [ ] Secure by default configuration
```

## Output

Provide:
1. Run all security scans
2. Generate comprehensive report
3. Prioritized remediation plan
4. Scripts to automate future scans (`scripts/security_scan.sh`)
