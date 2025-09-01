#!/usr/bin/env bash
set -euo pipefail

# This script ensures ALL PyTorch / NVIDIA CUDA wheel hashes are present in uv.lock
# It scans uv.lock for any wheel URLs hosted at download.pytorch.org that lack a hash field
# and inserts the computed sha256 so Nix stops emitting "missing hash" warnings.
#
# Usage:
#   ./fix-hashes.sh            # adds any missing hashes in-place
#   NOCACHE=1 ./fix-hashes.sh   # force re-download even if cached
#
# Requires: bash, python3, network access.

# Check if uv.lock exists
if [ ! -f "uv.lock" ]; then
    echo "❌ uv.lock not found in current directory."
    echo "   Please run 'uv lock' first or navigate to the project root."
    exit 1
fi

# echo "📁 Found uv.lock file"
echo "🔍 Checking for PyTorch wheel hashes..."

python3 - <<'PY'
import hashlib, os, re, sys, urllib.request, tempfile, time

LOCK_PATH = 'uv.lock'
if not os.path.isfile(LOCK_PATH):
    print('❌ uv.lock disappeared during run')
    sys.exit(1)

with open(LOCK_PATH, 'r') as f:
    content = f.read()

# Regex to find wheel entries without hash
wheel_re = re.compile(r'(\{ *url *= *"(https://download\.pytorch\.org/[^" ]+?\.whl)" *\})')

missing = []
for m in wheel_re.finditer(content):
    full_entry = m.group(1)
    url = m.group(2)
    # If the entry already has hash (some variant) skip
    # (We matched only entries without hash but double-check in case pattern broadens.)
    if 'hash =' in full_entry:
        continue
    missing.append((full_entry, url))

if not missing:
    print('✅ No missing PyTorch / NVIDIA wheel hashes found.')
    sys.exit(0)

print(f'🧪 Found {len(missing)} wheel(s) missing hashes — downloading...')

cache_dir = os.path.join(tempfile.gettempdir(), 'pytorch-wheel-hashes')
os.makedirs(cache_dir, exist_ok=True)
force = bool(os.environ.get('NOCACHE'))

def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(1<<20), b''):
            h.update(chunk)
    return h.hexdigest()

updated = 0
for full_entry, url in missing:
    name = url.rsplit('/', 1)[-1]
    local_path = os.path.join(cache_dir, name)
    if not os.path.exists(local_path) or force:
        try:
            print(f'  ↓ Fetch {name}')
            with urllib.request.urlopen(url, timeout=120) as r, open(local_path, 'wb') as out:
                out.write(r.read())
        except Exception as e:
            print(f'  ❌ Failed to download {url}: {e}')
            continue
    else:
        print(f'  • Using cached {name}')
    digest = sha256_of(local_path)
    # Construct replacement with hash inserted
    replacement = f'{{ url = "{url}", hash = "sha256:{digest}" }}'
    # Replace only the first occurrence of the specific entry
    content, n = re.subn(re.escape(full_entry), replacement, content, count=1)
    if n == 1:
        updated += 1
        print(f'    ✅ Added hash sha256:{digest[:12]}…')
    else:
        print(f'    ⚠ Could not patch entry for {url}')

if updated:
    backup = LOCK_PATH + f'.bak.{int(time.time())}'
    with open(backup, 'w') as b:
        b.write(content)
    with open(LOCK_PATH, 'w') as f:
        f.write(content)
    print(f'\n✅ Added hashes for {updated} wheel(s). Backup saved to {backup}')
else:
    print('ℹ No entries updated (all failed or already hashed).')
PY

echo "💡 Tip: Run after 'uv lock' whenever you change torch / CUDA versions. Commit uv.lock afterward."
