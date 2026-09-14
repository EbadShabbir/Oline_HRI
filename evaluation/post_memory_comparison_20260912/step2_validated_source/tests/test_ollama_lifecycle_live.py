"""Opt-in model-residency smoke test for the local Ollama service."""

from dataclasses import replace
import json
import os
import time
import unittest
from urllib.request import ProxyHandler, Request, build_opener

from oline_hri.config import load_config
from oline_hri.ollama import ChatMessage, OllamaClient


RUN_LIVE = os.environ.get("OLINE_HRI_RUN_LIVE_LIFECYCLE") == "1"


@unittest.skipUnless(
    RUN_LIVE,
    "set OLINE_HRI_RUN_LIVE_LIFECYCLE=1 to switch real local models",
)
class LiveOllamaLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        config = load_config()
        self.ollama = config.ollama
        generation = replace(
            config.generation,
            max_output_tokens=8,
            temperature=0.0,
        )
        self.client = OllamaClient(self.ollama, generation)
        self.models = {
            self.ollama.small_model,
            self.ollama.general_large_model,
            self.ollama.large_model,
        }
        self.opener = build_opener(ProxyHandler({})).open
        self._unload_configured_models()
        self._wait_for_models(set())

    def tearDown(self) -> None:
        self._unload_configured_models()
        self._wait_for_models(set())

    def test_small_large_small_never_overlap_residency(self) -> None:
        message = (ChatMessage(role="user", content="Reply with only OK."),)

        first_small = self.client.chat(self.ollama.small_model, message)
        self.assertEqual(first_small.model, self.ollama.small_model)
        self._wait_for_models({self.ollama.small_model})

        large = self.client.chat(
            self.ollama.general_large_model, message
        )
        self.assertEqual(
            large.model, self.ollama.general_large_model
        )
        self._wait_for_models(set())

        second_small = self.client.chat(self.ollama.small_model, message)
        self.assertEqual(second_small.model, self.ollama.small_model)
        self._wait_for_models({self.ollama.small_model})

    def _unload_configured_models(self) -> None:
        for model in dict.fromkeys(
            (
                self.ollama.large_model,
                self.ollama.general_large_model,
                self.ollama.small_model,
            )
        ):
            request = Request(
                f"{self.ollama.base_url}/api/generate",
                data=json.dumps(
                    {
                        "model": model,
                        "prompt": "",
                        "stream": False,
                        "keep_alive": 0,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.opener(
                request, timeout=self.ollama.unload_timeout_seconds
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if (
                payload.get("model") != model
                or payload.get("done") is not True
                or payload.get("done_reason") != "unload"
            ):
                raise AssertionError(f"failed to unload configured model: {model}")

    def _running_configured_models(self) -> set[str]:
        request = Request(f"{self.ollama.base_url}/api/ps", method="GET")
        with self.opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("models")
        if not isinstance(models, list):
            raise AssertionError("Ollama /api/ps returned an invalid model list")

        running = set()
        for item in models:
            if not isinstance(item, dict):
                raise AssertionError("Ollama /api/ps returned an invalid model item")
            for key in ("name", "model"):
                value = item.get(key)
                if value in self.models:
                    running.add(value)
        return running

    def _wait_for_models(self, expected: set[str]) -> None:
        deadline = time.monotonic() + 10
        while True:
            running = self._running_configured_models()
            if running == expected:
                return
            if time.monotonic() >= deadline:
                self.fail(
                    "configured Ollama residency did not settle: "
                    f"expected {sorted(expected)}, found {sorted(running)}"
                )
            time.sleep(0.2)


if __name__ == "__main__":
    unittest.main()
