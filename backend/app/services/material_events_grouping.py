"""Group near-duplicate material events: same (ticker, event_type) within a
4-day window collapse into one group (UX-overhaul spec §6). Pure — both
/api/events and the status-board summary consume it.

Window anchoring: groups are seeded by the NEWEST event (input is sorted
filing_date DESC before bucketing), so members join when they fall within
GROUP_WINDOW_DAYS of the group's newest member — not of each other.
"""

GROUP_WINDOW_DAYS = 4


def group_events(events: list) -> list[dict]:
    """events: MaterialEvent rows (any order). Returns groups sorted by
    newest filing_date desc; each: {primary, count, member_ids, headlines}."""
    by_key: dict[tuple, list] = {}
    for ev in sorted(events, key=lambda e: e.filing_date, reverse=True):
        placed = False
        for (ticker, etype, anchor_date), members in by_key.items():
            if (
                ticker == ev.ticker and etype == ev.event_type
                and abs((anchor_date - ev.filing_date).days) <= GROUP_WINDOW_DAYS
            ):
                members.append(ev)
                placed = True
                break
        if not placed:
            by_key[(ev.ticker, ev.event_type, ev.filing_date)] = [ev]
    groups = []
    for members in by_key.values():
        primary = members[0]  # newest — input was sorted desc
        groups.append({
            "primary": primary,
            "count": len(members),
            "member_ids": [str(m.id) for m in members],
            "headlines": [m.headline for m in members],
        })
    groups.sort(key=lambda g: g["primary"].filing_date, reverse=True)
    return groups
