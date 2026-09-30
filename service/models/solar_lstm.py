"""Solar LSTM Forecaster — Multi-step Global Horizontal Irradiance (GHI) Prediction

Input:  Lookback window of 144 timesteps (24 hours at 10-minute resolution) x 16 aligned features.
Output: Forecast horizon of 18 timesteps (3 hours ahead at 10-minute resolution).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class SolarLSTMForecaster(nn.Module):
    """Deep LSTM Network for multi-step solar irradiance forecasting."""

    def __init__(
        self,
        input_dim: int = 16,
        hidden_dim: int = 128,
        num_layers: int = 2,
        forecast_steps: int = 18,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.forecast_steps = forecast_steps

        # Multi-layer LSTM
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        # Output MLP Head
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, forecast_steps),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.
        Args:
            x: Input tensor of shape (batch_size, seq_len=144, input_dim=16)
        Returns:
            GHI forecast tensor of shape (batch_size, forecast_steps=18)
        """
        # LSTM output: (batch_size, seq_len, hidden_dim)
        lstm_out, _ = self.lstm(x)

        # Take last timestep's hidden state for sequence-to-vector prediction
        last_hidden = lstm_out[:, -1, :]

        # Project to 18-step forecast
        raw_pred = self.head(last_hidden)

        # Physical boundary: Solar GHI cannot be negative (W/m^2 >= 0)
        return torch.clamp(raw_pred, min=0.0)
