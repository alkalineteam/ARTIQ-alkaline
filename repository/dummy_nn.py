import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from artiq.experiment import EnvExperiment, rpc


class ffnn(EnvExperiment):
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

            # Dummy training data: 100 samples
            X_train = torch.randn(100, input_size)
            y_train = torch.randint(0, output_size, (100,))

            # Train the model
            for epoch in range(50):
                optimizer.zero_grad()
                outputs = model(X_train)
                loss = criterion(outputs, y_train)
                loss.backward()
                optimizer.step()

                if (epoch + 1) % 10 == 0:
                    print(f"Epoch [{epoch+1}/50], Loss: {loss.item():.4f}")

            # ---------------------------
            # Evaluation on random test data
            # ---------------------------
            X_test = torch.randn(20, input_size)             # 20 test samples
            y_test = torch.randint(0, output_size, (20,))    # random labels

            with torch.no_grad():  # no gradient calculation needed
                predictions = model(X_test)
                predicted_classes = predictions.argmax(dim=1)

            accuracy = (predicted_classes == y_test).float().mean()
            print(f"Accuracy on random test set: {accuracy.item()*100:.2f}%")