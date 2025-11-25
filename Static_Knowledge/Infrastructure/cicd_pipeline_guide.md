# CI/CD Pipeline Guide
**Ablage-System - Kontinuierliche Integration und Bereitstellung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Status: PRODUCTION

---

## Executive Summary

Complete CI/CD pipeline guide for Ablage-System, covering automated testing, building, deployment, and monitoring using GitHub Actions and GitLab CI/CD.

**Pipeline Metrics:**
- ✅ Build Time: <10 minutes
- ✅ Test Coverage: ≥80%
- ✅ Deployment Frequency: Multiple times per day
- ✅ Mean Time to Recovery (MTTR): <30 minutes

---

## Table of Contents

1. [Pipeline Architecture](#pipeline-architecture)
2. [GitHub Actions Pipelines](#github-actions-pipelines)
3. [GitLab CI/CD Pipelines](#gitlab-cicd-pipelines)
4. [Build Strategies](#build-strategies)
5. [Testing Automation](#testing-automation)
6. [Deployment Strategies](#deployment-strategies)
7. [Monitoring & Alerting](#monitoring--alerting)

---

## Pipeline Architecture

### CI/CD Flow

```
Developer Push
       ↓
   Git Trigger
       ↓
   ┌─────────────────┐
   │  CI Pipeline    │
   ├─────────────────┤
   │ 1. Lint         │
   │ 2. Test         │
   │ 3. Build        │
   │ 4. Scan         │
   └─────────────────┘
       ↓
   Artifacts Ready
       ↓
   ┌─────────────────┐
   │  CD Pipeline    │
   ├─────────────────┤
   │ 1. Deploy Dev   │
   │ 2. Test Dev     │
   │ 3. Deploy Stag  │
   │ 4. Test Staging │
   │ 5. Approve Prod │
   │ 6. Deploy Prod  │
   └─────────────────┘
       ↓
   Production Release
       ↓
   Monitoring & Alerts
```

### Pipeline Stages

**Continuous Integration (CI):**
1. **Code Quality:** Lint, format check, type checking
2. **Testing:** Unit, integration, security tests
3. **Building:** Docker images, documentation
4. **Scanning:** Vulnerability scans, code analysis

**Continuous Deployment (CD):**
1. **Deploy to Dev:** Automated deployment
2. **Deploy to Staging:** After dev validation
3. **Deploy to Production:** Manual approval required
4. **Post-Deployment:** Smoke tests, monitoring

---

## GitHub Actions Pipelines

### Complete CI/CD Workflow

```yaml
# .github/workflows/ci-cd.yml

name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  release:
    types: [published]

env:
  DOCKER_REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ============================================================================
  # Job 1: Code Quality
  # ============================================================================
  code-quality:
    name: Code Quality Checks
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Cache dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint with Ruff
        run: ruff check .

      - name: Type check with mypy
        run: mypy app/

      - name: Security check with Bandit
        run: bandit -r app/ -f json -o bandit-report.json

      - name: Upload security report
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: bandit-report
          path: bandit-report.json

  # ============================================================================
  # Job 2: Unit Tests
  # ============================================================================
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: code-quality

    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          pytest tests/unit/ \
            --cov=app \
            --cov-report=xml \
            --cov-report=term \
            --junitxml=junit.xml \
            -v

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: unittests
          name: codecov-${{ matrix.python-version }}

      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        if: always()
        with:
          files: junit.xml

  # ============================================================================
  # Job 3: Integration Tests
  # ============================================================================
  integration-tests:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: unit-tests

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: ablage_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run database migrations
        run: alembic upgrade head
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/ablage_test

      - name: Run integration tests
        run: |
          pytest tests/integration/ \
            -v \
            --tb=short
        env:
          DATABASE_URL: postgresql://postgres:test@localhost:5432/ablage_test
          REDIS_URL: redis://localhost:6379

  # ============================================================================
  # Job 4: Build Docker Images
  # ============================================================================
  build:
    name: Build Docker Images
    runs-on: ubuntu-latest
    needs: [unit-tests, integration-tests]
    if: github.event_name == 'push'

    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.DOCKER_REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - name: Build and push backend image
        uses: docker/build-push-action@v4
        with:
          context: .
          file: docker/Dockerfile.backend
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push worker image
        uses: docker/build-push-action@v4
        with:
          context: .
          file: docker/Dockerfile.worker
          push: true
          tags: ${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}/worker:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ============================================================================
  # Job 5: Security Scanning
  # ============================================================================
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    needs: build

    steps:
      - uses: actions/checkout@v3

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.DOCKER_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'

      - name: Dependency scanning
        run: |
          pip install pip-audit
          pip-audit --format json --output pip-audit-report.json

      - name: Upload dependency scan results
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            trivy-results.sarif
            pip-audit-report.json

  # ============================================================================
  # Job 6: Deploy to Development
  # ============================================================================
  deploy-dev:
    name: Deploy to Development
    runs-on: ubuntu-latest
    needs: [build, security-scan]
    if: github.ref == 'refs/heads/develop'
    environment:
      name: development
      url: https://dev.ablage.local

    steps:
      - uses: actions/checkout@v3

      - name: Deploy to development server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DEV_SERVER_HOST }}
          username: ${{ secrets.DEV_SERVER_USER }}
          key: ${{ secrets.DEV_SERVER_SSH_KEY }}
          script: |
            cd /opt/ablage
            docker-compose pull
            docker-compose up -d
            docker-compose exec -T backend alembic upgrade head

      - name: Run smoke tests
        run: |
          sleep 10
          curl -f https://dev.ablage.local/health || exit 1

  # ============================================================================
  # Job 7: Deploy to Production
  # ============================================================================
  deploy-prod:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: build
    if: github.event_name == 'release'
    environment:
      name: production
      url: https://ablage.local

    steps:
      - uses: actions/checkout@v3

      - name: Deploy to production
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.PROD_SERVER_HOST }}
          username: ${{ secrets.PROD_SERVER_USER }}
          key: ${{ secrets.PROD_SERVER_SSH_KEY }}
          script: |
            cd /opt/ablage
            ./deploy.sh ${{ github.event.release.tag_name }}

      - name: Verify deployment
        run: |
          sleep 30
          curl -f https://ablage.local/health || exit 1

      - name: Notify team
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Production deployment completed: ${{ github.event.release.tag_name }}'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## GitLab CI/CD Pipelines

### .gitlab-ci.yml

```yaml
# .gitlab-ci.yml

stages:
  - quality
  - test
  - build
  - scan
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"
  PYTHON_VERSION: "3.11"

# ============================================================================
# Templates
# ============================================================================
.python_template: &python_template
  image: python:${PYTHON_VERSION}
  before_script:
    - pip install -r requirements.txt
    - pip install -r requirements-dev.txt

.docker_template: &docker_template
  image: docker:24.0
  services:
    - docker:24.0-dind

# ============================================================================
# Stage: Quality
# ============================================================================
lint:
  <<: *python_template
  stage: quality
  script:
    - ruff check .
  allow_failure: false

type-check:
  <<: *python_template
  stage: quality
  script:
    - mypy app/
  allow_failure: false

security-check:
  <<: *python_template
  stage: quality
  script:
    - bandit -r app/ -f json -o bandit-report.json
  artifacts:
    reports:
      json: bandit-report.json
  allow_failure: true

# ============================================================================
# Stage: Test
# ============================================================================
unit-tests:
  <<: *python_template
  stage: test
  script:
    - pytest tests/unit/ --cov=app --cov-report=xml --cov-report=term
  coverage: '/TOTAL.*\s+(\d+%)$/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml

integration-tests:
  <<: *python_template
  stage: test
  services:
    - name: postgres:16
      alias: postgres
    - name: redis:7
      alias: redis
  variables:
    POSTGRES_DB: ablage_test
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: test
    DATABASE_URL: "postgresql://postgres:test@postgres:5432/ablage_test"
    REDIS_URL: "redis://redis:6379"
  script:
    - alembic upgrade head
    - pytest tests/integration/ -v
  needs: [unit-tests]

# ============================================================================
# Stage: Build
# ============================================================================
build-backend:
  <<: *docker_template
  stage: build
  script:
    - docker build -f docker/Dockerfile.backend -t $CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA
  only:
    - main
    - develop
  needs: [unit-tests, integration-tests]

build-worker:
  <<: *docker_template
  stage: build
  script:
    - docker build -f docker/Dockerfile.worker -t $CI_REGISTRY_IMAGE/worker:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE/worker:$CI_COMMIT_SHA
  only:
    - main
    - develop
  needs: [unit-tests, integration-tests]

# ============================================================================
# Stage: Scan
# ============================================================================
trivy-scan:
  <<: *docker_template
  stage: scan
  script:
    - apk add --no-cache curl
    - curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin
    - trivy image --severity HIGH,CRITICAL $CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA
  allow_failure: true
  needs: [build-backend]

# ============================================================================
# Stage: Deploy
# ============================================================================
deploy-dev:
  stage: deploy
  environment:
    name: development
    url: https://dev.ablage.local
  script:
    - apt-get update && apt-get install -y openssh-client
    - eval $(ssh-agent -s)
    - echo "$DEV_SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
    - mkdir -p ~/.ssh
    - chmod 700 ~/.ssh
    - ssh -o StrictHostKeyChecking=no $DEV_SERVER_USER@$DEV_SERVER_HOST "cd /opt/ablage && docker-compose pull && docker-compose up -d"
  only:
    - develop
  needs: [build-backend, build-worker]

deploy-staging:
  stage: deploy
  environment:
    name: staging
    url: https://staging.ablage.local
  script:
    - apt-get update && apt-get install -y openssh-client
    - eval $(ssh-agent -s)
    - echo "$STAGING_SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
    - ssh -o StrictHostKeyChecking=no $STAGING_SERVER_USER@$STAGING_SERVER_HOST "cd /opt/ablage && docker-compose pull && docker-compose up -d"
  when: manual
  only:
    - main
  needs: [build-backend, build-worker, trivy-scan]

deploy-production:
  stage: deploy
  environment:
    name: production
    url: https://ablage.local
  script:
    - apt-get update && apt-get install -y openssh-client
    - eval $(ssh-agent -s)
    - echo "$PROD_SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -
    - ssh -o StrictHostKeyChecking=no $PROD_SERVER_USER@$PROD_SERVER_HOST "cd /opt/ablage && ./deploy.sh $CI_COMMIT_TAG"
  when: manual
  only:
    - tags
  needs: [build-backend, build-worker, trivy-scan]
```

---

## Build Strategies

### Multi-Stage Docker Builds

```yaml
# Parallel build jobs
build-images:
  parallel:
    matrix:
      - SERVICE: [backend, worker, frontend]
  script:
    - docker build -f docker/Dockerfile.$SERVICE -t $IMAGE:$TAG .
```

### Caching Strategy

```yaml
# GitHub Actions cache
- name: Cache Docker layers
  uses: actions/cache@v3
  with:
    path: /tmp/.buildx-cache
    key: ${{ runner.os }}-buildx-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-buildx-
```

---

## Testing Automation

### Test Matrix

```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12']
    os: [ubuntu-latest, macos-latest]
    include:
      - python-version: '3.11'
        experimental: false
      - python-version: '3.12'
        experimental: true
  fail-fast: false

steps:
  - name: Run tests
    run: pytest
    continue-on-error: ${{ matrix.experimental }}
```

### GPU Testing

```yaml
# Self-hosted runner with GPU
gpu-tests:
  runs-on: [self-hosted, gpu]
  steps:
    - name: Check GPU
      run: nvidia-smi

    - name: Run GPU tests
      run: pytest tests/ -m gpu
```

---

## Deployment Strategies

### Blue-Green Deployment

```yaml
deploy-blue-green:
  steps:
    - name: Deploy to green
      run: |
        kubectl set image deployment/ablage ablage=ablage:$VERSION -n green
        kubectl rollout status deployment/ablage -n green

    - name: Run smoke tests on green
      run: ./smoke-tests.sh green

    - name: Switch traffic to green
      run: kubectl patch service ablage -p '{"spec":{"selector":{"version":"green"}}}'

    - name: Monitor for 5 minutes
      run: sleep 300

    - name: Rollback if needed
      if: failure()
      run: kubectl patch service ablage -p '{"spec":{"selector":{"version":"blue"}}}'
```

### Canary Deployment

```yaml
deploy-canary:
  steps:
    - name: Deploy canary (10% traffic)
      run: |
        kubectl apply -f k8s/canary-10.yaml
        sleep 300  # Monitor for 5 minutes

    - name: Increase to 50%
      run: kubectl apply -f k8s/canary-50.yaml

    - name: Full rollout (100%)
      run: kubectl apply -f k8s/canary-100.yaml
```

---

## Monitoring & Alerting

### Post-Deployment Checks

```yaml
post-deploy-checks:
  steps:
    - name: Health check
      run: |
        curl -f https://ablage.local/health || exit 1

    - name: Check metrics
      run: |
        python scripts/check_metrics.py \
          --threshold-error-rate 1 \
          --threshold-latency-p95 500

    - name: Alert on failure
      if: failure()
      uses: 8398a7/action-slack@v3
      with:
        status: failure
        text: 'Deployment health checks failed!'
        webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

### Performance Monitoring

```yaml
performance-check:
  steps:
    - name: Run load test
      run: locust -f tests/performance/locustfile.py --headless -u 100 -r 10 --run-time 5m

    - name: Check response times
      run: |
        p95=$(cat locust_stats.json | jq '.p95')
        if [ $p95 -gt 500 ]; then
          echo "P95 latency too high: ${p95}ms"
          exit 1
        fi
```

---

## Related Documents

- [Docker Containerization Guide](docker_containerization_guide.md)
- [Terraform Infrastructure Guide](terraform_infrastructure_guide.md)
- [Testing Strategy](../Testing/comprehensive_testing_strategy.md)
- [Deployment Checklist](../../Execution_Layer/Checklists/pre_deployment_checklist.md)

---

## Revision History

| Version | Date       | Author      | Changes                    |
|---------|------------|-------------|----------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial CI/CD pipeline guide |

---

**"Automate everything that can be automated, test everything that can be tested."**

🚀 **CI/CD Excellence Achieved!**
