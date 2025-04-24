from datetime import datetime, timedelta, date
from collections import defaultdict, deque

from dateutil.rrule import rrulestr

import ephemeris.settings as settings
from ephemeris.utils import css_color_to_hex, fmt_time

def assign_stacks(events):
    # Helper to detect overlap
    def overlaps(e1, e2):
        return e1[0] < e2[1] and e2[0] < e1[1]

    # Build overlap graph
    graph = defaultdict(set)
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if overlaps(events[i], events[j]):
                graph[i].add(j)
                graph[j].add(i)

    # Find clusters via BFS
    visited = set()
    clusters = []
    for i in range(len(events)):
        if i not in visited:
            queue = deque([i])
            cluster = []
            while queue:
                node = queue.popleft()
                if node not in visited:
                    visited.add(node)
                    cluster.append(node)
                    queue.extend(graph[node])
            clusters.append(cluster)

    result = []
    for cluster in clusters:
        # Prepare list of (idx, event)
        cluster_events = [(i, events[i]) for i in cluster]

        # Dynamic layer assignment: longer events first
        layers = []         # list of lists of (start,end)
        assignments = {}    # event idx -> layer index

        # Sort by duration descending, then by start ascending
        sorted_by_duration = sorted(
            cluster_events,
            key=lambda x: (-(x[1][1] - x[1][0]).total_seconds(), x[1][0])
        )

        for idx, (start, end, title, meta) in sorted_by_duration:
            placed = False
            for layer_index, layer in enumerate(layers):
                # if no overlap with existing items in this layer
                if all(end <= s or start >= e for (s, e) in layer):
                    layer.append((start, end))
                    assignments[idx] = layer_index
                    placed = True
                    break
            if not placed:
                # new layer
                layers.append([(start, end)])
                assignments[idx] = len(layers) - 1

        max_depth = len(layers)
        # ── DEBUG DUMP ─────────────────────────────
        if settings.DEBUG_LAYERS:
            print("🔍  Debug: event layers for this cluster:")
            for idx, (start, end, title, meta) in cluster_events:
                li = assignments[idx]              # safe now, idx ∈ cluster
                ts = lambda dt: dt.astimezone(settings.TZ_LOCAL).strftime("%H:%M")
                clean_title = str(title)    # title is your vText instance
                print(f"   • Layer {li}: {clean_title} [{ts(start)} → {ts(end)}]")
            print("🔍  End debug dump\n")
        # ────────────────────────────────────────────

        # Compute width fraction for each event in cluster
        for idx, (start, end, title, meta) in cluster_events:
            layer_index = assignments[idx]
            width_frac  = (max_depth - layer_index) / max_depth
            result.append({
                "start":       start,
                "end":         end,
                "title":       title,
                "meta":        meta,
                "width_frac":  width_frac,
                "layer_index": layer_index
            })

    return result

def build_override_map(raw_events: list[tuple]) -> dict:
    """
    Build a mapping from event UID to a set of overridden recurrence datetimes.
    """
    override_map = defaultdict(set)
    for comp, _, _, _ in raw_events:
        rid = comp.get('RECURRENCE-ID')
        if rid:
            dt = comp.decoded('RECURRENCE-ID')
            uid = comp.get('UID')
            override_map[uid].add(dt)
    return override_map


