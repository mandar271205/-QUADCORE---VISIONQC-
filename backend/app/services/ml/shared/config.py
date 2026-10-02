"""Central configuration for reproducible Member 2 experiments."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentConfig:
    image_size: int = 256
    seed: int = 42
    epochs: int = 50
    batch_size: int = 8
    learning_rate: float = 0.001
    percentile: float = 99.0
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.image_size < 16 or self.image_size % 8:
            raise ValueError("image_size must be at least 16 and divisible by 8")
        if self.epochs < 1 or self.batch_size < 1 or self.learning_rate <= 0:
            raise ValueError("epochs, batch size and learning rate must be positive")
        if not 0 < self.percentile <= 100:
            raise ValueError("percentile must be in (0, 100]")
