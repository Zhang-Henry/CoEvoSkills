---
name: evo-simpo-loss
description: "Implement the SimPO (Simple Preference Optimization) loss function for the SimPOTrainer class. Use when reproducing the SimPO paper's loss computation, injecting the simpo_loss method into simpo_trainer.py, running unit tests, and generating validated loss outputs."
---

# SimPO Loss Implementation Skill

This skill implements the SimPO loss function based on the SimPO paper for preference optimization of language models.

## Key Concepts

### SimPO Loss Formula

SimPO defines reward as `r(x,y) = (beta/|y|) * log pi_theta(y|x)`, which equals `beta * avg_log_prob`.

The loss inputs are **already length-normalized** average log probabilities from upstream.

**Sigmoid loss** (default):
```
losses = -log_sigmoid(beta * (chosen_logps - rejected_logps) - gamma)
```

With label smoothing epsilon:
```
losses = (1-eps) * (-log_sigmoid(logits - gamma)) + eps * (-log_sigmoid(-(logits - gamma)))
```

**Hinge loss**:
```
losses = max(0, gamma - beta * (chosen_logps - rejected_logps))
```

### Parameters
- `beta`: Scaling constant (default 2.0)
- `gamma_beta_ratio`: Ratio gamma/beta (default 0.25), so `gamma = gamma_beta_ratio * beta`
- `label_smoothing`: Smoothing factor (default 0.0)
- `loss_type`: "sigmoid" or "hinge" (default "sigmoid")

### Rewards (diagnostic only, detached)
- `chosen_rewards = beta * policy_chosen_logps`
- `rejected_rewards = beta * policy_rejected_logps`

## Environment Setup

Required packages with known-good versions:
- torch==2.2.2
- transformers==4.44.2
- trl==0.9.6
- accelerate==0.29.2
- peft==0.7.1
- numpy==1.26.4
- rich (any version)
- datasets (any version)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-simpo-loss/scripts')
from run_task import run_simpo_task

# Run the complete task end-to-end
run_simpo_task(
    project_dir='/root/SimPO',
    output_path='/root/loss.npz',
    python_info_path='/root/python_info.txt',
)
```

This will:
1. Install any missing packages
2. Inject the simpo_loss implementation into simpo_trainer.py
3. Run the unit test to generate loss.npz
4. Log Python version and packages to python_info.txt
5. Validate the output

## Utility Functions

### compute_simpo_loss
Standalone function for computing SimPO loss (useful for testing independently):

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-simpo-loss/scripts')
from utils import compute_simpo_loss
import torch

chosen = torch.tensor([-1.0, -2.0, -0.5])
rejected = torch.tensor([-2.0, -1.5, -1.0])
losses, c_rew, r_rew = compute_simpo_loss(chosen, rejected, beta=2.0, gamma_beta_ratio=0.25)
```

### inject_simpo_loss
Injects the implementation into the trainer file:

```python
from utils import inject_simpo_loss
inject_simpo_loss('/root/SimPO/scripts/simpo_trainer.py')
```

### validate_loss_output
Validates the generated .npz file:

```python
from utils import validate_loss_output
validate_loss_output('/root/loss.npz')
```
