#!/bin/bash
set -e

DO="root@68.183.130.60"
DEST="$DO:/home/simonhans/coding/statistical_uniqueness"
SSH="ssh -i $HOME/.ssh/id_ed25519"

echo "Syncing to DO..."
rsync -av --checksum \
  -e "ssh -i $HOME/.ssh/id_ed25519" \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='data/cache/' \
  --exclude='analysis/' \
  --exclude='*.egg-info/' \
  ./ "$DEST"

echo "Restarting service..."
$SSH $DO "systemctl restart uniquefier && systemctl is-active uniquefier"

echo "Deployed."
