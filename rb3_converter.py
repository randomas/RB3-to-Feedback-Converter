import os
import configparser
import zipfile
import yaml
import argparse
import re
from rb_parser import parse_midi_file


def parse_tuning(value, default):
    if not value:
        return default
    value = value.strip().strip('"').strip("'").strip()
    if not value:
        return default
    tokens = [t for t in re.split(r'[,\s]+', value) if t != '']
    offsets = []
    for tok in tokens:
        try:
            offsets.append(int(tok))
        except ValueError:
            continue
    return offsets if offsets else default


def parse_tuning_strict(value):
    # Like parse_tuning, but returns None instead of a default when the
    # value is missing/blank/non-numeric ("Unknown" etc.) - resolve_tuning
    # below needs to tell "no usable data" apart from "a real tuning".
    if not value:
        return None
    value = value.strip().strip('"').strip("'").strip()
    if not value:
        return None
    tokens = [t for t in re.split(r'[,\s]+', value) if t != '']
    if not tokens:
        return None
    try:
        return [int(t) for t in tokens]
    except ValueError:
        return None


def resolve_tuning(rb3_tuning_str, songsterr_tuning_str, default):
    """
    Reconciles the RB3-declared tuning against a Songsterr-sourced tuning
    for the same instrument. Returns (tuning, needs_check):
      - No usable Songsterr value -> fall back to the RB3 tuning (or
        default), never flagged - there's nothing to disagree with.
      - Songsterr present but RB3 tuning missing, or the two have a
        different number of strings (e.g. a 7-string chart Songsterr knows
        about that the RB3 .ini only ever declared 6 strings for) -> can't
        meaningfully compare, so trust Songsterr as-is, not flagged.
      - Both present, same length, and the per-string difference is
        constant across every string (including all-zero, i.e. identical)
        -> they're the same tuning (or a uniform transposition of it) ->
        use Songsterr, not flagged.
      - Both present, same length, but the per-string difference is NOT
        constant -> genuinely conflicting tunings -> use Songsterr, but
        flag it for a human to double check.
    """
    rb3 = parse_tuning_strict(rb3_tuning_str)
    songsterr = parse_tuning_strict(songsterr_tuning_str)

    if songsterr is None:
        return (rb3 if rb3 is not None else default), False

    if rb3 is None or len(rb3) != len(songsterr):
        return songsterr, False

    diffs = [s - r for s, r in zip(songsterr, rb3)]
    needs_check = len(set(diffs)) > 1
    return songsterr, needs_check


