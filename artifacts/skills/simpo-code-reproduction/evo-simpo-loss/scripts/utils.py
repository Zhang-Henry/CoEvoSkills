import torch
import torch.nn.functional as F
from typing import Tuple


def compute_simpo_loss(
    policy_chosen_logps: torch.FloatTensor,
    policy_rejected_logps: torch.FloatTensor,
    beta: float = 2.0,
    gamma_beta_ratio: float = 0.25,
    label_smoothing: float = 0.0,
    loss_type: str = "sigmoid",
) -> Tuple[torch.FloatTensor, torch.FloatTensor, torch.FloatTensor]:
    """Compute SimPO loss for a batch of policy model log probabilities.

    The inputs are already length-normalized average log probabilities
    (normalization is done upstream). This function:
    1. Scales them by beta to form rewards
    2. Computes reward difference
    3. Subtracts the target margin gamma = gamma_beta_ratio * beta
    4. Applies logistic (sigmoid) or hinge loss

    Args:
        policy_chosen_logps: Average log probs for chosen responses. Shape: (batch_size,)
        policy_rejected_logps: Average log probs for rejected responses. Shape: (batch_size,)
        beta: Scaling constant for rewards. Default 2.0.
        gamma_beta_ratio: Ratio of target margin gamma to beta. Default 0.25.
        label_smoothing: Label smoothing factor. Default 0.0.
        loss_type: "sigmoid" or "hinge". Default "sigmoid".

    Returns:
        Tuple of (losses, chosen_rewards, rejected_rewards), each shape (batch_size,).
    """
    gamma = gamma_beta_ratio * beta

    pi_logratios = policy_chosen_logps - policy_rejected_logps
    logits = pi_logratios * beta

    if loss_type == "sigmoid":
        if label_smoothing == 0:
            losses = -F.logsigmoid(logits - gamma)
        else:
            losses = (
                (1 - label_smoothing) * (-F.logsigmoid(logits - gamma))
                + label_smoothing * (-F.logsigmoid(-(logits - gamma)))
            )
    elif loss_type == "hinge":
        losses = torch.relu(gamma - logits)
    else:
        raise ValueError(f"Unknown loss type: {loss_type}")

    chosen_rewards = beta * policy_chosen_logps.detach()
    rejected_rewards = beta * policy_rejected_logps.detach()

    return losses, chosen_rewards, rejected_rewards


def inject_simpo_loss(trainer_path: str) -> None:
    """Inject the simpo_loss implementation into the SimPOTrainer class file.

    Reads the trainer file, finds the simpo_loss method stub, and replaces it
    with the full implementation.

    Args:
        trainer_path: Path to simpo_trainer.py
    """
    import re

    with open(trainer_path, 'r') as f:
        content = f.read()

    new_method = '''    def simpo_loss(
        self,
        policy_chosen_logps: torch.FloatTensor,
        policy_rejected_logps: torch.FloatTensor,
    ) -> Tuple[torch.FloatTensor, torch.FloatTensor, torch.FloatTensor]:
        """Compute the SimPO loss for a batch of policy model log probabilities.

        Args:
            policy_chosen_logps: Log probabilities of the policy model for the chosen responses. Shape: (batch_size,)
            policy_rejected_logps: Log probabilities of the policy model for the rejected responses. Shape: (batch_size,)

        Returns:
            A tuple of three tensors: (losses, chosen_rewards, rejected_rewards).
            The losses tensor contains the SimPO loss for each example in the batch.
            The chosen_rewards and rejected_rewards tensors contain the rewards for the chosen and rejected responses, respectively.
        """
        # Compute the target reward margin
        gamma = self.gamma_beta_ratio * self.beta

        # Compute the logits (reward difference)
        pi_logratios = policy_chosen_logps - policy_rejected_logps
        logits = pi_logratios * self.beta

        # Compute the loss based on the loss type
        if self.loss_type == "sigmoid":
            if self.label_smoothing == 0:
                losses = -F.logsigmoid(logits - gamma)
            else:
                losses = (
                    (1 - self.label_smoothing) * (-F.logsigmoid(logits - gamma))
                    + self.label_smoothing * (-F.logsigmoid(-(logits - gamma)))
                )
        elif self.loss_type == "hinge":
            losses = torch.relu(gamma - logits)
        else:
            raise ValueError(f"Unknown loss type: {self.loss_type}")

        # Compute rewards (detached from computation graph)
        chosen_rewards = self.beta * policy_chosen_logps.detach()
        rejected_rewards = self.beta * policy_rejected_logps.detach()

        return losses, chosen_rewards, rejected_rewards'''

    pattern = r'    def simpo_loss\(.*?return losses, chosen_rewards, rejected_rewards'
    new_content = re.sub(pattern, new_method, content, flags=re.DOTALL)

    with open(trainer_path, 'w') as f:
        f.write(new_content)


def validate_loss_output(npz_path: str) -> bool:
    """Validate the loss output file.

    Args:
        npz_path: Path to the .npz file containing losses.

    Returns:
        True if validation passes.
    """
    import numpy as np

    data = np.load(npz_path)
    assert 'losses' in data, "Key 'losses' not found in npz file"
    losses = data['losses']
    assert losses.ndim == 1, f"Expected 1D array, got {losses.ndim}D"
    assert len(losses) > 0, "Losses array is empty"
    assert np.all(np.isfinite(losses)), "Losses contain non-finite values"
    assert np.all(losses >= 0), "Losses should be non-negative"
    print(f"Validation passed: {len(losses)} loss values, range [{losses.min():.6f}, {losses.max():.6f}]")
    return True