def expand_event_for_day(
    comp,
    color,
    tz_factory,
    target_date: date,
    tz_local,
    override_map: dict
) -> list[tuple]:
    from datetime import datetime, timedelta, time
    import pytz
    from dateutil.rrule import rrulestr

    instances = []
    uid        = comp.get("UID")

    # 0) Decode raw start/end and attach tzinfo
    start = comp.decoded("dtstart")
    end   = comp.decoded("dtend") if comp.get("dtend") \
            else start + comp.decoded("duration") if comp.get("duration") \
            else start

    # Normalize start
    if isinstance(start, datetime) and start.tzinfo is None:
        tzid = comp['dtstart'].params.get('TZID')
        if tz_factory and tzid:
            try:
                tzinfo = tz_factory.get(tzid)
            except Exception:
                tzinfo = pytz.UTC
        else:
            tzinfo = pytz.UTC
        start = start.replace(tzinfo=tzinfo)
    start = start.astimezone(tz_local)

    # Normalize end the same way
    if isinstance(end, datetime) and end.tzinfo is None:
        tzid_end = comp.get('dtend', comp.get('dtstart')).params.get('TZID')
        if tz_factory and tzid_end:
            try:
                tzinfo = tz_factory.get(tzid_end)
            except Exception:
                tzinfo = pytz.UTC
        else:
            tzinfo = pytz.UTC
        end = end.replace(tzinfo=tzinfo)
    end = end.astimezone(tz_local)


    tzid = comp["dtstart"].params.get("TZID")
    for dt in (start, end):
        if dt.tzinfo is None:
            if tz_factory and tzid in tz_factory._ttinfo_cache:
                dt = dt.replace(tzinfo=tz_factory.get(tzid))
            else:
                dt = dt.replace(tzinfo=pytz.UTC)

    # 1) All-day (flagged or spans midnight)
    start_local = start.astimezone(tz_local)
    end_local   = end.astimezone(tz_local)
    sod         = datetime.combine(target_date, time.min).replace(tzinfo=tz_local)
    sod_next    = sod + timedelta(days=1)
    is_flagged  = comp.get("DTSTART").params.get("VALUE") == "DATE"
    spans_mid   = (start_local <= sod and end_local >= sod_next)
    if is_flagged or spans_mid:
        meta = {"uid": uid, "calendar_color": color, "all_day": True}
        return [(sod, sod_next, str(comp.get("SUMMARY","")), meta)]

    # 2) Recurring?
    raw_rr = comp.get("RRULE")
    if raw_rr:
        rule = rrulestr(raw_rr.to_ical().decode(), dtstart=start)
        day_start = sod
        day_end   = sod_next
        exdates = set()
        ex_prop = comp.get("EXDATE")
        if ex_prop:
            ex_props = ex_prop if isinstance(ex_prop, list) else [ex_prop]
            for p in ex_props:
                for exdt in getattr(p, "dts", []):
                    dt0 = exdt.dt
                    if isinstance(dt0, datetime) and dt0.tzinfo is None:
                        dt0 = dt0.replace(tzinfo=tz_local)
                    exdates.add(dt0)

        for occ in rule.between(day_start, day_end, inc=True):
            if occ in override_map.get(uid, set()) or occ in exdates:
                continue
            st_local = occ.astimezone(tz_local)
            en_local = (occ + (end - start)).astimezone(tz_local)
            meta     = {"uid": uid, "calendar_color": color, "all_day": False}
            instances.append((st_local, en_local, str(comp.get("SUMMARY","")), meta))

        return instances

    # 3) One-off
    if start_local.date() == target_date:
        meta = {"uid": uid, "calendar_color": color, "all_day": False}
        instances.append((start_local, end_local, str(comp.get("SUMMARY","")), meta))

    return instances


def split_all_day_events(events: list[tuple], target_date: date, tz_local) -> tuple:
    """
    Separate events into all-day and timed lists.
    """
    all_day = []
    timed = []
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz_local)
    start_of_next = start_of_day + timedelta(days=1)
    for st, en, title, meta in events:
        if meta.get('all_day') or (st <= start_of_day and en >= start_of_next):
            all_day.append((st, en, title, meta))
        else:
            timed.append((st, en, title, meta))
    return all_day, timed


def filter_events_for_day(events, target_date):
    cancel_variants = ("cancelled","canceled")
    kept = []
    for st, en, title, meta in events:
        local_start = st.astimezone(settings.TZ_LOCAL)

        if local_start.date() != target_date:
            continue
        if local_start.hour < settings.EXCLUDE_BEFORE:
            print(f"⏰ Dropped (too early): {title!r} @ {fmt_time(local_start)}")
            continue
        if local_start.hour >= settings.END_HOUR:
            print(f"⏰ Dropped (after end): {title!r} @ {fmt_time(local_start)}")
            continue

        title_lower = title.lower()
        status = meta.get("status","").lower()
        if any(v in title_lower for v in cancel_variants) or status in cancel_variants:
            print(f"❌ Dropped (cancelled): {title!r}")
            continue

        duration = (en - st).total_seconds() / 60
        if duration < 15:
            print(f"⌛ Dropped (too short {duration:.1f} min): {title!r}")
            continue

        kept.append((st, en, title, meta))

    return sorted(kept, key=lambda x: x[0])


def compute_events_hash(raw_events: list[tuple]) -> str:
    """
    Deterministically hash VEVENT components to detect changes.
    """
    import copy, hashlib
    items = []
    for comp, color, tzf, name in raw_events:
        comp2 = copy.deepcopy(comp)
        for prop in ("DTSTAMP", "CREATED", "LAST-MODIFIED", "SEQUENCE"):
            comp2.pop(prop, None)
        data = comp2.to_ical()
        items.append((name, data))
    items.sort(key=lambda x: (x[0], hashlib.sha256(x[1]).hexdigest()))
    h = hashlib.sha256()
    for name, data in items:
        h.update(name.encode())
        h.update(data)
    return h.hexdigest()
