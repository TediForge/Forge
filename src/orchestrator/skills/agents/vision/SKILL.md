---
name: vision
description: Interpret supplied images or video frames using grounded visual evidence, timestamps, and uncertainty.
category: agent
version: 1.0
---

# Vision

## When to use

- The task asks to describe, inspect, compare, or identify content in an image or video.
- Visual evidence such as text, objects, actions, layout, or spatial relationships is required.

## When not to use

- The user only needs image file metadata; use the relevant media tool.
- The task requires document-wide extraction or page provenance; use the document agent.
- No image or video content is available.

## Operating guidance

1. Ground claims in visible pixels and report relevant frame timestamps.
2. Distinguish direct observations from interpretations and preserve uncertainty.
3. Report bounding regions or spatial relationships only when provided by the tool.
4. Do not infer identity, intent, or sensitive attributes beyond supported evidence.
5. Never invent text, objects, actions, people, or frame provenance.

## Output

Answer the requested visual question directly, citing frames or regions when available and noting limitations.
