#!/bin/bash

# Base URL of the API
BASE_URL="https://eoagritool-cwfzfndaazauawex.canadacentral-01.azurewebsites.net"

# Endpoint for deleting extensions
DELETE_ENDPOINT="/api/delete_extension"

# Function to delete files
delete_files() {
    # Make a DELETE request to the API endpoint
    response=$(curl -X DELETE "$BASE_URL$DELETE_ENDPOINT" -w "%{http_code}" -o /dev/null -s)
    
    # Check the HTTP response code
    if [ "$response" -eq 200 ]; then
        echo "Files deleted successfully."
    else
        echo "Failed to delete files. HTTP response code: $response"
    fi
}

# Call the function to delete files
delete_files
