#!/bin/bash

# Usage: ./add_context.sh <repo_url> <package_name>

REPO_URL=$1
PACKAGE_NAME=$2

if [ -z "$REPO_URL" ] || [ -z "$PACKAGE_NAME" ]; then
  echo "Usage: ./add_context.sh <repo_url> <package_name>"
  exit 1
fi

CONTEXT_DIR="_blueprint/context/$PACKAGE_NAME"
REPO_DIR="$CONTEXT_DIR/repo"

echo "Creating directory: $CONTEXT_DIR"
mkdir -p "$REPO_DIR"

echo "Cloning repository: $REPO_URL"
git clone --depth 1 "$REPO_URL" "$REPO_DIR"

echo "Done. Now analyze the repo and create $CONTEXT_DIR/README.md"
