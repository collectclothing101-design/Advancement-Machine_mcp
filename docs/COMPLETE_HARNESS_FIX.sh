#!/bin/bash
# Complete Harness v3.0.1 Fix (MCP RequestContext + Skill Install)

set -e

OUTPUTS_DIR="/mnt/user-data/outputs"
HARNESS_SKILL_DIR="$OUTPUTS_DIR/harness-installation-skill-v1.0.0"
CLAUDE_SKILLS_DIR="$HOME/Library/Application Support/Claude/skills"

echo "═════════════════════════════════════════════════════"
echo "COMPLETE HARNESS v3.0.1 FIX SUITE"
echo "═════════════════════════════════════════════════════"
echo ""

# Step 1: Deploy fixed MCP server
echo "[1/2] Deploying MCP v3.0.1 (fixes RequestContext)..."
bash "$OUTPUTS_DIR/DEPLOY_HARNESS_v3.0.1_FIX.sh"

echo ""
echo "[2/2] Installing Harness Installation Skill v1.0.0..."

# Verify skill directory exists
if [ ! -d "$HARNESS_SKILL_DIR" ]; then
    echo "ERROR: Skill directory not found: $HARNESS_SKILL_DIR"
    exit 1
fi

# Create Claude skills directory if needed
mkdir -p "$CLAUDE_SKILLS_DIR"

# Copy skill
echo "  Copying skill to: $CLAUDE_SKILLS_DIR/harness-installation"
rm -rf "$CLAUDE_SKILLS_DIR/harness-installation" 2>/dev/null || true
cp -r "$HARNESS_SKILL_DIR" "$CLAUDE_SKILLS_DIR/harness-installation"

# Set permissions on scripts
chmod -R +x "$CLAUDE_SKILLS_DIR/harness-installation/scripts"/*.sh 2>/dev/null || true

echo "  ✓ Skill installed"

echo ""
echo "═════════════════════════════════════════════════════"
echo "ALL FIXES COMPLETE"
echo "═════════════════════════════════════════════════════"
echo ""
echo "Summary:"
echo "✓ MCP server: v3.0.1 (RequestContext fix applied)"
echo "✓ Skill: v1.0.0 (installed to ~/.../Claude/skills/)"
echo ""
echo "Final steps:"
echo "1. Restart Claude: killall Claude && open /Applications/Claude.app"
echo "2. Check Settings > Integrations > harness [Connected]"
echo "3. Trigger skill: 'Help me install Harness'"
echo "4. Test MCP: '@harness help'"
echo ""
