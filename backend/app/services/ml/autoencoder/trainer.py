"""GOOD-only training, without any benchmark test access."""
from pathlib import Path
import torch
from app.services.ml.shared.data import validate_good
from app.services.ml.shared.preprocessing import read_rgb, tensor, seed_everything


def train(model, paths: list[Path], config) -> list[float]:
    validate_good(paths)
    seed_everything(config.seed)
    samples = torch.cat([tensor(read_rgb(p, config.image_size), "cpu") for p in paths])
    generator = torch.Generator().manual_seed(config.seed)
    loader = torch.utils.data.DataLoader(samples, batch_size=config.batch_size,
                                         shuffle=True, generator=generator)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    history = []
    model.train()
    for _ in range(config.epochs):
        total = 0.0
        for batch in loader:
            batch = batch.to(config.device)
            optimizer.zero_grad()
            loss = torch.nn.functional.mse_loss(model(batch), batch)
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * len(batch)
        history.append(total / len(samples))
    model.eval()
    return history
