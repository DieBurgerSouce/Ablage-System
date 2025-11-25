#!/bin/bash
# Security Scanning Script - Ablage-System OCR
# Comprehensive security analysis of code and dependencies

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPORTS_DIR="security-reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Ensure reports directory exists
mkdir -p "$REPORTS_DIR"

# Tracking variables
ISSUES_CRITICAL=0
ISSUES_HIGH=0
ISSUES_MEDIUM=0
ISSUES_LOW=0

# Function to check dependencies
check_dependencies() {
    echo -e "${BLUE}🔍 Checking security tools...${NC}"

    TOOLS_AVAILABLE=()
    TOOLS_MISSING=()

    # Check Bandit (Python security)
    if command -v bandit &> /dev/null; then
        TOOLS_AVAILABLE+=("bandit")
    else
        TOOLS_MISSING+=("bandit")
    fi

    # Check Safety (dependency vulnerabilities)
    if command -v safety &> /dev/null; then
        TOOLS_AVAILABLE+=("safety")
    else
        TOOLS_MISSING+=("safety")
    fi

    # Check Trivy (container/dependency scanner)
    if command -v trivy &> /dev/null; then
        TOOLS_AVAILABLE+=("trivy")
    else
        TOOLS_MISSING+=("trivy")
    fi

    # Check Semgrep (static analysis)
    if command -v semgrep &> /dev/null; then
        TOOLS_AVAILABLE+=("semgrep")
    else
        TOOLS_MISSING+=("semgrep")
    fi

    # Display results
    if [ ${#TOOLS_AVAILABLE[@]} -gt 0 ]; then
        echo -e "${GREEN}✅ Available tools: ${TOOLS_AVAILABLE[*]}${NC}"
    fi

    if [ ${#TOOLS_MISSING[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Missing tools: ${TOOLS_MISSING[*]}${NC}"
        echo -e "${BLUE}   Install with:${NC}"
        echo -e "     pip install bandit safety semgrep"
        echo -e "     brew install trivy  (or download from https://trivy.dev)"
    fi

    if [ ${#TOOLS_AVAILABLE[@]} -eq 0 ]; then
        echo -e "${RED}❌ No security tools found!${NC}"
        exit 1
    fi
}

# Function to run Bandit security scan
run_bandit() {
    if ! command -v bandit &> /dev/null; then
        return
    fi

    echo -e "${BLUE}🔒 Running Bandit security scan...${NC}"

    BANDIT_REPORT="$REPORTS_DIR/bandit-$TIMESTAMP.json"
    BANDIT_HTML="$REPORTS_DIR/bandit-$TIMESTAMP.html"

    # Run Bandit
    bandit -r app/ \
        -f json -o "$BANDIT_REPORT" \
        --severity-level medium \
        --confidence-level medium \
        || true

    # Generate HTML report
    bandit -r app/ \
        -f html -o "$BANDIT_HTML" \
        --severity-level medium \
        --confidence-level medium \
        || true

    # Parse results
    if [ -f "$BANDIT_REPORT" ]; then
        HIGH=$(cat "$BANDIT_REPORT" | jq '.metrics._totals | select(.SEVERITY.HIGH != null) | .SEVERITY.HIGH' 2>/dev/null || echo "0")
        MEDIUM=$(cat "$BANDIT_REPORT" | jq '.metrics._totals | select(.SEVERITY.MEDIUM != null) | .SEVERITY.MEDIUM' 2>/dev/null || echo "0")
        LOW=$(cat "$BANDIT_REPORT" | jq '.metrics._totals | select(.SEVERITY.LOW != null) | .SEVERITY.LOW' 2>/dev/null || echo "0")

        ISSUES_HIGH=$((ISSUES_HIGH + HIGH))
        ISSUES_MEDIUM=$((ISSUES_MEDIUM + MEDIUM))
        ISSUES_LOW=$((ISSUES_LOW + LOW))

        echo -e "${GREEN}✅ Bandit scan complete${NC}"
        echo -e "   High:   $HIGH issues"
        echo -e "   Medium: $MEDIUM issues"
        echo -e "   Low:    $LOW issues"
        echo -e "   Report: $BANDIT_REPORT"
    fi
}

# Function to run Safety check
run_safety() {
    if ! command -v safety &> /dev/null; then
        return
    fi

    echo -e "${BLUE}🛡️  Running Safety dependency check...${NC}"

    SAFETY_REPORT="$REPORTS_DIR/safety-$TIMESTAMP.json"

    # Run Safety
    safety check \
        -r requirements.txt \
        --json \
        --output "$SAFETY_REPORT" \
        || true

    # Parse results
    if [ -f "$SAFETY_REPORT" ]; then
        VULNS=$(cat "$SAFETY_REPORT" | jq '.vulnerabilities | length' 2>/dev/null || echo "0")

        if [ "$VULNS" -gt 0 ]; then
            ISSUES_HIGH=$((ISSUES_HIGH + VULNS))
            echo -e "${YELLOW}⚠️  Found $VULNS vulnerable dependencies${NC}"

            # Show top vulnerabilities
            echo -e "${BLUE}   Top vulnerabilities:${NC}"
            cat "$SAFETY_REPORT" | jq -r '.vulnerabilities[] | "   - \(.package): \(.vulnerability_name)"' | head -5
        else
            echo -e "${GREEN}✅ No vulnerable dependencies found${NC}"
        fi

        echo -e "   Report: $SAFETY_REPORT"
    fi
}

# Function to run Trivy scan
run_trivy() {
    if ! command -v trivy &> /dev/null; then
        return
    fi

    echo -e "${BLUE}🔍 Running Trivy security scan...${NC}"

    TRIVY_REPORT="$REPORTS_DIR/trivy-$TIMESTAMP.json"

    # Scan filesystem
    trivy fs . \
        --format json \
        --output "$TRIVY_REPORT" \
        --severity HIGH,CRITICAL \
        --scanners vuln,config,secret \
        || true

    # Parse results
    if [ -f "$TRIVY_REPORT" ]; then
        CRITICAL=$(cat "$TRIVY_REPORT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "CRITICAL")] | length' 2>/dev/null || echo "0")
        HIGH=$(cat "$TRIVY_REPORT" | jq '[.Results[]?.Vulnerabilities[]? | select(.Severity == "HIGH")] | length' 2>/dev/null || echo "0")

        ISSUES_CRITICAL=$((ISSUES_CRITICAL + CRITICAL))
        ISSUES_HIGH=$((ISSUES_HIGH + HIGH))

        echo -e "${GREEN}✅ Trivy scan complete${NC}"
        echo -e "   Critical: $CRITICAL issues"
        echo -e "   High:     $HIGH issues"
        echo -e "   Report: $TRIVY_REPORT"
    fi
}

# Function to run Semgrep scan
run_semgrep() {
    if ! command -v semgrep &> /dev/null; then
        return
    fi

    echo -e "${BLUE}🔎 Running Semgrep static analysis...${NC}"

    SEMGREP_REPORT="$REPORTS_DIR/semgrep-$TIMESTAMP.json"

    # Run Semgrep with auto config (detects language automatically)
    semgrep --config=auto \
        --json \
        --output="$SEMGREP_REPORT" \
        app/ \
        || true

    # Parse results
    if [ -f "$SEMGREP_REPORT" ]; then
        HIGH=$(cat "$SEMGREP_REPORT" | jq '[.results[] | select(.extra.severity == "ERROR")] | length' 2>/dev/null || echo "0")
        MEDIUM=$(cat "$SEMGREP_REPORT" | jq '[.results[] | select(.extra.severity == "WARNING")] | length' 2>/dev/null || echo "0")

        ISSUES_HIGH=$((ISSUES_HIGH + HIGH))
        ISSUES_MEDIUM=$((ISSUES_MEDIUM + MEDIUM))

        echo -e "${GREEN}✅ Semgrep scan complete${NC}"
        echo -e "   Errors:   $HIGH issues"
        echo -e "   Warnings: $MEDIUM issues"
        echo -e "   Report: $SEMGREP_REPORT"
    fi
}

# Function to check for hardcoded secrets
check_secrets() {
    echo -e "${BLUE}🔐 Checking for hardcoded secrets...${NC}"

    # Common secret patterns
    PATTERNS=(
        "password\s*=\s*['\"][^'\"]{8,}"
        "api[_-]?key\s*=\s*['\"][^'\"]{16,}"
        "secret[_-]?key\s*=\s*['\"][^'\"]{16,}"
        "token\s*=\s*['\"][^'\"]{16,}"
        "aws[_-]?access[_-]?key"
        "-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----"
    )

    SECRETS_FOUND=0

    for pattern in "${PATTERNS[@]}"; do
        MATCHES=$(grep -r -i -E "$pattern" app/ 2>/dev/null | grep -v ".pyc" | wc -l)
        SECRETS_FOUND=$((SECRETS_FOUND + MATCHES))
    done

    if [ "$SECRETS_FOUND" -gt 0 ]; then
        echo -e "${RED}❌ Found $SECRETS_FOUND potential hardcoded secrets${NC}"
        ISSUES_HIGH=$((ISSUES_HIGH + SECRETS_FOUND))
    else
        echo -e "${GREEN}✅ No hardcoded secrets detected${NC}"
    fi
}

# Function to check file permissions
check_permissions() {
    echo -e "${BLUE}📂 Checking file permissions...${NC}"

    # Check for files with overly permissive permissions
    INSECURE_FILES=$(find app/ -type f -perm -o+w 2>/dev/null | wc -l)

    if [ "$INSECURE_FILES" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Found $INSECURE_FILES files with world-writable permissions${NC}"
        ISSUES_MEDIUM=$((ISSUES_MEDIUM + INSECURE_FILES))
    else
        echo -e "${GREEN}✅ File permissions are appropriate${NC}"
    fi
}

# Function to check Docker security
check_docker_security() {
    echo -e "${BLUE}🐳 Checking Docker security...${NC}"

    if [ ! -f "docker-compose.yml" ]; then
        echo -e "${YELLOW}⚠️  docker-compose.yml not found${NC}"
        return
    fi

    # Check for running as root
    if grep -q "user: root" docker-compose.yml; then
        echo -e "${YELLOW}⚠️  Containers running as root detected${NC}"
        ISSUES_MEDIUM=$((ISSUES_MEDIUM + 1))
    fi

    # Check for privileged mode
    if grep -q "privileged: true" docker-compose.yml; then
        echo -e "${RED}❌ Privileged containers detected${NC}"
        ISSUES_HIGH=$((ISSUES_HIGH + 1))
    fi

    # Check for host network mode
    if grep -q "network_mode: host" docker-compose.yml; then
        echo -e "${YELLOW}⚠️  Host network mode detected${NC}"
        ISSUES_MEDIUM=$((ISSUES_MEDIUM + 1))
    fi

    echo -e "${GREEN}✅ Docker security check complete${NC}"
}

# Function to generate summary report
generate_summary() {
    SUMMARY_FILE="$REPORTS_DIR/security-summary-$TIMESTAMP.txt"

    cat > "$SUMMARY_FILE" <<EOF
═══════════════════════════════════════════════════
   Ablage-System OCR - Security Scan Summary
═══════════════════════════════════════════════════

Scan Date: $(date)

ISSUES BY SEVERITY:
  🔴 Critical: $ISSUES_CRITICAL
  🟠 High:     $ISSUES_HIGH
  🟡 Medium:   $ISSUES_MEDIUM
  ⚪ Low:      $ISSUES_LOW

TOTAL ISSUES: $((ISSUES_CRITICAL + ISSUES_HIGH + ISSUES_MEDIUM + ISSUES_LOW))

RISK ASSESSMENT:
EOF

    TOTAL_ISSUES=$((ISSUES_CRITICAL + ISSUES_HIGH + ISSUES_MEDIUM + ISSUES_LOW))

    if [ "$ISSUES_CRITICAL" -gt 0 ]; then
        echo "  ❌ CRITICAL: Immediate action required!" >> "$SUMMARY_FILE"
    elif [ "$ISSUES_HIGH" -gt 10 ]; then
        echo "  ⚠️  HIGH RISK: Address issues before deployment" >> "$SUMMARY_FILE"
    elif [ "$ISSUES_HIGH" -gt 0 ] || [ "$ISSUES_MEDIUM" -gt 20 ]; then
        echo "  ⚠️  MODERATE RISK: Review and remediate" >> "$SUMMARY_FILE"
    elif [ "$TOTAL_ISSUES" -gt 0 ]; then
        echo "  ✅ LOW RISK: Minor issues to address" >> "$SUMMARY_FILE"
    else
        echo "  ✅ NO ISSUES: Security posture is good" >> "$SUMMARY_FILE"
    fi

    cat >> "$SUMMARY_FILE" <<EOF

REPORTS GENERATED:
EOF

    ls -1 "$REPORTS_DIR"/*-$TIMESTAMP.* >> "$SUMMARY_FILE" 2>/dev/null || true

    cat >> "$SUMMARY_FILE" <<EOF

RECOMMENDATIONS:
  1. Review all CRITICAL and HIGH severity issues immediately
  2. Update vulnerable dependencies (run: pip install -U -r requirements.txt)
  3. Rotate any exposed secrets or credentials
  4. Implement recommended security patches
  5. Run security scans regularly (at least weekly)
  6. Integrate security scanning into CI/CD pipeline

NEXT STEPS:
  • View detailed reports: ls $REPORTS_DIR/
  • Fix vulnerabilities: Review individual reports
  • Re-run scan: ./scripts/security-scan.sh
  • Update dependencies: make update-deps

═══════════════════════════════════════════════════
EOF

    echo -e "${GREEN}✅ Summary report: $SUMMARY_FILE${NC}"
}

# Function to display results
display_results() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Security Scan Complete! 🔒${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}📊 Issues by Severity:${NC}"
    echo -e "   ${RED}🔴 Critical: $ISSUES_CRITICAL${NC}"
    echo -e "   ${YELLOW}🟠 High:     $ISSUES_HIGH${NC}"
    echo -e "   ${YELLOW}🟡 Medium:   $ISSUES_MEDIUM${NC}"
    echo -e "   ${GREEN}⚪ Low:      $ISSUES_LOW${NC}"
    echo ""

    TOTAL=$((ISSUES_CRITICAL + ISSUES_HIGH + ISSUES_MEDIUM + ISSUES_LOW))
    echo -e "${BLUE}Total Issues: $TOTAL${NC}"
    echo ""

    if [ "$ISSUES_CRITICAL" -gt 0 ]; then
        echo -e "${RED}❌ CRITICAL ISSUES FOUND - DO NOT DEPLOY!${NC}"
    elif [ "$ISSUES_HIGH" -gt 10 ]; then
        echo -e "${YELLOW}⚠️  HIGH RISK - Address before deployment${NC}"
    elif [ "$TOTAL" -eq 0 ]; then
        echo -e "${GREEN}✅ No security issues detected!${NC}"
    else
        echo -e "${GREEN}✅ Security posture is acceptable${NC}"
    fi

    echo ""
    echo -e "${BLUE}📁 Reports saved in: $REPORTS_DIR${NC}"
    echo ""
}

# Main script
main() {
    echo -e "${BLUE}🔒 Security Scanning Script${NC}"
    echo -e "${BLUE}═══════════════════════════${NC}"
    echo ""

    check_dependencies
    echo ""

    run_bandit
    echo ""

    run_safety
    echo ""

    run_trivy
    echo ""

    run_semgrep
    echo ""

    check_secrets
    echo ""

    check_permissions
    echo ""

    check_docker_security
    echo ""

    generate_summary
    display_results

    # Exit with error if critical issues found
    if [ "$ISSUES_CRITICAL" -gt 0 ]; then
        exit 1
    fi
}

# Run main function
main
