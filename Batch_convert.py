import os
import csv
import argparse
from rb3_converter import convert_to_feedpak, resolve_tuning, load_tuning_lookup

def parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return -1

def batch_convert(csv_path, base_songs_dir, output_folder, dry_run=False, tuning_csv_path=None):
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    filtered_rows = []
    total_csv_count = 0

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # The merged CSV (rb3_songs_db_merged_with_tunings.csv) has these
        # extra columns; the plain rb3_songs_db.csv doesn't. If a separate
        # --tuning-csv was given, that takes priority as the tuning source
        # regardless of what columns csv_path itself has.
        main_csv_has_tuning_columns = reader.fieldnames is not None and \
            'S.SterrGtuning' in reader.fieldnames and 'S.SterrBtuning' in reader.fieldnames

        for row in reader:
            total_csv_count += 1
            has_pro_guitar = row.get('Has Pro Guitar', '').strip().lower() == 'true'
            has_pro_keys = row.get('Has Pro Keys', '').strip().lower() == 'true'
            diff_pro_guitar = parse_int(row.get('Diff Pro Guitar', -1))
            diff_pro_keys = parse_int(row.get('Diff Pro Keys', -1))

            # Filter rows where either Pro Guitar / Combo or Pro Keys is present
            if has_pro_guitar or has_pro_keys or diff_pro_guitar >= 0 or diff_pro_keys >= 0:
                filtered_rows.append(row)

    total_matches = len(filtered_rows)

    # Resolve where tuning cross-reference data comes from, if anywhere.
    tuning_lookup = None
    if tuning_csv_path:
        tuning_lookup = load_tuning_lookup(tuning_csv_path)
        if not tuning_lookup:
            print(f"Warning: --tuning-csv '{tuning_csv_path}' not found or missing expected columns - "
                  f"falling back to each song's own song.ini tuning.\n")
    elif main_csv_has_tuning_columns:
        tuning_lookup = {row['Folder Name']: row for row in filtered_rows}
    else:
        print("Note: no tuning cross-reference available (main CSV has no S.SterrGtuning/S.SterrBtuning "
              "columns and no --tuning-csv was given) - falling back to each song's own song.ini tuning.\n")

    # Dry Run Execution
    if dry_run:
        print(f"--- DRY RUN MODE ---")
        print(f"Found {total_matches} songs matching criteria out of {total_csv_count} total songs in CSV:\n")
        
        missing_count = 0
        for row in filtered_rows:
            folder_name = row['Folder Name']
            song_folder = os.path.join(base_songs_dir, folder_name)
            
            exists = os.path.exists(song_folder)
            status = "FOUND" if exists else "MISSING ON DISK"
            if not exists:
                missing_count += 1
                
            print(f" - [{status}] {folder_name}")

        print(f"\nDry run complete. {total_matches - missing_count} folders ready to convert ({missing_count} missing on disk).")
        return

    # Normal Conversion Execution
    print(f"Converting {total_matches} files...\n")

    success_count = 0
    check_tuning_count = 0
    string_mismatch_count = 0
    for row in filtered_rows:
        folder_name = row['Folder Name']
        song_folder = os.path.join(base_songs_dir, folder_name)
        
        if not os.path.exists(song_folder):
            print(f"Warning: Song folder not found on disk: {song_folder}")
            continue
            
        print(f"[{success_count + 1}/{total_matches}] Processing folder: {folder_name}")

        guitar_tuning, guitar_check, guitar_string_mismatch = None, False, False
        bass_tuning, bass_check, bass_string_mismatch = None, False, False
        tuning_row = tuning_lookup.get(folder_name) if tuning_lookup else None
        if tuning_row:
            guitar_tuning, guitar_check, guitar_string_mismatch = resolve_tuning(
                tuning_row.get('Guitar Tuning'), tuning_row.get('S.SterrGtuning'), None)
            bass_tuning, bass_check, bass_string_mismatch = resolve_tuning(
                tuning_row.get('Bass Tuning'), tuning_row.get('S.SterrBtuning'), None)
            if guitar_check or bass_check:
                check_tuning_count += 1
            if guitar_string_mismatch or bass_string_mismatch:
                string_mismatch_count += 1

        try:
            convert_to_feedpak(
                song_folder, output_folder,
                guitar_tuning_override=guitar_tuning, guitar_tuning_check=guitar_check,
                guitar_string_mismatch=guitar_string_mismatch,
                bass_tuning_override=bass_tuning, bass_tuning_check=bass_check,
                bass_string_mismatch=bass_string_mismatch
            )
            success_count += 1
        except Exception as e:
            print(f"Error converting {folder_name}: {e}")

    print(f"\nBatch conversion complete! Successfully processed {success_count} files.")
    if tuning_lookup:
        print(f"{check_tuning_count} song(s) flagged '(check tuning)' - RB3 and Songsterr tunings "
              f"disagreed by a non-uniform amount across strings.")
        print(f"{string_mismatch_count} song(s) flagged '(string count mismatch)' - RB3 and Songsterr "
              f"tunings had a different number of strings, so Songsterr's was used without comparison.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch convert RB3 songs with Pro Guitar/Keys from CSV.")
    parser.add_argument("csv_path", help="Path to rb3_songs_db.csv or rb3_songs_db_merged_with_tunings.csv")
    parser.add_argument("base_songs_dir", help="Base directory containing the song folders")
    parser.add_argument("output_folder", help="Directory where .feedpak files will be saved")
    parser.add_argument("--dry-run", action="store_true", help="Preview the songs to be converted without running the conversion")
    parser.add_argument("--tuning-csv", default=None,
                         help="Optional separate path to rb3_songs_db_merged_with_tunings.csv, used as a "
                              "cross-reference lookup table for tuning by folder name. Only used when "
                              "provided; takes priority over tuning columns already in csv_path, if any. "
                              "Without either, tuning comes from each song's own song.ini.")

    args = parser.parse_args()
    batch_convert(args.csv_path, args.base_songs_dir, args.output_folder,
                  dry_run=args.dry_run, tuning_csv_path=args.tuning_csv)