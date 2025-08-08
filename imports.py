import torch
import torchvision
import torchaudio
import pandas as pd
import seaborn
import matplotlib
import sklearn
import requests
# import boto3

# t1 = torch.randn(10, 10)
# t2 = torch.randn(10, 10)

# @torch.compile
# def opt_foo2(x, y):
#     a = torch.sin(x)
#     b = torch.cos(y)
#     return a + b
# print(opt_foo2(t1, t2))

print(torch.__version__)
print(torch.tensor([1, 2, 3]))
print(torch.cuda.is_available())