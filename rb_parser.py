import mido
import json
import os
import re
import math
from collections import Counter

def build_tempo_map(mid):
    tempo_events = []
    ticks_per_beat = mid.ticks_per_beat

    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                tempo_events.append({'tick': current_tick, 'tempo': msg.tempo})

    tempo_events.sort(key=lambda x: x['tick'])

    filtered_tempo_map = []
    for ev in tempo_events:
        if filtered_tempo_map and filtered_tempo_map[-1]['tick'] == ev['tick']:
            filtered_tempo_map[-1] = ev
        else:
            filtered_tempo_map.append(ev)

    return filtered_tempo_map

def ticks_to_seconds(tick, tempo_map, ticks_per_beat):
    if not tempo_map:
        return round(mido.tick2second(tick, ticks_per_beat, 500000), 4)

    accumulated_time = 0.0
    last_tick = 0
    active_tempo = 500000

    for tempo_event in tempo_map:
        if tick <= tempo_event['tick']:
            break
        delta_ticks = tempo_event['tick'] - last_tick
        accumulated_time += mido.tick2second(delta_ticks, ticks_per_beat, active_tempo)
        last_tick = tempo_event['tick']
        active_tempo = tempo_event['tempo']

    remaining_ticks = tick - last_tick
    accumulated_time += mido.tick2second(remaining_ticks, ticks_per_beat, active_tempo)
    return round(accumulated_time, 4)

def get_track_name(track):
    for msg in track:
        if msg.type == 'track_name':
            return msg.name.strip().upper()
    return getattr(track, 'name', '').strip().upper()


def build_time_signature_map(mid):
    ts_events = []
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'time_signature':
                ts_events.append({'tick': current_tick, 'num': msg.numerator, 'den': msg.denominator})

    ts_events.sort(key=lambda x: x['tick'])

    filtered = []
    for ev in ts_events:
        if filtered and filtered[-1]['tick'] == ev['tick']:
            filtered[-1] = ev
        else:
            filtered.append(ev)

    if not filtered or filtered[0]['tick'] != 0:
        filtered.insert(0, {'tick': 0, 'num': 4, 'den': 4})

    return filtered


def get_tempo_bpm_at_tick(tick, tempo_map):
    active_tempo = 500000  # default 120bpm
    for ev in tempo_map:
        if ev['tick'] > tick:
            break
        active_tempo = ev['tempo']
    return round(mido.tempo2bpm(active_tempo), 4)


ALLOWED_NOTE_VALUES = [1, 2, 4, 8, 16, 32]

def seconds_to_note_value(duration_seconds, bpm):
    if duration_seconds <= 0 or bpm <= 0:
        return 32
    quarter_note_seconds = 60.0 / bpm
    duration_in_quarters = duration_seconds / quarter_note_seconds
    if duration_in_quarters <= 0:
        return 32
    ideal = 4.0 / duration_in_quarters
    return min(ALLOWED_NOTE_VALUES, key=lambda v: abs(math.log2(v) - math.log2(ideal)))


def build_measure_boundaries(ts_map, ticks_per_beat, end_tick):
    measures = []
    current_tick = 0
    ts_idx = 0
    while current_tick <= end_tick:
        while ts_idx + 1 < len(ts_map) and ts_map[ts_idx + 1]['tick'] <= current_tick:
            ts_idx += 1
        num = ts_map[ts_idx]['num']
        den = ts_map[ts_idx]['den']
        measures.append((current_tick, num, den))
        measure_ticks = int(round(ticks_per_beat * 4 * num / den))
        if measure_ticks <= 0:
            measure_ticks = ticks_per_beat * 4
        current_tick += measure_ticks
    return measures


