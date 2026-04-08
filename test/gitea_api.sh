#!/bin/bash
# Helper: call Gitea API via docker exec (bypasses host port forwarding issues)

GITEA_TOKEN="${GITEA_TOKEN:-c50bad400bd9b8cde3e930cca052eae6ded71f7b}"
GITEA_URL="http://127.0.0.1:3000"

gitea_get() {
    docker exec gitea wget -qO- \
        --header="Authorization: token ${GITEA_TOKEN}" \
        "${GITEA_URL}$1" 2>/dev/null
}

gitea_post() {
    local path="$1"
    local data="$2"
    docker exec gitea wget -qO- \
        --post-data="$data" \
        --header="Content-Type: application/json" \
        --header="Authorization: token ${GITEA_TOKEN}" \
        "${GITEA_URL}${path}" 2>/dev/null
}

gitea_put() {
    local path="$1"
    local data="${2:-{}}"
    docker exec gitea wget -qO- \
        --method=PUT \
        --body-data="$data" \
        --header="Content-Type: application/json" \
        --header="Authorization: token ${GITEA_TOKEN}" \
        "${GITEA_URL}${path}" 2>/dev/null
}
