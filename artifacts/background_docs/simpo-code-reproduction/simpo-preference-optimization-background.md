# SimPO: Preference Optimization Loss Functions

This document provides background on preference optimization for language model alignment, focusing on the mathematical derivation and implementation mechanics of the SimPO (Simple Preference Optimization) loss. Understanding these concepts is essential for correctly reproducing the SimPO loss function from the paper.

## From RLHF to Direct Preference Optimization

Reinforcement Learning from Human Feedback (RLHF) aligns language models with human preferences through a multi-stage pipeline: supervised fine-tuning (SFT), reward model training, and policy optimization (typically via PPO). Direct Preference Optimization (DPO) collapses the reward model and policy optimization stages into a single step by reparameterizing the reward function using the optimal policy.

In DPO, the implicit reward for a response `y` given prompt `x` is defined as:

The implicit reward is `r(x, y) = beta * log(pi_theta(y | x) / pi_ref(y | x)) + beta * log Z(x)`.

where `pi_theta` is the policy model, `pi_ref` is a reference model (typically the SFT checkpoint), and `Z(x)` is a partition function. The DPO objective uses the Bradley-Terry model to express the probability that a winning response `y_w` is preferred over a losing response `y_l`:

The probability that the winning response is preferred is `p(y_w > y_l | x) = sigma(r(x, y_w) - r(x, y_l))`, where `sigma` is the logistic sigmoid function. The DPO training loss becomes the negative expected log of sigma applied to the difference of log-ratios: `L_DPO = -E[ log sigma( beta * log(pi_theta(y_w|x)/pi_ref(y_w|x)) - beta * log(pi_theta(y_l|x)/pi_ref(y_l|x)) ) ]`.

A critical drawback of DPO is that it requires a reference model `pi_ref` to be loaded in memory during training, roughly doubling GPU memory requirements.

## The Reward-Generation Discrepancy

A subtler problem with DPO is the mismatch between its training objective and the metric used during generation. The DPO reward is a log-ratio of policy and reference likelihoods, but during inference (text generation), the model uses the average log-likelihood of its own policy to rank candidate outputs. This means the reward being optimized during training does not directly correspond to the ranking criterion used at inference time. Empirically, only about half of the preference pairs where `r(x, y_w) > r(x, y_l)` also satisfy the condition that the policy's average log-likelihood ranks the winning response higher.

## SimPO: Aligning Reward with Generation

SimPO addresses both problems -- the reference model requirement and the reward-generation discrepancy -- by redefining the implicit reward to use the **average log probability** of the policy model alone.

### Length-Normalized Reward

SimPO defines its reward as:

The SimPO reward is `r_SimPO(x, y) = (beta / |y|) * log pi_theta(y | x)`, which expands to `(beta / |y|) * sum_{i=1}^{|y|} log pi_theta(y_i | x, y_{<i})`.

Here `|y|` is the number of tokens in the response, `beta` is a scaling constant, and `log pi_theta(y | x)` is the total log probability of the response under the policy. Dividing by `|y|` yields the **average** log probability per token.

This length normalization is critical. Without it, the summed log probability would be used as the reward, which introduces a **length bias**: longer sequences naturally have lower total log probabilities (since each token multiplication adds a factor less than 1). This means optimizing the summed log probability as a reward would force the model to artificially inflate probabilities for longer sequences, leading to degenerate outputs.

### Target Reward Margin (gamma)

SimPO introduces a target reward margin `gamma > 0` into the Bradley-Terry preference model. Instead of simply requiring the winning response to have a higher reward than the losing response, SimPO requires the reward gap to exceed `gamma`:

The margin-augmented preference probability is `p(y_w > y_l | x) = sigma(r(x, y_w) - r(x, y_l) - gamma)`.

The margin acts like the margin in support vector machines: it pushes the model to learn a clear separation between preferred and dispreferred responses, which generally improves generalization. Too small a margin provides weak signal; too large a margin can degrade quality by over-constraining the optimization.

## The SimPO Loss (Full Derivation)

Substituting the length-normalized reward into the margin-augmented Bradley-Terry objective gives the complete SimPO loss:

The complete SimPO loss is `L_SimPO = -E[ log sigma( (beta/|y_w|) * log pi_theta(y_w | x) - (beta/|y_l|) * log pi_theta(y_l | x) - gamma ) ]`.

In the standard implementation, the inputs to the loss function are **already** the average log probabilities. Specifically, the upstream method that computes batch log probabilities with the average flag enabled produces:

Specifically, the chosen log probabilities equal `(1/|y_w|)` times the sum of per-token log probabilities for the chosen response, and the rejected log probabilities equal `(1/|y_l|)` times the sum of per-token log probabilities for the rejected response.

Therefore, by the time these values reach the loss function, the length normalization has already been applied. The loss function itself needs to:

1. Scale these average log probabilities by `beta` to form rewards.
2. Compute the difference between chosen and rejected rewards.
3. Subtract the target margin `gamma`.
4. Apply the logistic loss (negative log sigmoid).

### Relationship Between gamma and gamma_beta_ratio

