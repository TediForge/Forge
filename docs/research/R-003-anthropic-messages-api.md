# R-003: Anthropic Messages API

- **Date checked:** 2026-11-11
- **Purpose:** Compare a major provider's documented message API shape.

## Findings

Anthropic documents a Messages API accepting structured messages and
supporting stateless multi-turn conversations. This is a separate provider
contract; it does not define Forge's public API or require an Anthropic
integration.

## Source

- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages)

## Application

This source is comparative research only. Forge service credentials and
provider-specific adapters remain outside the speech tools and caller-owned
external integrations.
