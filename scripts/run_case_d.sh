#!/bin/bash
# Run Case D: transient buoyantPimpleFoam with ventilation
set -e
export FOAM_SIGFPE=false

SRC="/mnt/d/dev/SaunaFEM/results/dry_sauna_transient_vent"
CASE_NAME=$(basename "$SRC")
CASE="$HOME/saunaflow_run/$CASE_NAME"

echo "============================================"
echo "=== Case D (transient + vent): $CASE_NAME ==="
echo "============================================"

rm -rf "$CASE"
mkdir -p "$(dirname "$CASE")"
cp -r "$SRC" "$CASE"
cd "$CASE"

# Fix Windows line endings
find . -type f ! -path '*/polyMesh/*' | xargs -r sed -i 's/\r$//'

echo "=== blockMesh ==="
blockMesh > log.blockMesh 2>&1
echo "blockMesh done, exit=$?"

if [ -f system/topoSetDict ]; then
    echo "=== topoSet ==="
    topoSet > log.topoSet 2>&1
    echo "topoSet done, exit=$?"
fi

# Generate view factors for radiation model if enabled
if grep -q "radiationModel.*viewFactor" constant/radiationProperties 2>/dev/null; then
    echo "=== faceAgglomerate ==="
    faceAgglomerate -dict constant/viewFactorsDict > log.faceAgglomerate 2>&1
    FA_EXIT=$?
    echo "faceAgglomerate done, exit=$FA_EXIT"
    if [ $FA_EXIT -ne 0 ]; then
        echo "ERROR: faceAgglomerate failed"
        cat log.faceAgglomerate
        exit 1
    fi
    # Verify finalAgglom was created
    if [ ! -f constant/finalAgglom ]; then
        echo "ERROR: constant/finalAgglom not created by faceAgglomerate"
        exit 1
    fi

    echo "=== viewFactorsGen ==="
    viewFactorsGen > log.viewFactorsGen 2>&1
    VF_EXIT=$?
    echo "viewFactorsGen done, exit=$VF_EXIT"
    grep "coarse faces" log.viewFactorsGen || true
    if [ $VF_EXIT -ne 0 ]; then
        echo "ERROR: viewFactorsGen failed"
        tail -20 log.viewFactorsGen
        exit 1
    fi
fi

SOLVER=$(grep "^application" system/controlDict | awk '{print $2}' | tr -d ';\r\n')
echo "=== $SOLVER ==="
$SOLVER > log.solver 2>&1 || true

echo ""
echo "--- Errors ---"
grep -i "fatal\|abort" log.solver | head -3 || echo "No fatal errors"

echo ""
echo "--- Progress ---"
grep "^Time = " log.solver | tail -10

echo ""
echo "--- Courant ---"
grep "Courant Number" log.solver | tail -3

echo ""
echo "--- rho ---"
grep "rho min/max" log.solver | tail -3

echo ""
echo "--- Probes ---"
PROBE_DIR=$(ls -d postProcessing/probes/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
if [ -n "$PROBE_DIR" ]; then
    echo "Time series (last 15 lines):"
    tail -15 "$PROBE_DIR/T" 2>/dev/null
else
    echo "No probe data"
fi

echo ""
echo "--- wallHeatFlux ---"
if [ -d postProcessing/wallHeatFlux ]; then
    WHFLUX_DIR=$(ls -d postProcessing/wallHeatFlux/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
    if [ -n "$WHFLUX_DIR" ]; then
        tail -10 "$WHFLUX_DIR/wallHeatFlux.dat" 2>/dev/null
    fi
else
    echo "No wallHeatFlux data"
fi

echo ""
echo "--- volAverageT ---"
if [ -d postProcessing/volAverageT ]; then
    VAT_DIR=$(ls -d postProcessing/volAverageT/[0-9]* 2>/dev/null | sort -t/ -k3 -n | tail -1)
    if [ -n "$VAT_DIR" ]; then
        tail -10 "$VAT_DIR/volFieldValue.dat" 2>/dev/null
    fi
else
    echo "No volAverageT data"
fi

echo ""
echo "--- Copy back ---"
for d in [0-9]*; do cp -r "$d" "$SRC/" 2>/dev/null || true; done
cp -r postProcessing "$SRC/" 2>/dev/null || true
cp log.* "$SRC/" 2>/dev/null || true
echo "=== Case D Done ==="