The standard parameterization stores the margin not as a raw `gamma` value but as the ratio `gamma / beta`, referred to as gamma_beta_ratio. This design choice makes tuning easier because the effective margin scales naturally with `beta`. To recover the actual `gamma` used in the loss formula:

The actual gamma is computed as `gamma = gamma_beta_ratio * beta`.

This means if `beta = 2.0` and `gamma_beta_ratio = 0.5`, the effective margin is `gamma = 1.0`.

## Loss Variants: Sigmoid vs. Hinge

The SimPO implementation supports two loss types:

**Sigmoid loss** (default): This is the standard logistic loss derived from the Bradley-Terry model:

The sigmoid loss is computed as `losses = -log sigma( beta * (policy_chosen_logps - policy_rejected_logps) - gamma )`.

where `sigma(z) = 1 / (1 + exp(-z))`. Note that `-log sigma(z) = log(1 + exp(-z))`, which is equivalent to computing the negative of the log-sigmoid of the logits difference.

**Hinge loss**: An alternative max-margin formulation that does not use the probabilistic Bradley-Terry framework:

The hinge loss is computed as `losses = max(0, -beta * (policy_chosen_logps - policy_rejected_logps) + gamma)`.

The hinge loss produces zero gradient once the reward gap exceeds the margin, whereas the sigmoid loss always provides some gradient signal (though it diminishes as the gap grows). When using hinge loss, the label smoothing parameter is not applicable.

## Label Smoothing

The SimPO loss supports label smoothing, which softens the binary preference signal. With label smoothing parameter `epsilon`, the loss is interpolated between the loss for the original label ordering and the reversed ordering:

The smoothed loss is `smoothed_loss = (1 - epsilon) * loss(chosen_preferred) + epsilon * loss(rejected_preferred)`.

In practice, this means computing the logistic loss for both the "chosen is better" direction and the "rejected is better" direction, then combining them with weights `(1 - epsilon)` and `epsilon`. When `epsilon = 0`, this reduces to the standard unsmoothed loss.

## Reward Computation

Beyond the loss itself, the loss function must also return reward values for both the chosen and rejected responses. These are used for logging and metrics (reward accuracy, reward margins) but do not directly affect the gradient.

The rewards are the scaled average log probabilities, detached from the computation graph:

The chosen rewards are `beta * policy_chosen_logps` and the rejected rewards are `beta * policy_rejected_logps`.

These represent the implicit rewards assigned by the SimPO formulation. The reward accuracy metric (fraction of pairs where chosen reward exceeds rejected reward) tracks how well the model has learned the preference ordering. The rewards are detached (no gradient flows through them) because they are purely diagnostic.

## The Role of Average Log Probabilities as Input

A key implementation detail: the upstream forward method computes per-token log probabilities using the log-softmax of the logits tensor, then gathers the values corresponding to the target token indices, and averages over non-padding tokens by dividing the masked sum by the count of valid tokens.

This means the chosen and rejected log probabilities arriving at the loss function are already **per-token averages**, not raw sums. The `beta` scaling in the loss formula converts these averages into rewards. No additional length normalization should be applied inside the loss function -- it has already been done upstream.

## Key Distinctions in Practice

**Length normalization is applied upstream, not in the loss function.** The upstream computation already produces average log probabilities (dividing by response length), so the loss function operates on these averages directly. The formula in the paper shows `beta / |y|` multiplied by the total log probability, which is mathematically equivalent to `beta` multiplied by the average log probability. Both forms yield the same result, and the standard implementation uses the latter representation.

**The gamma parameter is derived from gamma_beta_ratio.** The configuration stores gamma_beta_ratio (the ratio of gamma to beta), not gamma directly. The actual margin value used in the loss is computed by multiplying gamma_beta_ratio by beta. Using gamma_beta_ratio directly as the margin would understate it significantly when beta exceeds 1.

**The sigmoid direction determines optimization polarity.** The loss is the negative log-sigmoid of the logits difference, where the logits difference equals beta times the difference between chosen and rejected log probabilities, minus gamma. A sign error in this computation (such as negating the logits difference or swapping chosen and rejected) would cause the model to optimize in the wrong direction, reinforcing dispreferred responses instead of preferred ones.

**Rewards are diagnostic quantities, not gradient-carrying tensors.** The chosen and rejected rewards returned from the loss function are used only for logging metrics such as reward accuracy and reward margins. They are detached from the computation graph and do not participate in backpropagation. This detachment is standard practice for auxiliary metrics that should not influence the training gradient.

**Label smoothing alters the loss structure.** When label smoothing is greater than zero, the loss is not simply the negative log-sigmoid of the logits difference. The smoothed version interpolates between the forward and reverse preference directions, and implementing only the unsmoothed form will produce incorrect numerical results whenever a non-zero smoothing value is specified.

**Output dimensionality matches input dimensionality.** The loss function receives inputs of shape (batch_size,) and returns three tensors each of shape (batch_size,) -- losses, chosen rewards, and rejected rewards. Reducing across the batch dimension inside the loss function (for example by computing the mean prematurely) would produce a scalar instead of per-example tensors, which would be incompatible with downstream code that applies its own reduction.
