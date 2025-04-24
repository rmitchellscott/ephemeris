from datetime import datetime, date, time, timedelta
from collections import defaultdict, deque
import pytz
from dateutil.rrule import rrulestr

import ephemeris.settings as settings
from ephemeris.utils import fmt_time


def assign_stacks(events: list[tuple]) -> list[dict]:
    """
    Compute non-overlapping layers and width fractions for events.
    """
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
        cluster_events = [(i, events[i]) for i in cluster]
        # Sort by duration descending, start ascending
        sorted_events = sorted(
            cluster_events,
            key=lambda x: (-(x[1][1] - x[1][0]).total_seconds(), x[1][0])
        )
        layers = []
        assignments = {}
        for idx, (start, end, *_ ) in sorted_events:
            placed = False
            for li, layer in enumerate(layers):
                if all(end <= s or start >= e for s, e in layer):
                    layer.append((start, end))
                    assignments[idx] = li
                    placed = True
                    break
            if not placed:
                layers.append([(start, end)])
                assignments[idx] = len(layers) - 1

        max_depth = len(layers)
        if settings.DEBUG_LAYERS:
            print("🔍 Debug: event layers:")
            for idx, (start, end, title, _) in cluster_events:
                li = assignments[idx]
                ts = lambda dt: dt.astimezone(settings.TZ_LOCAL).strftime("%H:%M")
                print(f"  • Layer {li}: {title} [{ts(start)}→{ts(end)}]")

        for idx, (start, end, title, meta) in cluster_events:
            li = assignments[idx]
            wf = (max_depth - li) / max_depth
            result.append({
                'start': start,
                'end': end,
                'title': title,
                'meta': meta,
                'layer_index': li,
                'width_frac': wf
            })

    return result


def build_override_map(raw_events: list[tuple]) -> dict:
    """
    Map UID to overridden recurrence datetimes.
    """
    override_map = defaultdict(set)
    for comp, *_ in raw_events:
        rid = comp.get('RECURRENCE-ID')
        if rid:
            dt = comp.decoded('RECURRENCE-ID')
            uid = comp.get('UID')
            override_map[uid].add(dt)
    return override_map


