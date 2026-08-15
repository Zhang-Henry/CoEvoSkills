from pathlib import Path

from libs.terminus_agent.llms.base_llm import BaseLLM


class Chat:
    def __init__(self, model: BaseLLM):
        self._model = model
        self._messages = []
        # Track cumulative tokens across all interactions, even if messages are removed
        self._cumulative_input_tokens = 0
        self._cumulative_output_tokens = 0
        self._last_input_tokens = 0

    @property
    def messages(self) -> list[dict]:
        """Return the current conversation history."""
        return list(self._messages)

    @property
    def total_input_tokens(self) -> int:
        # Return cumulative tokens instead of recalculating from current messages
        return self._cumulative_input_tokens

    @property
    def last_input_tokens(self) -> int:
        """Token count of the most recent LLM call's input (= current context size)."""
        return self._last_input_tokens

    @property
    def total_output_tokens(self) -> int:
        # Return cumulative tokens instead of recalculating from current messages
        return self._cumulative_output_tokens

    def chat(
        self,
        prompt: str,
        logging_path: Path | None = None,
        **kwargs,
    ) -> str:
        # Count input tokens before making the call
        input_tokens = self._model.count_tokens(
            self._messages + [{"role": "user", "content": prompt}]
        )
        self._last_input_tokens = input_tokens

        response = self._model.call(
            prompt=prompt,
            message_history=self._messages,
            logging_path=logging_path,
            **kwargs,
        )

        # Count output tokens from the response
        output_tokens = self._model.count_tokens(
            [{"role": "assistant", "content": response}]
        )

        # Update cumulative counters
        self._cumulative_input_tokens += input_tokens
        self._cumulative_output_tokens += output_tokens

        self._messages.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
        )
        return response

    def replace_last_assistant_response(self, response: str) -> None:
        """Replace the last stored assistant turn with its executable form.

        Structured command agents occasionally emit several imagined future
        JSON turns in one completion. Only the first object is executable. If
        the full completion remains in history, the next call sees fictional
        terminal interactions and tends to repeat or skip work. Token accounting
        intentionally remains based on the provider's full response.
        """
        if not self._messages or self._messages[-1].get("role") != "assistant":
            raise RuntimeError("No assistant response is available to replace")
        self._messages[-1] = {"role": "assistant", "content": response}