# --- ANCHOR COMPUTATION FOR PRO GUITAR / BASS ---
def compute_anchors(notes, window_seconds=2.0):
    """
    Computes hand-position anchors purely from played note data - there's no
    reliable native MIDI marker for this (see notes in parse_pro_guitar_track).
    Chords anchor at their lowest fret, with width spanning the full chord
    shape. Single-note runs anchor at the most prevalent non-open fret within
    the window (ties go to the lower fret); stray outlier notes (e.g. one
    reach up the neck) are excluded from the width so they don't blow out
    the zoom box for the whole window.
    """
    fretted = [n for n in notes if n['f'] > 0]

    if not fretted:
        return [{"time": 0.0, "fret": 1, "width": 4}]

    grouped_notes = {}
    for n in fretted:
        grouped_notes.setdefault(n['t'], []).append(n)

    timestamps = sorted(grouped_notes.keys())
    anchors = []

    last_fret = None
    last_width = None

    start_idx = 0
    while start_idx < len(timestamps):
        window_start = timestamps[start_idx]
        window_end = window_start + window_seconds

        window_frets = []
        chord_found = False
        chord_lowest_fret = None
        chord_highest_fret = None

        end_idx = start_idx
        while end_idx < len(timestamps) and timestamps[end_idx] <= window_end:
            t = timestamps[end_idx]
            simultaneous_notes = grouped_notes[t]

            if len(simultaneous_notes) > 1:
                chord_found = True
                chord_lowest_fret = min(n['f'] for n in simultaneous_notes)
                chord_highest_fret = max(n['f'] for n in simultaneous_notes)
                break

            window_frets.append(simultaneous_notes[0]['f'])
            end_idx += 1

        if chord_found:
            target_fret = chord_lowest_fret
            target_width = max(4, chord_highest_fret - chord_lowest_fret + 1)
            start_idx = end_idx + 1
        else:
            counts = Counter(window_frets)
            top_count = counts.most_common(1)[0][1]
            # tie-break toward the lowest fret among equally-common candidates
            target_fret = min(f for f, c in counts.items() if c == top_count)
            # discard stray outlier frets (a single reach far from the
            # prevalent position) before sizing the zoom box
            close_frets = [f for f in window_frets if abs(f - target_fret) <= 4]
            target_width = max(4, max(close_frets) - min(close_frets) + 1) if close_frets else 4
            start_idx = end_idx

        if target_fret != last_fret or target_width != last_width:
            anchors.append({
                "time": window_start,
                "fret": target_fret,
                "width": target_width
            })
            last_fret = target_fret
            last_width = target_width

    return anchors if anchors else [{"time": 0.0, "fret": 1, "width": 4}]


# --- 1. PRO GUITAR / BASS PARSER (EXPERT-TIER STRING NOTE + VELOCITY FRET) ---
def parse_pro_guitar_track(track, tempo_map, ticks_per_beat, is_bass=False):
    active_notes = {}
    final_notes = []
    current_ticks = 0
    max_strings = 4 if is_bass else 6

    EXPERT_BASE = 96

    for msg in track:
        current_ticks += msg.time

        if msg.type in ['note_on', 'note_off']:
            abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)
            # --- Playable Note Parsing ---
            offset = msg.note - EXPERT_BASE
            if not (0 <= offset < max_strings):
                continue

            string_idx = offset  # 0-based, 0 = lowest-pitched string
            note_key = msg.note

            if msg.type == 'note_on' and msg.velocity > 0:
                fret = msg.velocity - 100
                if fret < 0 or fret > 22:
                    continue  # outside valid fret range, skip

                active_notes[note_key] = {
                    "t": abs_time,
                    "s": string_idx,
                    "f": fret
                }
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                if note_key in active_notes:
                    note_data = active_notes.pop(note_key)
                    sustain = round(abs_time - note_data["t"], 4)
                    
                    entry = {
                        "t": note_data["t"],
                        "s": note_data["s"],
                        "f": note_data["f"]
                    }
                    if sustain > 0.05:
                        entry["sus"] = sustain
                    final_notes.append(entry)

    # Cleanup any lingering notes that lack explicit note_off events
    for note_key, note_data in active_notes.items():
        final_notes.append({
            "t": note_data["t"],
            "s": note_data["s"],
            "f": note_data["f"]
        })

    final_notes.sort(key=lambda x: (x['t'], x['s']))

    # Anchors are always computed dynamically from the played notes - there's
    # no reliable native MIDI marker for hand position. An earlier version of
    # this treated notes 108-129 as fret-position markers, but checking that
    # against a real chart showed it doesn't hold up: that range only covers
    # ~14% of note onsets, hits both single notes and chords indiscriminately,
    # and its values don't correlate with the fret actually being played -
    # it's very likely carrying some other per-passage flag (palm mute is
    # the best current guess) rather than position data. See compute_anchors().
    anchors = compute_anchors(final_notes)

    return {
        "name": "Bass" if is_bass else "Combo",
        "tuning": [0] * max_strings,
        "capo": 0,
        "notes": final_notes,
        "chords": [],
        "anchors": anchors,
        # No "handPositions" field - not part of the spec (§6.1's top-level
        # shape doesn't include it). Anchors are the hand-position mechanism
        # per §6.4 ("where the fretting hand sits; drives a renderer's
        # zoom/focus box").
        "handshapes": [],
        "templates": []
    }


