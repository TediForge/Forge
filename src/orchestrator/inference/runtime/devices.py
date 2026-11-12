"""Device configuration validation shared by local backends."""

import re


def validate_device(value: str) -> str:
    if value == "cpu" or value == "cuda" or re.fullmatch(r"cuda:\d+", value):
        return value
    raise ValueError("Inference device must be cpu, cuda, or cuda:<index>.")
