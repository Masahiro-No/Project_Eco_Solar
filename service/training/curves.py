"""Learning curves of a retrain run: one value per epoch, logged to MLflow.

Same idea as the TensorBoard scalars of the course (training log, learning-rate plot, "how do you notice the
network converge?"), kept in the MLflow server the system already runs. A run's history is a list of
{"epoch": n, "<name>": value, ...}; every number is logged as metric `epoch_<name>` with step = epoch, so the
MLflow UI and the retrain page can draw loss, validation metric and learning rate against the epoch.
Epoch 0 is the deployed model before any update.
"""

from typing import Any, Iterable

PREFIX = "epoch_"


def log_history(mlflow: Any, history: Iterable[dict], skip: Iterable[str] = ()) -> int:
    """Log every numeric value of the history rows; returns how many points were logged."""
    skip = {"epoch", *skip}
    logged = 0
    for row in history or []:
        step = int(row.get("epoch", 0))
        for key, value in row.items():
            if key in skip or isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
                continue
            mlflow.log_metric(PREFIX + key, float(value), step=step)
            logged += 1
    return logged
