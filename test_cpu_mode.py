#!/usr/bin/env python3
"""
Test CPU-only mode behavior
"""
import torch

print("=== CPU-Only Mode Test ===")
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"Device count: {torch.cuda.device_count()}")

# Test tensor operations on CPU
x = torch.randn(3, 3)
y = torch.randn(3, 3)
z = torch.mm(x, y)

print(f"Tensor device: {x.device}")
print(f"Matrix multiplication result shape: {z.shape}")
print("✅ CPU tensor operations working!")

# Test that CUDA operations fail gracefully
if torch.cuda.is_available():
    print("⚠️  CUDA is available - this should be CPU-only mode")
else:
    print("✅ Confirmed: Running in CPU-only mode")
    try:
        x_gpu = x.cuda()
        print("⚠️  Unexpected: .cuda() worked in CPU-only mode")
    except:
        print("✅ Confirmed: .cuda() fails gracefully in CPU-only mode")