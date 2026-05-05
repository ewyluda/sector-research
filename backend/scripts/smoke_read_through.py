"""Smoke test for the read-through engine.

Seeds a synthetic earnings catalyst against a peer ticker that has at
least one outbound or inbound relationship row to a status-board ticker,
runs the resolver, asserts the synthetic event surfaces, then cleans up.

Usage (from project root with venv active):
    PYTHONPATH=. python backend/scripts/smoke_read_through.py
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.db import async_session
from backend.app.models.catalyst import Catalyst
from backend.app.models.filing import Relationship
from backend.app.models.read_through_dismissal import ReadThroughDismissal
from backend.app.services.read_through import (
    compute_peer_events,
    resolve_read_throughs,
)
from backend.app.services.status_board import build_status_board


async def main() -> None:
    async with async_session() as db:
        # Pick the first status-board entry to target.
        board = await build_status_board(db)
        if not board.entries:
            print("SKIP: status board is empty — seed at least one completed run first.")
            return
        target = board.entries[0]
        print(f"target: {target.ticker} (run {target.run_id})")

        # Find a peer ticker that has a relationship edge to/from the target.
        # Project convention: relationships.ticker and resolved_to_ticker are
        # stored uppercase (see edgar_relationships.py / counterparty_resolver).
        target_t = target.ticker.upper()
        rel_q = (
            select(Relationship.resolved_to_ticker, Relationship.ticker)
            .where(
                (Relationship.ticker == target_t)
                | (Relationship.resolved_to_ticker == target_t)
            )
            .limit(50)
        )
        rel_rows = (await db.execute(rel_q)).all()
        peers = {
            (r.upper() if r else None) or (t.upper() if t else None)
            for r, t in rel_rows
            if (r or t)
        }
        peers.discard(None)
        peers.discard(target_t)
        if not peers:
            print(f"SKIP: no relationship rows for {target.ticker}.")
            return
        peer_ticker = next(iter(peers))
        print(f"peer: {peer_ticker}")

        # Seed a synthetic earnings catalyst on the peer.
        synthetic_run_id = target.run_id
        synth = Catalyst(
            id=str(uuid.uuid4()),
            run_id=synthetic_run_id,
            ticker=peer_ticker,
            ordinal=999,
            timeframe="next 30d (synthetic)",
            description="SMOKE TEST earnings catalyst",
            type="earnings",
            signposts=[],
            linked_pillar=None,
            expected_date=date.today() + timedelta(days=5),
            expected_window_start=date.today() + timedelta(days=5),
            expected_window_end=date.today() + timedelta(days=7),
            date_source="smoke",
        )
        db.add(synth)
        await db.commit()
        print(f"seeded synthetic catalyst id={synth.id}")

        try:
            # Run the engine.
            now = datetime.now(timezone.utc)
            events = await compute_peer_events(db, now - timedelta(days=30), now + timedelta(days=30))
            event_keys = [e.event_key for e in events]
            expected_key = f"earnings:{peer_ticker}:{synth.expected_window_start.isoformat()}"
            assert expected_key in event_keys, f"missing synthetic key: {expected_key}"
            print(f"PASS: synthetic event present ({len(events)} total)")

            resolved = await resolve_read_throughs(db, [target.run_id], events)
            target_items = resolved.get(target.run_id, [])
            matched = [it for it in target_items if it.event_key == expected_key]
            assert matched, f"resolver did not surface synthetic event for {target.run_id}"
            print(f"PASS: resolver surfaced synthetic event with {len(matched[0].links)} link(s)")

            # Test dismissal filtering.
            dismissal = ReadThroughDismissal(
                id=str(uuid.uuid4()),
                run_id=target.run_id,
                event_key=expected_key,
            )
            db.add(dismissal)
            await db.commit()
            print("seeded dismissal")

            resolved2 = await resolve_read_throughs(db, [target.run_id], events)
            target_items2 = resolved2.get(target.run_id, [])
            still_matched = [it for it in target_items2 if it.event_key == expected_key]
            assert not still_matched, "dismissed event should be filtered out"
            print("PASS: dismissal filtered the synthetic event")

            # Cleanup dismissal.
            await db.delete(dismissal)
            await db.commit()
        finally:
            # Cleanup synthetic catalyst.
            await db.delete(synth)
            await db.commit()
            print("cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
