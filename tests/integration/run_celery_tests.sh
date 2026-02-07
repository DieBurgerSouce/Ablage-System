#!/bin/bash
# Celery Integration Tests Runner
# Usage: ./run_celery_tests.sh [category]

set -e

echo "=========================================="
echo "Celery Integration Tests"
echo "=========================================="
echo ""

if [ -z "$1" ]; then
    echo "Running ALL Celery integration tests..."
    pytest tests/integration/test_email_import_pipeline.py \
           tests/integration/test_folder_watcher.py \
           tests/integration/test_datev_token.py \
           tests/integration/test_risk_scoring.py \
           tests/integration/test_lineage_ordering.py \
           tests/integration/test_shipment_tracking.py \
           tests/integration/test_skonto_pipeline.py \
           tests/integration/test_dlq_management.py \
           -v --tb=short
else
    case "$1" in
        email)
            echo "Running Email Import tests..."
            pytest tests/integration/test_email_import_pipeline.py -v
            ;;
        folder)
            echo "Running Folder Watcher tests..."
            pytest tests/integration/test_folder_watcher.py -v
            ;;
        datev)
            echo "Running DATEV Token tests..."
            pytest tests/integration/test_datev_token.py -v
            ;;
        risk)
            echo "Running Risk Scoring tests..."
            pytest tests/integration/test_risk_scoring.py -v
            ;;
        lineage)
            echo "Running Lineage Event tests..."
            pytest tests/integration/test_lineage_ordering.py -v
            ;;
        shipment)
            echo "Running Shipment Tracking tests..."
            pytest tests/integration/test_shipment_tracking.py -v
            ;;
        skonto)
            echo "Running Skonto Pipeline tests..."
            pytest tests/integration/test_skonto_pipeline.py -v
            ;;
        dlq)
            echo "Running DLQ Management tests..."
            pytest tests/integration/test_dlq_management.py -v
            ;;
        *)
            echo "Unknown category: $1"
            echo "Available: email, folder, datev, risk, lineage, shipment, skonto, dlq"
            exit 1
            ;;
    esac
fi

echo ""
echo "=========================================="
echo "Tests completed!"
echo "=========================================="