# --- 2. KEYS PARSER ---
def parse_keys_track(track, tempo_map, ticks_per_beat, ts_map):
    active_notes = {}
    raw_notes = []
    current_ticks = 0
    MIN_PIANO_NOTE = 21
    MAX_PIANO_NOTE = 108

    for msg in track:
        current_ticks += msg.time

        if msg.type not in ('note_on', 'note_off'):
            continue

        abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)

        if 0 <= msg.note <= 11:
            continue

        if not (MIN_PIANO_NOTE <= msg.note <= MAX_PIANO_NOTE):
            continue

        if msg.type == 'note_on' and msg.velocity > 0:
            active_notes.setdefault(msg.note, []).append((current_ticks, abs_time))
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in active_notes and active_notes[msg.note]:
                start_tick, start_time = active_notes[msg.note].pop(0)
                dur_seconds = round(abs_time - start_time, 4)
                bpm = get_tempo_bpm_at_tick(start_tick, tempo_map)
                note_value = seconds_to_note_value(dur_seconds, bpm)
                raw_notes.append({
                    "tick": start_tick,
                    "t": start_time,
                    "midi": msg.note,
                    "dur_value": note_value,
                    "dur_seconds": dur_seconds
                })

    raw_notes.sort(key=lambda n: (n["tick"], n["midi"]))

    if not raw_notes:
        measures = [{
            "idx": 1,
            "t": 0.0,
            "ts": [ts_map[0]['num'], ts_map[0]['den']],
            "tempo": get_tempo_bpm_at_tick(0, tempo_map),
            "staves": {"rh": {"voices": [{"v": 1, "beats": []}]}}
        }]
    else:
        last_tick = raw_notes[-1]["tick"]
        boundaries = build_measure_boundaries(ts_map, ticks_per_beat, last_tick)

        measures = []
        last_ts = None
        last_bpm = None
        for m_idx, (start_tick, num, den) in enumerate(boundaries):
            end_tick = boundaries[m_idx + 1][0] if m_idx + 1 < len(boundaries) else float('inf')
            measure_beats = [
                {"t": n["t"], "dur": n["dur_value"], "notes": [{"midi": n["midi"]}]}
                for n in raw_notes if start_tick <= n["tick"] < end_tick
            ]

            measure = {
                "idx": m_idx + 1,
                "t": ticks_to_seconds(start_tick, tempo_map, ticks_per_beat),
                "staves": {"rh": {"voices": [{"v": 1, "beats": measure_beats}]}}
            }
            if (num, den) != last_ts:
                measure["ts"] = [num, den]
                last_ts = (num, den)
            bpm = get_tempo_bpm_at_tick(start_tick, tempo_map)
            if bpm != last_bpm:
                measure["tempo"] = bpm
                last_bpm = bpm
            measures.append(measure)

    notation_json = {
        "version": 1,
        "instrument": "piano",
        "staves": [{"id": "rh", "clef": "G2", "label": "Right Hand"}],
        "measures": measures
    }

    wire_notes = [
        {
            "t": n["t"],
            "s": n["midi"] // 24,
            "f": n["midi"] % 24,
            "sus": n["dur_seconds"]
        }
        for n in raw_notes
    ]

    keys_wire_json = {
        "name": "Keys",
        "tuning": [0, 0, 0, 0, 0, 0],
        "capo": 0,
        "notes": wire_notes,
        "chords": [],
        "anchors": [{"time": 0.0, "fret": 1, "width": 4}],
        "handshapes": [],
        "templates": []
    }

    return notation_json, keys_wire_json