def expand_event_for_day(
    comp,
    color: str,
    tz_factory,
    target_date: date,
    tz_local,
    override_map: dict
) -> list[tuple]:
    """
    Expand a VEVENT for one day, handling one-offs, recurrences, and all-day events.
    Returns list of (start_local, end_local, title, meta).
    """
    instances = []
    uid = comp.get('UID')

    # Decode raw DTSTART and DTEND or duration
    start_raw = comp.decoded('dtstart')
    if comp.get('dtend'):
        end_raw = comp.decoded('dtend')
    elif comp.get('duration'):
        end_raw = start_raw + comp.decoded('duration')
    else:
        end_raw = start_raw

    def normalize(dt_raw, param_name):
        # date-only to midnight
        if isinstance(dt_raw, date) and not isinstance(dt_raw, datetime):
            dt = datetime.combine(dt_raw, time.min)
        else:
            dt = dt_raw
        # attach tzinfo if missing
        if isinstance(dt, datetime) and dt.tzinfo is None:
            tzid = comp[param_name].params.get('TZID') if comp.get(param_name) else None
            if tz_factory and tzid:
                try:
                    tzinfo = tz_factory.get(tzid)
                except Exception:
                    tzinfo = pytz.UTC
            else:
                tzinfo = pytz.UTC
            dt = dt.replace(tzinfo=tzinfo)
        # convert to local
        if isinstance(dt, datetime):
            dt = dt.astimezone(tz_local)
        return dt

    start = normalize(start_raw, 'dtstart')
    end   = normalize(end_raw, 'dtend')

    sod      = datetime.combine(target_date, time.min).replace(tzinfo=tz_local)
    sod_next = sod + timedelta(days=1)

    #    Only catch VEVENTs whose raw DTSTART was a date (no time component).
    if isinstance(start_raw, date) and not isinstance(start_raw, datetime):
        # `dtend` for a DATE-valued VEVENT is also a date, and is the day AFTER
        # the last all-day instance.  Only expand if our target_date is in [start_raw, dtend).
        dtend_date = comp.decoded('dtend')
        if isinstance(dtend_date, date):
            if start_raw <= target_date < dtend_date:
                # st = datetime.combine(target_date, time.min).replace(tzinfo=tz_local)
                # en = datetime.combine(target_date + timedelta(days=1), time.min).replace(tzinfo=tz_local)
                st = sod
                en = sod_next
                meta = {'uid': uid, 'calendar_color': color, 'all_day': True}
                return [(st, en, str(comp.get('SUMMARY','')), meta)]
        return []
    # Recurring
    raw_rr = comp.get('RRULE')
    if raw_rr:
        rule = rrulestr(raw_rr.to_ical().decode(), dtstart=start_raw if isinstance(start_raw, datetime) else None)
        # build exdates
        exdates = set()
        ex_prop = comp.get('EXDATE')
        if ex_prop:
            ex_list = ex_prop if isinstance(ex_prop, list) else [ex_prop]
            for prop in ex_list:
                for exdt in getattr(prop, 'dts', []):
                    dt0 = exdt.dt
                    if isinstance(dt0, datetime) and dt0.tzinfo is None:
                        dt0 = dt0.replace(tzinfo=tz_local)
                    exdates.add(dt0)
        for occ in rule.between(sod, sod_next, inc=True):
            if occ in override_map.get(uid, set()) or occ in exdates:
                continue
            st = occ.astimezone(tz_local)
            en = (occ + (end - start)).astimezone(tz_local)
            meta = {'uid': uid, 'calendar_color': color, 'all_day': False}
            instances.append((st, en, str(comp.get('SUMMARY','')), meta))
        return instances

    # One-off
    if isinstance(start, datetime) and start.date() == target_date:
        meta = {'uid': uid, 'calendar_color': color, 'all_day': False}
        instances.append((start, end, str(comp.get('SUMMARY','')), meta))

    return instances


def split_all_day_events(events: list[tuple], target_date: date, tz_local) -> tuple:
    all_day, timed = [], []
    sod = datetime.combine(target_date, time.min).replace(tzinfo=tz_local)
    sod_next = sod + timedelta(days=1)
    for st, en, title, meta in events:
        if meta.get('all_day') or (st <= sod and en >= sod_next):
            all_day.append((st, en, title, meta))
        else:
            timed.append((st, en, title, meta))
    return all_day, timed


def filter_events_for_day(events: list[tuple], target_date: date) -> list[tuple]:
    cancel_variants = ('cancelled','canceled')
    kept = []
    for st, en, title, meta in events:
        local_start = st
        if local_start.date() != target_date:
            continue
        if local_start.hour < settings.EXCLUDE_BEFORE or local_start.hour >= settings.END_HOUR:
            continue
        tl = title.lower()
        status = meta.get('status','').lower()
        if any(v in tl for v in cancel_variants) or status in cancel_variants:
            continue
        duration = (en - st).total_seconds() / 60
        if duration < 15:
            continue
        kept.append((st, en, title, meta))
    return sorted(kept, key=lambda x: x[0])


def compute_events_hash(raw_events: list[tuple]) -> str:
    import copy, hashlib
    items = []
    for comp, color, tzf, name in raw_events:
        comp2 = copy.deepcopy(comp)
        for prop in ('DTSTAMP','CREATED','LAST-MODIFIED','SEQUENCE'):
            comp2.pop(prop, None)
        data = comp2.to_ical()
        items.append((name, data))
    items.sort(key=lambda x: (x[0], hashlib.sha256(x[1]).hexdigest()))
    h = hashlib.sha256()
    for name, data in items:
        h.update(name.encode())
        h.update(data)
    return h.hexdigest()
