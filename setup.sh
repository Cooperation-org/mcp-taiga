#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Creating venv..."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

chmod +x mcp-taiga

echo ""
echo "Done. Configure your token:"
echo "  echo 'TAIGA_URL=https://taiga.linkedtrust.us' >> ~/.mcp-taiga.conf"
echo "  echo 'TAIGA_TOKEN=your-token' >> ~/.mcp-taiga.conf"
echo ""
echo "To add to PATH:"
echo "  sudo ln -sf $(pwd)/mcp-taiga /opt/shared/tools/mcp-taiga"
