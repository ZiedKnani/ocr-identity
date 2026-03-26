#!/bin/bash

# test-docker.sh - Script de test pour OCR Identity Extractor V2

set -e

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test OCR Identity Extractor V2 - Docker${NC}"
echo -e "${GREEN}========================================${NC}\n"

# Variables
API_URL="http://localhost:8000"
RETRY_COUNT=30
RETRY_DELAY=2

# Fonction pour attendre que l'API soit prête
wait_for_api() {
    echo -e "${YELLOW}⏳ Attente du démarrage de l'API...${NC}"
    
    for i in $(seq 1 $RETRY_COUNT); do
        if curl -s "$API_URL/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ API prête !${NC}\n"
            return 0
        fi
        
        echo -ne "${YELLOW}Tentative $i/$RETRY_COUNT...${NC}\r"
        sleep $RETRY_DELAY
    done
    
    echo -e "${RED}❌ Timeout : L'API n'a pas démarré${NC}"
    return 1
}

# Fonction de test
run_test() {
    local test_name=$1
    local command=$2
    local expected=$3
    
    echo -e "${YELLOW}🧪 Test: $test_name${NC}"
    
    result=$(eval "$command")
    
    if echo "$result" | grep -q "$expected"; then
        echo -e "${GREEN}✅ PASS${NC}\n"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        echo "Attendu: $expected"
        echo "Reçu: $result"
        echo ""
        return 1
    fi
}

# Compteur de tests
TOTAL_TESTS=0
PASSED_TESTS=0

# Attendre que l'API soit prête
if ! wait_for_api; then
    echo -e "${RED}❌ Les tests ne peuvent pas continuer${NC}"
    exit 1
fi

# Test 1: Health Check
((TOTAL_TESTS++))
if run_test "Health Check" \
    "curl -s $API_URL/health | jq -r '.status'" \
    "healthy"; then
    ((PASSED_TESTS++))
fi

# Test 2: Root endpoint
((TOTAL_TESTS++))
if run_test "Root Endpoint" \
    "curl -s $API_URL/ | jq -r '.service'" \
    "OCR Identity Extractor V2"; then
    ((PASSED_TESTS++))
fi

# Test 3: Supported types
((TOTAL_TESTS++))
if run_test "Supported Types" \
    "curl -s $API_URL/supported-types | jq -r '.success'" \
    "true"; then
    ((PASSED_TESTS++))
fi

# Test 4: Check version
((TOTAL_TESTS++))
if run_test "API Version" \
    "curl -s $API_URL/ | jq -r '.version'" \
    "2.0.0"; then
    ((PASSED_TESTS++))
fi

# Test 5: Docker container status
((TOTAL_TESTS++))
echo -e "${YELLOW}🧪 Test: Docker Container Status${NC}"
if docker ps | grep -q "ocr-identity-api"; then
    echo -e "${GREEN}✅ PASS${NC}\n"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ FAIL - Conteneur non démarré${NC}\n"
fi

# Test 6: Container health
((TOTAL_TESTS++))
echo -e "${YELLOW}🧪 Test: Container Health${NC}"
health_status=$(docker inspect --format='{{.State.Health.Status}}' ocr-identity-api 2>/dev/null || echo "unknown")
if [ "$health_status" = "healthy" ]; then
    echo -e "${GREEN}✅ PASS${NC}\n"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ FAIL - Status: $health_status${NC}\n"
fi

# Test 7: Volume exists
((TOTAL_TESTS++))
echo -e "${YELLOW}🧪 Test: Volume Paddle Models${NC}"
if docker volume ls | grep -q "ocr-paddle-models"; then
    echo -e "${GREEN}✅ PASS${NC}\n"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ FAIL - Volume non trouvé${NC}\n"
fi

# Test 8: Network exists
((TOTAL_TESTS++))
echo -e "${YELLOW}🧪 Test: Docker Network${NC}"
if docker network ls | grep -q "ocr-network"; then
    echo -e "${GREEN}✅ PASS${NC}\n"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ FAIL - Network non trouvé${NC}\n"
fi

# Test 9: Test upload (optionnel - nécessite une image de test)
if [ -f "./test_images/test.jpg" ]; then
    ((TOTAL_TESTS++))
    echo -e "${YELLOW}🧪 Test: Upload Document${NC}"
    upload_result=$(curl -s -X POST "$API_URL/ocr-only" \
        -F "file=@./test_images/test.jpg" | jq -r '.success')
    
    if [ "$upload_result" = "true" ]; then
        echo -e "${GREEN}✅ PASS${NC}\n"
        ((PASSED_TESTS++))
    else
        echo -e "${RED}❌ FAIL${NC}\n"
    fi
fi

# Résumé
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Résumé des Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Total: $TOTAL_TESTS tests"
echo -e "${GREEN}Réussis: $PASSED_TESTS${NC}"
echo -e "${RED}Échoués: $((TOTAL_TESTS - PASSED_TESTS))${NC}"

if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
    echo -e "\n${GREEN}🎉 Tous les tests sont passés !${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Certains tests ont échoué${NC}"
    exit 1
fi
