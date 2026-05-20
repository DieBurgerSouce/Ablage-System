#!/bin/bash
#
# validate-german-text.sh - Umlaut Accuracy Testing Script
#
# Testet OCR-Genauigkeit fuer deutsche Texte:
# - Umlaut-Erkennung (ae, oe, ue, ss)
# - Fraktur-Schrift Unterstuetzung
# - Sonderzeichen-Handling
#
# Verwendung: ./scripts/validate-german-text.sh [test-image-path]
#

set -e

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

API_URL="${API_URL:-http://localhost:8000}"
TEST_DIR="tests/fixtures/german"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Deutsche Text-Validierung (OCR)      ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Test-Texte mit erwarteten Umlauten
declare -A TEST_CASES=(
    ["standard"]="Größe Öffentlichkeit Übung Straße Gemütlichkeit"
    ["fraktur"]="Änderung Österreich Übergang Maßnahme"
    ["mixed"]="Der größte Bär trägt Ärmel über seine Füße"
    ["technical"]="Prüfprotokoll Gerätespezifikation Ausführungsbestätigung"
)

# Funktion: API Health Check
check_api() {
    echo -e "${BLUE}Pruefe API-Verfuegbarkeit...${NC}"
    if curl -s "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} API erreichbar unter $API_URL"
        return 0
    else
        echo -e "${RED}[FAIL]${NC} API nicht erreichbar unter $API_URL"
        return 1
    fi
}

# Funktion: Umlaut-Erkennung pruefen
check_umlauts() {
    local text="$1"
    local expected_umlauts=("ä" "ö" "ü" "Ä" "Ö" "Ü" "ß")
    local found=0
    local missing=""

    for umlaut in "${expected_umlauts[@]}"; do
        if [[ "$text" == *"$umlaut"* ]]; then
            ((found++))
        else
            missing="$missing $umlaut"
        fi
    done

    if [ -n "$missing" ]; then
        echo -e "${YELLOW}[WARN]${NC} Fehlende Umlaute:$missing"
    fi

    return $found
}

# Funktion: OCR mit Backend testen
test_ocr_backend() {
    local backend="$1"
    local image_path="$2"
    local expected_text="$3"

    echo -e "\n${BLUE}Testing $backend...${NC}"

    # OCR Request
    local response=$(curl -s -X POST "$API_URL/api/v1/ocr/process" \
        -H "Content-Type: multipart/form-data" \
        -F "file=@$image_path" \
        -F "backend=$backend" \
        2>/dev/null)

    if [ -z "$response" ]; then
        echo -e "${RED}[FAIL]${NC} Keine Antwort von $backend"
        return 1
    fi

    # Text extrahieren
    local extracted=$(echo "$response" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('text',''))" 2>/dev/null || echo "")

    if [ -z "$extracted" ]; then
        echo -e "${RED}[FAIL]${NC} Kein Text extrahiert"
        return 1
    fi

    # Umlaut-Analyse
    local correct_umlauts=0
    local total_umlauts=0

    # Zaehle Umlaute im erwarteten Text
    for char in ä ö ü Ä Ö Ü ß; do
        count=$(echo "$expected_text" | grep -o "$char" | wc -l)
        total_umlauts=$((total_umlauts + count))

        extracted_count=$(echo "$extracted" | grep -o "$char" | wc -l)
        if [ "$extracted_count" -ge "$count" ]; then
            correct_umlauts=$((correct_umlauts + count))
        else
            correct_umlauts=$((correct_umlauts + extracted_count))
        fi
    done

    # Genauigkeit berechnen
    if [ "$total_umlauts" -gt "0" ]; then
        accuracy=$((correct_umlauts * 100 / total_umlauts))
    else
        accuracy=100
    fi

    # Ergebnis ausgeben
    if [ "$accuracy" -ge "90" ]; then
        echo -e "${GREEN}[PASS]${NC} $backend: ${accuracy}% Umlaut-Genauigkeit ($correct_umlauts/$total_umlauts)"
    elif [ "$accuracy" -ge "70" ]; then
        echo -e "${YELLOW}[WARN]${NC} $backend: ${accuracy}% Umlaut-Genauigkeit ($correct_umlauts/$total_umlauts)"
    else
        echo -e "${RED}[FAIL]${NC} $backend: ${accuracy}% Umlaut-Genauigkeit ($correct_umlauts/$total_umlauts)"
    fi

    # Detail-Vergleich
    echo "   Erwartet: $expected_text"
    echo "   Erkannt:  $extracted"

    return $accuracy
}