# --- KEY/SCALE ANNOTATIONS (keys.json) ---
def parse_key_signature_events(mid, tempo_map, ticks_per_beat):
    events = []
    for track in mid.tracks:
        current_ticks = 0
        for msg in track:
            current_ticks += msg.time
            if msg.type == 'key_signature':
                abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)
                is_minor = msg.key.endswith('m')
                events.append({
                    "t": abs_time,
                    "key": msg.key,
                    "scale": "natural_minor" if is_minor else "major"
                })

    events.sort(key=lambda e: e["t"])
    deduped = []
    for ev in events:
        if deduped and deduped[-1]["t"] == ev["t"]:
            deduped[-1] = ev
        else:
            deduped.append(ev)

    return deduped


# --- 3. DRUMS PARSER (PRO DRUMS: TOM/CYMBAL AWARE) ---
def parse_drums_track(track, tempo_map, ticks_per_beat):
    hits = []
    current_ticks = 0

    simple_pad_mapping = {
        96: "kick",
        97: "snare",
    }

    tom_cymbal_pads = {
        98: {"marker": 110, "cymbal": "hh_closed", "tom": "tom_hi"},
        99: {"marker": 111, "cymbal": "ride",       "tom": "tom_mid"},
        100: {"marker": 112, "cymbal": "crash_r",   "tom": "tom_floor"},
    }
    marker_to_pad_note = {info["marker"]: pad_note for pad_note, info in tom_cymbal_pads.items()}

    tom_marker_active = {98: False, 99: False, 100: False}
    processed_hits_this_tick = set()

    for msg in track:
        if msg.time > 0:
            processed_hits_this_tick.clear()

        current_ticks += msg.time
        abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)

        if msg.type not in ('note_on', 'note_off'):
            continue

        note_off_event = (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0)

        if msg.note in marker_to_pad_note:
            pad_note = marker_to_pad_note[msg.note]
            tom_marker_active[pad_note] = not note_off_event
            continue

        if note_off_event:
            continue

        if msg.note in simple_pad_mapping:
            pad_id = simple_pad_mapping[msg.note]
        elif msg.note in tom_cymbal_pads:
            info = tom_cymbal_pads[msg.note]
            pad_id = info["tom"] if tom_marker_active[msg.note] else info["cymbal"]
        else:
            continue

        if pad_id not in processed_hits_this_tick:
            hits.append({"t": abs_time, "p": pad_id, "v": msg.velocity})
            processed_hits_this_tick.add(pad_id)

    hits.sort(key=lambda x: x['t'])

    return {
        "version": 1,
        "name": "Drums",
        "kit": [
            {"id": "kick", "name": "Kick"},
            {"id": "snare", "name": "Snare"},
            {"id": "hh_closed", "name": "Hi-hat (closed)"},
            {"id": "tom_hi", "name": "High Tom"},
            {"id": "ride", "name": "Ride"},
            {"id": "tom_mid", "name": "Mid Tom"},
            {"id": "crash_r", "name": "Crash (right)"},
            {"id": "tom_floor", "name": "Floor Tom"}
        ],
        "hits": hits
    }


# --- 4. VOCALS PARSER ---
def parse_vocals_track(track, tempo_map, ticks_per_beat):
    raw_lyrics = []
    vocal_pitches = []
    current_ticks = 0
    active_vocal_notes = {}

    for msg in track:
        current_ticks += msg.time
        abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)

        if msg.type in ['text', 'lyrics']:
            text = msg.text.strip()
            if text and not text.startswith('[') and not text.startswith('#'):
                raw_lyrics.append({"t": abs_time, "w": text})

        elif msg.type == 'note_on' and msg.velocity > 0:
            if 36 <= msg.note <= 84:
                active_vocal_notes[msg.note] = {"t": abs_time}

        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in active_vocal_notes:
                note_info = active_vocal_notes.pop(msg.note)
                dur = round(abs_time - note_info["t"], 4)
                if dur > 0.05:
                    vocal_pitches.append({
                        "t": note_info["t"],
                        "d": dur,
                        "midi": msg.note
                    })
                    
    lyrics = []
    for lyric in raw_lyrics:
        closest_note = None
        min_diff = 0.15 
        for note in vocal_pitches:
            diff = abs(note["t"] - lyric["t"])
            if diff < min_diff:
                closest_note = note
                min_diff = diff
        
        dur = closest_note["d"] if closest_note else 0.1 
        
        lyrics.append({
            "t": lyric["t"],
            "d": dur,
            "w": lyric["w"]
        })

    lyrics.sort(key=lambda x: x['t'])
    vocal_pitches.sort(key=lambda x: x['t'])

    return lyrics, {"version": 1, "notes": vocal_pitches}


