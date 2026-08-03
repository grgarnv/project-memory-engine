"""
Ordering.

The read path exposed a defect worth stating plainly: memory carried no time,
so `SingleOccupancyDecisionRule` retired whatever happened to already be in the
store. Replaying the same artifacts in a different order inverted what the
project believed. Append-only memory was monotonic in content but not in
meaning.

This module is the fix. Every supersession decision routes through
`compare_assertions`, which answers "which of these two assertions came later?"
using artifact timestamps when they exist, and says so explicitly when they do
not.

Three outcomes:

    LATER    the incoming assertion post-dates the stored one -> it supersedes
    EARLIER  the incoming assertion pre-dates the stored one  -> IT is superseded
    UNKNOWN  no usable timestamps                             -> fall back to
             ingestion order and mark the edge `basis="ingestion_order"`

The EARLIER case is what makes backfill safe: importing a ten-year archive in
arbitrary order converges on the same beliefs as importing it chronologically.
The UNKNOWN case is not silently equivalent to LATER - it is recorded on the
edge, counted, and surfaced by the resolver, because a memory whose beliefs
rest on replay order should say so rather than look confident.
"""
from __future__ import annotations

from enum import Enum


class Order(Enum):
    LATER = "later"
    EARLIER = "earlier"
    SIMULTANEOUS = "simultaneous"
    UNKNOWN = "unknown"


BASIS_TIME = "recorded_at"
BASIS_INGESTION = "ingestion_order"


def compare_assertions(incoming_at: str, stored_at: str) -> Order:
    """
    Compare two ISO-8601 timestamps.

    Compared as strings on purpose: ISO-8601 sorts lexicographically, and
    parsing introduces timezone ambiguity for no benefit. Empty means unknown.
    """
    if not incoming_at or not stored_at:
        return Order.UNKNOWN
    if incoming_at > stored_at:
        return Order.LATER
    if incoming_at < stored_at:
        return Order.EARLIER
    return Order.SIMULTANEOUS


def basis_for(order: Order) -> str:
    return BASIS_TIME if order in (Order.LATER, Order.EARLIER) else BASIS_INGESTION
