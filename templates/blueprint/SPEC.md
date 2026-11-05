# {{BLUEPRINT_NAME}} specification

## Mission

Provide a runnable starting point for a new co-worker. Replace this section
with its real mission before publishing it in the catalog.

## Current behavior

One bounded batch step, `do_nothing`, invokes `domain.noop:run` through the
stock domain-operation block and returns `{}`. There are no required inputs,
domain artifacts, model calls, network requests or external actions. The
runtime owns execution state and its normal coordination receipts.

## Acceptance

The canonical package validates and compiles. The empty hook test passes.
A run completes the single step without requesting a GPU or performing domain
work. Chat and MCP supervision use the standard runtime extensions.

## Limits

This starter solves no domain problem and makes no accuracy or completion
claim beyond the no-op step. Define real outcomes, evidence, permissions,
approval rules and failure behavior before adding capabilities.