# --- 5. TIMELINE PARSER ---
def parse_events_and_timeline(mid, tempo_map):
    ticks_per_beat = mid.ticks_per_beat
    timeline_data = {
        "version": 1,
        "tempos": [],
        "time_signatures": [],
        "sections": []
    }

    for track in mid.tracks:
        current_ticks = 0
        for msg in track:
            current_ticks += msg.time
            abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)

            if msg.type == 'set_tempo':
                bpm = round(mido.tempo2bpm(msg.tempo), 3)
                if not any(t['time'] == abs_time for t in timeline_data["tempos"]):
                    timeline_data["tempos"].append({"time": abs_time, "bpm": bpm})

            elif msg.type == 'time_signature':
                ts = [msg.numerator, msg.denominator]
                if not any(t['time'] == abs_time for t in timeline_data["time_signatures"]):
                    timeline_data["time_signatures"].append({"time": abs_time, "ts": ts})

    section_counter = {}
    for track in mid.tracks:
        if get_track_name(track) == 'EVENTS':
            current_ticks = 0
            for msg in track:
                current_ticks += msg.time
                if msg.type == 'text':
                    text = msg.text.strip()
                    if text.startswith('[section ') or text.startswith('[prc_'):
                        sec_name = re.sub(r'\[(section|prc_)\s*', '', text).rstrip(']').strip()
                        abs_time = ticks_to_seconds(current_ticks, tempo_map, ticks_per_beat)

                        num = section_counter.get(sec_name, 0) + 1
                        section_counter[sec_name] = num

                        timeline_data["sections"].append({
                            "name": sec_name,
                            "number": num,
                            "time": abs_time
                        })

    return timeline_data


# --- MAIN DISPATCHER ---
def parse_midi_file(midi_path, output_folder):
    if not os.path.exists(midi_path):
        return [], {}

    mid = mido.MidiFile(midi_path)
    ticks_per_beat = mid.ticks_per_beat
    tempo_map = build_tempo_map(mid)
    ts_map = build_time_signature_map(mid)

    arrangements = {}
    extra_files = {}
    generated_files = []

    timeline_data = parse_events_and_timeline(mid, tempo_map)
    extra_files['song_timeline.json'] = timeline_data

    key_signature_events = parse_key_signature_events(mid, tempo_map, ticks_per_beat)
    if key_signature_events:
        extra_files['keys.json'] = {"version": 1, "events": key_signature_events}

    for track in mid.tracks:
        t_name = get_track_name(track)

        if 'REAL_GUITAR' in t_name:
            arrangements['combo'] = parse_pro_guitar_track(track, tempo_map, ticks_per_beat, is_bass=False)

        elif 'REAL_BASS' in t_name:
            arrangements['bass'] = parse_pro_guitar_track(track, tempo_map, ticks_per_beat, is_bass=True)

        elif t_name == 'PART REAL_KEYS_X':
            notation_json, keys_wire_json = parse_keys_track(track, tempo_map, ticks_per_beat, ts_map)
            extra_files['notation_keys.json'] = notation_json
            extra_files['keys_pro_wire.json'] = keys_wire_json

        elif 'DRUM' in t_name:
            drum_tab = parse_drums_track(track, tempo_map, ticks_per_beat)
            if drum_tab["hits"]:
                extra_files['drum_tab.json'] = drum_tab

        elif 'VOCAL' in t_name or 'HARM1' in t_name:
            lyrics, vocal_pitch = parse_vocals_track(track, tempo_map, ticks_per_beat)
            if lyrics:
                extra_files['lyrics.json'] = lyrics
            if vocal_pitch["notes"]:
                extra_files['vocal_pitch.json'] = vocal_pitch

    os.makedirs(output_folder, exist_ok=True)

    for name, data in arrangements.items():
        file_name = f'{name}.json'
        with open(os.path.join(output_folder, file_name), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        generated_files.append(file_name)

    for file_name, data in extra_files.items():
        with open(os.path.join(output_folder, file_name), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        generated_files.append(file_name)

    return generated_files