import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from artiq.experiment import EnvExperiment, rpc


class TestCore(EnvExperiment):
	def build(self):
		self.setattr_device("core")

	@rpc
	def run(self):
            input_size = 10     # number of input features
            hidden_size = 16
            output_size = 2     # number of classes

            # Define a simple neural network without a custom class
            model = nn.Sequential(
                nn.Linear(input_size, hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, output_size)
            )

            # Loss and optimizer
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(model.parameters(), lr=0.01)

            # Dummy data: 100 samples with 10 features
            X = torch.randn(100, input_size)
            y = torch.randint(0, output_size, (100,))

            # Training loop
            for epoch in range(50):
                optimizer.zero_grad()
                outputs = model(X)
                loss = criterion(outputs, y)
                loss.backward()
                optimizer.step()
                
                if (epoch + 1) % 10 == 0:
                    print(f"Epoch [{epoch+1}/50], Loss: {loss.item():.4f}")