def convert_to_feedpak(song_folder, output_folder,
                        guitar_tuning_override=None, guitar_tuning_check=False,
                        bass_tuning_override=None, bass_tuning_check=False):
    ini_path = os.path.join(song_folder, 'song.ini')
    if not os.path.exists(ini_path):
        print(f"Error: No song.ini found in {song_folder}")
        return

    config = configparser.ConfigParser()
    config.read(ini_path, encoding='utf-8-sig') 
    
    if 'song' not in config:
        print("Error: Missing [song] section in song.ini")
        return

    meta = config['song']
    song_name = meta.get('name', 'Unknown Song')
    artist = meta.get('artist', 'Unknown Artist')
    
    print(f"Processing: {artist} - {song_name}")

    midi_path = os.path.join(song_folder, 'notes.mid')
    generated_jsons = []
    if os.path.exists(midi_path):
        print(" -> Parsing MIDI track data...")
        generated_jsons = parse_midi_file(midi_path, song_folder)

    guitar_tuning = guitar_tuning_override if guitar_tuning_override is not None \
        else parse_tuning(meta.get('real_guitar_tuning'), [0, 0, 0, 0, 0, 0])
    bass_tuning = bass_tuning_override if bass_tuning_override is not None \
        else parse_tuning(meta.get('real_bass_tuning'), [0, 0, 0, 0])

    arrangements = []
    if 'combo.json' in generated_jsons:
        arrangements.append({
            "id": "combo",
            "name": "Combo",
            "file": "arrangements/combo.json",
            "tuning": guitar_tuning,
            "capo": 0
        })
    if 'bass.json' in generated_jsons:
        arrangements.append({
            "id": "bass",
            "name": "Bass",
            "file": "arrangements/bass.json",
            "tuning": bass_tuning,
            "capo": 0
        })
    if 'notation_keys.json' in generated_jsons:
        keys_entry = {
            "id": "keys",
            "name": "Keys",
            "type": "piano",
            "notation": "arrangements/notation_keys.json"
        }
        if 'keys_pro_wire.json' in generated_jsons:
            keys_entry["file"] = "arrangements/keys.json"
        arrangements.append(keys_entry)
    if 'drum_tab.json' in generated_jsons:
        arrangements.append({
            "id": "drums",
            "name": "Drums",
            "type": "drums",
            "drum_tab": "drum_tab.json"
        })

    stems = []
    files_in_folder = os.listdir(song_folder)
    ogg_files = [f for f in files_in_folder if f.endswith('.ogg')]
    has_separated_stems = len(ogg_files) > 1

    cover_file = None

    for file in files_in_folder:
        if file.endswith('.ogg'):
            stem_id = file.replace('.ogg', '')
            is_full_mix = (stem_id == "song")
            
            default_state = False if (is_full_mix and has_separated_stems) else True

            stems.append({
                "id": "full" if is_full_mix else stem_id,
                "file": f"stems/{file}",
                "default": default_state
            })
        elif file.lower() in ['album.jpg', 'cover.jpg', 'album.png', 'cover.png']:
            cover_file = file

    duration_ms = float(meta.get('song_length', 0))

    display_title = song_name
    if guitar_tuning_check or bass_tuning_check:
        display_title = f"{song_name} (check tuning)"

    manifest = {
        "feedpak_version": "1.19.0",
        "title": display_title,
        "artist": artist,
        "album": meta.get('album', ''),
        "year": int(meta['year']) if meta.get('year') and meta['year'].isdigit() else None,
        "genres": [meta['genre']] if meta.get('genre') else [],
        "duration": round(duration_ms / 1000.0, 3) if duration_ms > 0 else 180.0,
        "authors": [{"name": meta.get('charter', 'Unknown'), "role": "transcriber"}],
        "arrangements": arrangements,
        "stems": stems
    }

    if 'lyrics.json' in generated_jsons:
        manifest['lyrics'] = 'lyrics.json'
    if 'vocal_pitch.json' in generated_jsons:
        manifest['vocal_pitch'] = 'vocal_pitch.json'
    if 'drum_tab.json' in generated_jsons:
        manifest['drum_tab'] = 'drum_tab.json'
    if 'song_timeline.json' in generated_jsons:
        manifest['song_timeline'] = 'song_timeline.json'
    if 'keys.json' in generated_jsons:
        manifest['keys'] = 'keys.json'
    if cover_file:
        manifest['cover'] = cover_file

    manifest = {k: v for k, v in manifest.items() if v is not None and v != ''}

    manifest_path = os.path.join(song_folder, 'manifest.yaml')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    os.makedirs(output_folder, exist_ok=True)
    safe_filename = f"{artist} - {song_name}.feedpak".replace('/', '_')
    feedpak_path = os.path.join(output_folder, safe_filename)

    with zipfile.ZipFile(feedpak_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(manifest_path, 'manifest.yaml')

        for file in files_in_folder:
            if file.endswith('.ogg'):
                zipf.write(os.path.join(song_folder, file), f"stems/{file}")
            elif file == cover_file:
                zipf.write(os.path.join(song_folder, file), file)

        for json_file in generated_jsons:
            full_json_path = os.path.join(song_folder, json_file)
            if json_file in ['combo.json', 'bass.json', 'notation_keys.json']:
                zipf.write(full_json_path, f"arrangements/{json_file}")
            elif json_file == 'keys_pro_wire.json':
                zipf.write(full_json_path, "arrangements/keys.json")
            else:
                zipf.write(full_json_path, json_file)

    os.remove(manifest_path)
    for json_file in generated_jsons:
        json_full_path = os.path.join(song_folder, json_file)
        if os.path.exists(json_full_path):
            os.remove(json_full_path)

    print(f"Successfully generated: {feedpak_path}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Rock Band song folder to Feedpak format.")
    parser.add_argument("song_folder", help="Path to the input song folder containing song.ini and notes.mid")
    parser.add_argument("output_folder", help="Path to the directory where the generated .feedpak will be saved")
    
    args = parser.parse_args()
    
    convert_to_feedpak(args.song_folder, args.output_folder)