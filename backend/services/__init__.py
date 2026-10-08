"""Adapters for the systems OFS talks to but does not own: the payment
gateway, the mapping service, and the delivery vehicle.

Each module exposes one interface and picks its implementation from an
environment variable, so the rest of OFS never changes when a provider
does. The fake implementations are the defaults: they work offline,
cost nothing, and always give the same answer for the same input, which
is what the tests need (backlog item T-05).
"""
