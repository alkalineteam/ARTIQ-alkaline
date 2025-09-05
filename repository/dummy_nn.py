import torch
import torch.nn as nn
import torch.optim as optim
from artiq.experiment import EnvExperiment, rpc, kernel


class ffnn(EnvExperiment):
    def build(self):
        self.setattr_device("core")

    @rpc
    def train_model(self):
        input_size = 10      # number of input features
        hidden_size = 16
        output_size = 2      # number of classes

        model = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size)
        )

        model.input_size = input_size
        model.output_size = output_size

        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.01)

        X_train = torch.randn(100, input_size)
        y_train = torch.randint(0, output_size, (100,))

        for epoch in range(50):
            optimizer.zero_grad()
            outputs = model(X_train)
            loss = criterion(outputs, y_train)
            loss.backward()
            optimizer.step()
            if (epoch + 1) % 10 == 0:
                print(f"Epoch [{epoch+1}/50], Loss: {loss.item():.4f}")

        return model
    
    @kernel
    def run(self):
        model = self.train_model()
        X_test = torch.randn(20, model.input_size)
        y_test = torch.randint(0, model.output_size, (20,))

        with torch.no_grad():
            predictions = model(X_test)
            predicted_classes = predictions.argmax(dim=1)

        accuracy = (predicted_classes == y_test).float().mean()
        print(accuracy)