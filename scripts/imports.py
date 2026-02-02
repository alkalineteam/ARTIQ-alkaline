import torch
from torch import version as torch_version
from ndscan.experiment import Fragment
import torchvision
# import torchaudio
import pandas as pd
import seaborn
import matplotlib
import sklearn
import requests
# import boto3

t1 = torch.randn(2, 2)
t2 = torch.randn(2, 2)

@torch.compile
def opt_foo2(x, y):
    a = torch.sin(x)
    b = torch.cos(y)
    return a + b
print(opt_foo2(t1, t2))

print(torch.__version__)
print(torch.tensor([1, 2, 3]))
print(torch.cuda.is_available())
print(getattr(torch_version, 'cuda', 'unknown_cuda_version'))
print(torch.cuda.device_count())
if torch.cuda.is_available() and torch.cuda.device_count() > 0:
    print(torch.cuda.get_device_name(0))
else:
    print("No CUDA enabled GPU detected (torch.cuda.is_available() is False or device_count == 0)")