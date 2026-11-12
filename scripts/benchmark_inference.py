"""Measure local text-model startup, first-token latency, and concurrent requests."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from orchestrator.inference.gateway import InferenceGateway
from orchestrator.inference.protocols import InferenceRequest
from orchestrator.settings import Settings


async def benchmark(model_path: Path) -> dict[str, float | int]:
    gateway_started = time.perf_counter()
    gateway = InferenceGateway(settings=Settings(
        inference_model_sources={
            "text": {"type": "localpath", "locator": str(model_path.resolve())},
        },
    ))
    gateway_init_ms = (time.perf_counter() - gateway_started) * 1000
    try:
        request = InferenceRequest(
            "text", "text", "Reply with one short sentence.",
            {"max_new_tokens": 32},
        )
        first_token_started = time.perf_counter()
        stream = gateway.stream(request)
        try:
            first_token = await stream.__anext__()
        except StopAsyncIteration as exc:
            raise RuntimeError("The local text model returned no stream tokens") from exc
        finally:
            await stream.aclose()
        first_token_ms = (time.perf_counter() - first_token_started) * 1000

        concurrent_started = time.perf_counter()
        responses = await asyncio.gather(*(
            gateway.infer(InferenceRequest(
                "text", "text", f"Reply briefly to request {index}.",
                {"max_new_tokens": 32},
            ))
            for index in range(5)
        ))
        concurrent_request_ms = (time.perf_counter() - concurrent_started) * 1000
        if len(responses) != 5 or any(not str(response.output).strip() for response in responses):
            raise RuntimeError("Five concurrent local inference requests did not all succeed")
        if not first_token.strip():
            raise RuntimeError("The local text model returned an empty first token")
        return {
            "gateway_cold_start_ms": round(gateway_init_ms, 3),
            "first_token_ms": round(first_token_ms, 3),
            "concurrent_requests": len(responses),
            "concurrent_requests_ms": round(concurrent_request_ms, 3),
        }
    finally:
        await gateway.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-path",
        required=True,
        type=Path,
        help="path to a locally available Transformers text-model directory (no download)",
    )
    args = parser.parse_args()
    if not args.model_path.is_dir():
        parser.error(f"model path is not a directory: {args.model_path}")
    print(json.dumps(asyncio.run(benchmark(args.model_path)), indent=2))


if __name__ == "__main__":
    main()
