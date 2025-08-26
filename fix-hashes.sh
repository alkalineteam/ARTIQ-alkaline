#!/usr/bin/env bash
set -euo pipefail

# Hash Fix Script
# This script ensures PyTorch wheel hashes are present in uv.lock
# Run this before 'nix develop --impure' if you encounter PyTorch hash errors

echo "🔧 Hash Fix Script"
echo "=================="

# Check if uv.lock exists
if [ ! -f "uv.lock" ]; then
    echo "❌ uv.lock not found in current directory."
    echo "   Please run 'uv lock' first or navigate to the project root."
    exit 1
fi

echo "📁 Found uv.lock file"
echo "🔍 Checking for PyTorch wheel hashes..."

# Use Python to add missing hashes
python3 -c "
torch_hashes = {
    'torch-2.8.0%2Bcu129-cp313-cp313-manylinux_2_28_x86_64.whl': 'sha256:563740167be2189b71530b503f0c8a8d7a8267dd49d4de6f9c5f1d23fbe237df',
    'torch-2.8.0%2Bcu129-cp313-cp313-win_amd64.whl': 'sha256:2cef066f9759ff4d7868a8c3695aa60d9a878598acb3685bb1ef2fdac29dcd68',
    'torch-2.8.0%2Bcu129-cp313-cp313t-manylinux_2_28_x86_64.whl': 'sha256:6344260959ebcfa6dae458e1c4365195bcfdf00f4f1f1ad438cbaf50756829ed',
    'torch-2.8.0%2Bcu129-cp313-cp313t-win_amd64.whl': 'sha256:9c0cd89e54ce3208c5cf4163773b9cda0067e4b48cfcac56a4e04af52040'
}

try:
    with open('uv.lock', 'r') as f:
        content = f.read()
    
    modified = False
    for wheel_name, wheel_hash in torch_hashes.items():
        pattern = '{{ url = \"https://download.pytorch.org/whl/cu129/{}\" }},'.format(wheel_name)
        replacement = '{{ url = \"https://download.pytorch.org/whl/cu129/{}\", hash = \"{}\" }},'.format(wheel_name, wheel_hash)
        if pattern in content and replacement not in content:
            content = content.replace(pattern, replacement)
            modified = True
            print(f'  ✅ Added hash for {wheel_name}')
    
    if modified:
        with open('uv.lock', 'w') as f:
            f.write(content)
        print('\\n✅ PyTorch wheel hashes added to uv.lock successfully!')
    else:
        print('✅ All PyTorch wheel hashes are already present')
except Exception as e:
    print(f'❌ Error processing uv.lock: {e}')
    exit(1)
"

echo ""
echo "🚀 Ready to run: nix develop --impure"
echo ""
echo "💡 Tip: Run this script after any 'uv lock' operation to ensure"
echo "   PyTorch hashes remain in place."
