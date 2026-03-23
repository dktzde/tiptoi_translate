#!/bin/bash
# colab_sync.sh – Upload OGG-ZIP nach Drive / Download Transcripts-ZIP von Drive
# Verwendung:
#   ./colab_sync.sh upload
#   ./colab_sync.sh download

set -e
cd "$(dirname "$0")"

DRIVE_DIR="gdrive:tiptoi"

# Neueste colab_config.py in 07_colab_upload/ suchen
CONFIG=$(find 07_colab_upload -name "colab_config.py" -printf "%T@ %p\n" 2>/dev/null \
         | sort -n | tail -1 | cut -d' ' -f2-)

if [[ -z "$CONFIG" ]]; then
    echo "❌ Keine colab_config.py gefunden in 07_colab_upload/"
    echo "   → Erst pipeline starten: ./tiptoi.sh \"01_input/...gme\""
    exit 1
fi

# BOOK, VERSION, LANG aus colab_config.py lesen
BOOK=$(python3 -c "exec(open('${CONFIG}').read()); print(BOOK)")
VERSION=$(python3 -c "exec(open('${CONFIG}').read()); print(VERSION)")
LANG=$(python3 -c "exec(open('${CONFIG}').read()); print(LANG)")

echo "  Buch:    ${BOOK}"
echo "  Version: ${VERSION}"
echo "  Sprache: ${LANG}"
echo "  Config:  ${CONFIG}"
echo ""

if [[ $# -lt 1 || "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Verwendung: $0 upload|download|bench"
    echo ""
    echo "  upload    OGG-ZIP + colab_config.py → Google Drive / tiptoi /"
    echo "  download  Transcripts-ZIP von Drive laden + nach 03_transcripts/ entpacken"
    echo "  bench     Nur gpu_benchmark.csv von Drive laden → backup/gpu_benchmark.csv"
    echo ""
    echo "──────────────────────────────────────────────────────"
    echo "  Google Drive erstmalig verbinden (einmalig nötig):"
    echo "──────────────────────────────────────────────────────"
    echo ""
    echo "  1. rclone konfigurieren:"
    echo "       rclone config"
    echo "       → 'n' (neue Remote)"
    echo "       → Name: gdrive"
    echo "       → Typ: drive  (Google Drive)"
    echo "       → client_id + secret: leer lassen (Enter)"
    echo "       → scope: 1 (Vollzugriff)"
    echo "       → root_folder_id: leer lassen (Enter)"
    echo "       → service_account: leer lassen (Enter)"
    echo "       → Auto-Config: y → Browser öffnet sich → Google-Konto auswählen"
    echo "       → Shared Drive: n"
    echo "       → Fertig: y"
    echo ""
    echo "  2. Verbindung testen:"
    echo "       rclone lsd gdrive:"
    echo "       rclone ls gdrive:tiptoi"
    echo ""
    echo "  3. tiptoi-Ordner auf Drive anlegen (falls nicht vorhanden):"
    echo "       rclone mkdir gdrive:tiptoi"
    echo ""
    [[ "$1" == "--help" || "$1" == "-h" ]] && exit 0 || exit 1
fi

MODE="$1"

case "$MODE" in

  upload)
    ZIP="07_colab_upload/${BOOK}/${BOOK}_ogg.zip"
    if [[ ! -f "$ZIP" ]]; then
        echo "❌ ZIP nicht gefunden: $ZIP"
        exit 1
    fi
    echo "↑ Upload: $ZIP"
    echo "        → ${DRIVE_DIR}/${BOOK}_ogg.zip"
    rclone copyto "$ZIP" "${DRIVE_DIR}/${BOOK}_ogg.zip" --progress

    echo "↑ Upload: $CONFIG"
    echo "        → ${DRIVE_DIR}/colab_config.py"
    rclone copyto "$CONFIG" "${DRIVE_DIR}/colab_config.py" --progress

    echo "✓ Upload fertig"
    ;;

  download)
    ZIP_NAME="${BOOK}_transcripts.zip"
    LOCAL_ZIP="/tmp/${ZIP_NAME}"
    EXTRACT_DIR="03_transcripts/${BOOK}"

    echo "↓ Download: ${DRIVE_DIR}/${ZIP_NAME}"
    rclone copyto "${DRIVE_DIR}/${ZIP_NAME}" "$LOCAL_ZIP" --progress

    echo "  Entpacke nach: ${EXTRACT_DIR}/"
    mkdir -p "$EXTRACT_DIR"
    unzip -o "$LOCAL_ZIP" -d "$EXTRACT_DIR"
    rm "$LOCAL_ZIP"

    # GPU-Benchmark CSV herunterladen + mit Backup zusammenführen
    BENCH_CSV="gpu_benchmark.csv"
    BENCH_LOCAL="backup/${BENCH_CSV}"
    BENCH_TMP="/tmp/${BENCH_CSV}"
    if rclone copyto "${DRIVE_DIR}/${BENCH_CSV}" "$BENCH_TMP" 2>/dev/null; then
        if [[ -f "$BENCH_LOCAL" ]]; then
            # Neue Zeilen anfügen (Header der Drive-Datei überspringen)
            tail -n +2 "$BENCH_TMP" >> "$BENCH_LOCAL"
            echo "✓ gpu_benchmark.csv: neue Zeilen angehängt → backup/${BENCH_CSV}"
        else
            cp "$BENCH_TMP" "$BENCH_LOCAL"
            echo "✓ gpu_benchmark.csv heruntergeladen → backup/${BENCH_CSV}"
        fi
        rm "$BENCH_TMP"
    else
        echo "  (gpu_benchmark.csv noch nicht auf Drive vorhanden – übersprungen)"
    fi

    echo ""
    echo "✓ Download + Entpacken fertig"
    echo ""
    echo "  Jetzt pipeline fortsetzen:"
    echo "    ./tiptoi.sh \"01_input/${BOOK}.gme\""
    ;;

  bench)
    BENCH_CSV="gpu_benchmark.csv"
    BENCH_LOCAL="backup/${BENCH_CSV}"
    BENCH_TMP="/tmp/${BENCH_CSV}"
    echo "↓ Download: ${DRIVE_DIR}/${BENCH_CSV}"
    if rclone copyto "${DRIVE_DIR}/${BENCH_CSV}" "$BENCH_TMP" --progress; then
        if [[ -f "$BENCH_LOCAL" ]]; then
            tail -n +2 "$BENCH_TMP" >> "$BENCH_LOCAL"
            echo "✓ Neue Zeilen angehängt → backup/${BENCH_CSV}"
        else
            cp "$BENCH_TMP" "$BENCH_LOCAL"
            echo "✓ Heruntergeladen → backup/${BENCH_CSV}"
        fi
        rm "$BENCH_TMP"
    else
        echo "❌ gpu_benchmark.csv nicht auf Drive gefunden"
        exit 1
    fi
    ;;

  *)
    echo "❌ Unbekannter Modus: $MODE (upload | download | bench)"
    exit 1
    ;;

esac
