#!/usr/bin/env python3
"""
Test CUDA availability and functionality
"""
import sys

# Test basic imports
print("=== Testing CUDA Environment ===")
print(f"Python: {sys.version}")

# Test if torch is available (it was removed)
try:
    import torch
    print(f"PyTorch: {torch.__version__}")
    print(f"CUDA Available: {torch.cuda.is_available()}")
    print(f"CUDA Devices: {torch.cuda.device_count()}")
    
    if torch.cuda.is_available():
        print(f"Current CUDA Device: {torch.cuda.current_device()}")
        print(f"Device Name: {torch.cuda.get_device_name()}")
        
        # Test tensor creation on GPU
        try:
            x = torch.randn(3, 3).cuda()
            print(f"GPU Tensor: {x.device}")
            print("✓ CUDA tensor operations working!")
        except Exception as e:
            print(f"✗ CUDA tensor operations failed: {e}")
    else:
        print("✗ CUDA not available")
        
except ImportError:
    print("PyTorch not installed (this is expected after removal)")

# Test NVIDIA driver access
print("\n=== Testing NVIDIA Driver ===")
try:
    import subprocess
    result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
    if result.returncode == 0:
        print("✓ nvidia-smi accessible")
        # Show just the first few lines
        lines = result.stdout.split('\n')[:5]
        for line in lines:
            if line.strip():
                print(f"  {line}")
    else:
        print("✗ nvidia-smi not accessible")
        print(f"  Error: {result.stderr}")
except FileNotFoundError:
    print("✗ nvidia-smi command not found")

print("\n=== CUDA Environment Variables ===")
import os
cuda_vars = ['CUDA_VISIBLE_DEVICES', 'CUDA_HOME', 'LD_LIBRARY_PATH']
for var in cuda_vars:
    value = os.environ.get(var, 'Not set')
    print(f"{var}: {value}")