#!/bin/bash

# Set the base directory (parent of Subs directory)
BASE_DIR="/media/jellyfin/shows/shows/Welcome to Wrexham/Season 1"
SUBS_DIR="${BASE_DIR}/Subs"

# Check if the directories exist
if [ ! -d "${BASE_DIR}" ]; then
    echo "Error: Base directory does not exist: ${BASE_DIR}"
    exit 1
fi

if [ ! -d "${SUBS_DIR}" ]; then
    echo "Error: Subs directory does not exist: ${SUBS_DIR}"
    exit 1
fi

# Process each subdirectory in the Subs folder
for SUB_FOLDER in "${SUBS_DIR}"/*; do
    if [ -d "${SUB_FOLDER}" ]; then
        # Extract the folder name
        FOLDER_NAME=$(basename "${SUB_FOLDER}")
        
        # Find the corresponding MP4 file in the parent directory
        MP4_FILE="${BASE_DIR}/${FOLDER_NAME}.mp4"
        
        if [ -f "${MP4_FILE}" ]; then
            # Get the base name of the MP4 file without extension
            MP4_BASE=$(basename "${MP4_FILE}" .mp4)
            
            # Find all SRT files in the subdirectory
            SRT_COUNT=0
            for SRT_FILE in "${SUB_FOLDER}"/*.srt; do
                if [ -f "${SRT_FILE}" ]; then
                    SRT_COUNT=$((SRT_COUNT + 1))
                    
                    # If there's only one SRT file, use the MP4 name directly
                    if [ $(find "${SUB_FOLDER}" -name "*.srt" | wc -l) -eq 1 ]; then
                        TARGET_NAME="${MP4_BASE}.srt"
                    else
                        # If there are multiple SRT files, append a language identifier
                        # Extract language from filename if possible
                        SRT_BASENAME=$(basename "${SRT_FILE}")
                        
                        # Try to extract language from the SRT filename (assumes format like "2_English.srt")
                        LANG_ID=$(echo "${SRT_BASENAME}" | grep -oE "[0-9]+_[A-Za-z]+" | head -1)
                        
                        if [ -n "${LANG_ID}" ]; then
                            TARGET_NAME="${MP4_BASE}.${LANG_ID}.srt"
                        else
                            # If no language identifier found, use numbering
                            TARGET_NAME="${MP4_BASE}.sub${SRT_COUNT}.srt"
                        fi
                    fi
                    
                    # Copy the SRT file to the parent directory with the new name
                    echo "Copying ${SRT_FILE} to ${BASE_DIR}/${TARGET_NAME}"
                    cp "${SRT_FILE}" "${BASE_DIR}/${TARGET_NAME}"
                fi
            done
            
            if [ ${SRT_COUNT} -eq 0 ]; then
                echo "No SRT files found in ${SUB_FOLDER}"
            fi
        else
            echo "Warning: No corresponding MP4 file found for ${FOLDER_NAME}"
        fi
    fi
done

echo "Subtitle extraction completed."