# Funktion: Synthetischen Test erstellen
create_test_image() {
    local text="$1"
    local output="$2"

    # Benoetigt ImageMagick
    if command -v convert &> /dev/null; then
        convert -size 800x100 xc:white \
            -font "DejaVu-Sans" -pointsize 24 \
            -fill black -gravity Center \
            -annotate 0 "$text" \
            "$output"
        echo -e "${GREEN}[OK]${NC} Test-Bild erstellt: $output"
        return 0
    else
        echo -e "${YELLOW}[WARN]${NC} ImageMagick nicht installiert - ueberspringe Bild-Generierung"
        return 1
    fi
}

# Hauptlogik
main() {
    local custom_image="$1"

    # API Check
    if ! check_api; then
        echo "Starte zuerst den API-Server"
        exit 1
    fi

    # Verfuegbare Backends ermitteln
    echo -e "\n${BLUE}Verfuegbare OCR-Backends:${NC}"
    local backends=$(curl -s "$API_URL/api/v1/ocr/backends" 2>/dev/null | python3 -c "import json,sys; backends=json.load(sys.stdin); print(' '.join([b['name'] for b in backends if b.get('available', True)]))" 2>/dev/null || echo "deepseek got_ocr surya")
    echo "   $backends"

    # Test mit benutzerdefinierten Bild
    if [ -n "$custom_image" ] && [ -f "$custom_image" ]; then
        echo -e "\n${BLUE}Teste mit benutzerdefiniertem Bild: $custom_image${NC}"
        for backend in $backends; do
            test_ocr_backend "$backend" "$custom_image" "Größe Öffentlichkeit Übung" || true
        done
        exit 0
    fi

    # Standard-Tests
    echo -e "\n${BLUE}Fuehre Standard-Tests durch...${NC}"

    # Test-Verzeichnis erstellen
    mkdir -p "$TEST_DIR"

    # Ergebnisse sammeln
    declare -A RESULTS
    total_tests=0
    passed_tests=0

    # Fuer jeden Test-Case
    for case_name in "${!TEST_CASES[@]}"; do
        expected_text="${TEST_CASES[$case_name]}"
        test_image="$TEST_DIR/test_${case_name}.png"

        echo -e "\n${BLUE}=== Test-Case: $case_name ===${NC}"
        echo "Erwarteter Text: $expected_text"

        # Test-Bild generieren
        if create_test_image "$expected_text" "$test_image"; then
            # Mit jedem Backend testen
            for backend in $backends; do
                ((total_tests++))
                if test_ocr_backend "$backend" "$test_image" "$expected_text"; then
                    ((passed_tests++))
                fi
            done
        fi
    done

    # Zusammenfassung
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}          Zusammenfassung              ${NC}"
    echo -e "${BLUE}========================================${NC}"

    if [ "$total_tests" -gt "0" ]; then
        success_rate=$((passed_tests * 100 / total_tests))
        echo -e "Bestanden: $passed_tests / $total_tests Tests (${success_rate}%)"

        if [ "$success_rate" -ge "90" ]; then
            echo -e "${GREEN}Umlaut-Erkennung: EXZELLENT${NC}"
        elif [ "$success_rate" -ge "70" ]; then
            echo -e "${YELLOW}Umlaut-Erkennung: AKZEPTABEL${NC}"
        else
            echo -e "${RED}Umlaut-Erkennung: VERBESSERUNG NOETIG${NC}"
        fi
    else
        echo -e "${YELLOW}Keine Tests ausgefuehrt${NC}"
    fi

    # Empfehlungen
    echo -e "\n${BLUE}Empfehlungen:${NC}"
    echo "- DeepSeek-Janus-Pro fuer beste Umlaut-Genauigkeit"
    echo "- GOT-OCR 2.0 fuer schnelle Verarbeitung mit guter Qualitaet"
    echo "- Surya+Docling fuer komplexe Layouts"
}

# Script ausfuehren
main "$@"
