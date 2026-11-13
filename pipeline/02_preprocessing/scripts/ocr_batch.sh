#!/bin/bash
cd "$(dirname "$0")"
export MAX_IMAGE_PIXELS=1000000000
UPLOAD_DIR="./original"
OCRED_DIR="./ocred"
THREADS=2

# 1. Ensure target directories exist
mkdir -p "$UPLOAD_DIR" "$OCRED_DIR"

# 2. Extract cleanly sorted lists of base filenames (excluding temp files)
find "$UPLOAD_DIR" -maxdepth 1 -name "*.pdf" -exec basename {} \; | sort > all_list.txt
find "$OCRED_DIR" -maxdepth 1 -name "*.pdf" ! -name "temp_*" -exec basename {} \; | sort > done_list.txt

# 3. Determine pending tasks by matching filenames (original minus already ocred)
comm -23 all_list.txt done_list.txt > pending_tasks.txt

TOTAL=$(wc -l < all_list.txt | tr -d ' ')
DONE_COUNT=$(wc -l < done_list.txt | tr -d ' ')
PENDING=$(wc -l < pending_tasks.txt | tr -d ' ')

echo "=========================================="
echo "Original files in batch:  $TOTAL"
echo "Total files in output:    $DONE_COUNT"
echo "Pending tasks to process: $PENDING"
echo "=========================================="

if [ "$PENDING" -eq 0 ]; then
    echo "No pending files found. All files in '$UPLOAD_DIR' have already been processed."
    rm -f all_list.txt done_list.txt pending_tasks.txt
    exit 0
fi

echo "Starting parallel OCR processing..."

# 4. Execute tasks via GNU Parallel
cat pending_tasks.txt | parallel --jobs "$THREADS" --keep-order --progress '
    file="'"$UPLOAD_DIR"'/{}"
    output_file="'"$OCRED_DIR"'/{}"
    temp_file="'"$OCRED_DIR"'/temp_{}"

    # Compress / standardize PDF prior to OCR
    gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/printer \
       -dColorImageResolution=300 -dGrayImageResolution=300 -dMonoImageResolution=300 \
       -dNOPAUSE -dBATCH -sOutputFile="$temp_file" "$file" > /dev/null 2>&1

    # Apply OCR
    ocrmypdf --force-ocr --clean "$temp_file" "$output_file" > /dev/null 2>&1

    rm -f "$temp_file"
    echo "Completed: {}"
'

echo "Validating output files against the original set..."

# 5. Re-check: Refresh output list and verify every file in original exists in ocred
find "$OCRED_DIR" -maxdepth 1 -name "*.pdf" ! -name "temp_*" -exec basename {} \; | sort > done_list.txt
comm -23 all_list.txt done_list.txt > missing_files.txt

MISSING_COUNT=$(wc -l < missing_files.txt | tr -d ' ')

if [ "$MISSING_COUNT" -gt 0 ]; then
    echo "⚠️ Warning: $MISSING_COUNT file(s) from '$UPLOAD_DIR' failed to generate in '$OCRED_DIR':"
    cat missing_files.txt
else
    echo "✅ Validation passed: All files from '$UPLOAD_DIR' exist in '$OCRED_DIR'."
fi

# 6. Cleanup temporary metadata files
rm -f all_list.txt done_list.txt pending_tasks.txt missing_files.txt
echo "--- Processing completed ---"