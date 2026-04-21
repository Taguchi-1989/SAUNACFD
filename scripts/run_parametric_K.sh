#!/bin/bash
# Run parametric K cases (both-side fixedValue vent control)
set -e
source /usr/lib/openfoam/openfoam2312/etc/bashrc 2>/dev/null || true
export FOAM_SIGFPE=false

BASE="/mnt/d/dev/SaunaFEM"

run_case() {
    local SRC="$1"
    local LABEL="$2"
    local CASE_NAME=$(basename "$SRC")
    local CASE="$HOME/saunaflow_run/$CASE_NAME"

    echo "============================================"
    echo "=== $LABEL ==="
    echo "============================================"

    rm -rf "$CASE"
    mkdir -p "$(dirname "$CASE")"
    cp -r "$SRC" "$CASE"
    cd "$CASE"

    find . -type f ! -path '*/polyMesh/*' | xargs -r sed -i 's/\r$//'

    echo "=== blockMesh ==="
    blockMesh > log.blockMesh 2>&1
    echo "blockMesh done, exit=$?"

    if [ -f system/topoSetDict ]; then
        echo "=== topoSet ==="
        topoSet > log.topoSet 2>&1
        echo "topoSet done, exit=$?"
    fi

    if grep -q "radiationModel.*viewFactor" constant/radiationProperties 2>/dev/null; then
        echo "=== faceAgglomerate ==="
        faceAgglomerate -dict constant/viewFactorsDict > log.faceAgglomerate 2>&1
        echo "faceAgglomerate done, exit=$?"

        echo "=== viewFactorsGen ==="
        viewFactorsGen > log.viewFactorsGen 2>&1
        echo "viewFactorsGen done, exit=$?"
    fi

    SOLVER=$(grep "^application" system/controlDict | awk '{print $2}' | tr -d ';\r\n')
    echo "=== $SOLVER (50k iter) ==="
    START=$(date +%s)
    $SOLVER > log.solver 2>&1 || true
    END=$(date +%s)
    echo "Elapsed: $((END - START)) sec"

    echo ""
    echo "--- Errors ---"
    grep -i "fatal\|abort\|Negative" log.solver | head -3 || echo "No fatal errors"

    echo ""
    echo "--- Progress ---"
    grep "^Time = " log.solver | tail -3

    echo ""
    echo "--- rho ---"
    grep "rho min/max" log.solver | tail -3

    echo ""
    echo "--- Probes (last 5) ---"
    PROBE_DIR=$(ls -d postProcessing/probes/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
    if [ -n "$PROBE_DIR" ]; then
        echo "# upper_bench, lower_bench, floor_level"
        tail -5 "$PROBE_DIR/T" 2>/dev/null
    else
        echo "No probe data"
    fi

    echo ""
    echo "--- wallHeatFlux (last iter) ---"
    if [ -d postProcessing/wallHeatFlux ]; then
        WHFLUX_DIR=$(ls -d postProcessing/wallHeatFlux/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
        if [ -n "$WHFLUX_DIR" ]; then
            LAST_TIME=$(grep "^Time = " log.solver | tail -1 | awk '{print $3}')
            grep "$LAST_TIME" "$WHFLUX_DIR/wallHeatFlux.dat" 2>/dev/null || tail -7 "$WHFLUX_DIR/wallHeatFlux.dat"
        fi
    fi

    echo ""
    echo "--- volAverageT ---"
    if [ -d postProcessing/volAverageT ]; then
        VAT_DIR=$(ls -d postProcessing/volAverageT/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
        if [ -n "$VAT_DIR" ]; then
            tail -3 "$VAT_DIR/volFieldValue.dat" 2>/dev/null
        fi
    fi

    echo ""
    echo "--- Copy results back ---"
    for d in [0-9]*; do cp -r "$d" "$SRC/" 2>/dev/null || true; done
    cp -r postProcessing "$SRC/" 2>/dev/null || true
    cp log.* "$SRC/" 2>/dev/null || true
    echo "=== $LABEL DONE ==="
    echo ""
}

run_case "$BASE/results/K1" "K-1: 13kW + std vent (both fixedValue)"
run_case "$BASE/results/K2" "K-2: 13kW + half vent (both fixedValue)"
run_case "$BASE/results/K3" "K-3: 8kW + half vent (both fixedValue)"

echo "============================================"
echo "=== ALL K CASES COMPLETE ==="
echo "============================================"
echo ""
echo "  K-1: 13kW, supply=0.010, exhaust=0.015 (both fixedValue)"
echo "  K-2: 13kW, supply=0.005, exhaust=0.008 (both fixedValue)"
echo "  K-3:  8kW, supply=0.005, exhaust=0.008 (both fixedValue)"
echo ""
echo "Target: upper_bench 80-100 C, lower_bench 40-60 C"
