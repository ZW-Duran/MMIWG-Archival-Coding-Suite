#!/bin/bash

INPUT_FILE="./pdf_links.txt"
BAD_LINKS_FILE="bad_links.txt"

> "$BAD_LINKS_FILE"

echo "Start..."

while IFS= read -r url || [ -n "$url" ]; do
    [[ -z "$url" ]] && continue
    status_code=$(curl -L -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url")

    if [[ "$status_code" -ne 200 ]]; then
        echo " [Invalid] $status_code - $url"
        echo "$url" >> "$BAD_LINKS_FILE"
    else
        echo " [Normal] 200 - $url"
    fi
done < "$INPUT_FILE"

echo "--------------------------------------"
echo "Complete, please check: $BAD_LINKS_FILE"
