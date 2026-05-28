#!/bin/bash
set -e
DEST="simonhans@raspberrypi:~/coding/statistical_uniqueness/"

echo "Syncing to Pi..."
rsync -avz \
  --exclude='.env' \
  --exclude='data/cache/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  ./ "$DEST"

echo ""
echo "Done. To run on Pi:"
echo "  ssh simonhans@raspberrypi 'cd ~/coding/statistical_uniqueness && python app.py'"
echo ""
echo "Note: Pi needs a .env with CENSUS_API_KEY — copy from snotrac if not present:"
echo "  ssh simonhans@raspberrypi 'echo CENSUS_API_KEY=46dd547ddad8d726d302bada27371ab52f789f48 > ~/coding/statistical_uniqueness/.env'"
