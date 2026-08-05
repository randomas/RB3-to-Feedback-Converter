# RB3-to-Feedback-Converter
# Rock Band 3 to Feedpak Converter Toolkit

A collection of Python utilities designed to index, parse, and convert **Rock Band 3** (and custom) song folders into the standard **Feedpak** format (`.feedpak`).

This toolkit parses metadata, audio stems, and MIDI tracks (including Pro Guitar, Pro Bass, Pro Keys, Pro Drums, Vocals, and Timeline events) to output valid Feedpak archives and custom song databases, with an optional pipeline for reconciling RB3's declared tunings against real-world tunings sourced from Songsterr.

> **Input format: Phase Shift / Clone Hero "open" folders, not raw RB3 CON files.**
> "Song folder" throughout this README means the **Phase Shift / Clone Hero style** layout: one `song.ini`, one `notes.mid`, and a separate `.ogg` file per audio stem, all as loose files in a folder. This is *not* the same as an original Rock Band 3 CON file - once extracted, a CON gives you a single multiplexed `.mogg` (not per-stem `.ogg` files) plus a `notes.mid` and a `songs.dta` (not `song.ini`) for metadata. Everything in this toolkit - `song.ini` parsing, per-stem `.ogg` stem detection, all of it - assumes the PH/CH layout and will not work directly against an extracted CON's files. A CON → PH/CH converter (demuxing the `.mogg` into stems and translating `songs.dta` into `song.ini`, while preserving tuning data through that step) is planned as a separate upstream tool, not yet part of this repo.

---

## Table of Contents

* [Overview](#overview)
* [Requirements & Dependencies](#requirements--dependencies)
* [Script Descriptions](#script-descriptions)
* [Usage Workflow](#usage-workflow)
  * [1. Indexing Songs (generate_db.py)](#1-indexing-songs-generate_dbpy)
  * [2. Single Song Conversion (rb3_converter.py)](#2-single-song-conversion-rb3_converterpy)
  * [3. Batch Conversion (Batch_convert.py)](#3-batch-conversion-batch_convertpy)
* [Tuning Reconciliation Pipeline (utility_scripts/)](#tuning-reconciliation-pipeline-utility_scripts)
* [MIDI Parsing Details](#midi-parsing-details)
* [Pro Guitar / Bass Technique Detection](#pro-guitar--bass-technique-detection)
* [Roadmap](#roadmap)

---

## Overview

The core toolkit consists of four interconnected Python scripts:

1. `generate_db.py` — Scans local song directories and generates a CSV database with track information, difficulties, and feature flags.
2. `rb_parser.py` — High-level MIDI engine that extracts tempo maps, time signatures, notes, lyrics, drum hits, and key annotations from `notes.mid`.
3. `rb3_converter.py` — Converts an individual Rock Band song folder (Phase Shift/Clone Hero layout - see the note above) into a single `.feedpak` file containing `manifest.yaml`, stems, artwork, and arrangement JSON files.
4. `Batch_convert.py` — Reads the generated CSV database, filters songs containing specific criteria (e.g., Pro Guitar or Pro Keys), and converts them in bulk.

Alongside these, `utility_scripts/` holds a separate, optional three-stage pipeline for building a tuning-reconciled song database — see [Tuning Reconciliation Pipeline](#tuning-reconciliation-pipeline-utility_scripts) below. Its output plugs into `rb3_converter.py` and `Batch_convert.py` via an optional `--tuning-csv` argument; nothing in the core toolkit requires it.

---

## Requirements & Dependencies

This toolkit requires **Python 3.7+**.

### Required Python Libraries

Install the required third-party libraries via `pip`:

```bash
pip install mido pyyaml requests

```

* `mido`: Used by `rb_parser.py` for reading and parsing standard MIDI files.
* `pyyaml`: Used by `rb3_converter.py` to construct and dump `manifest.yaml` files.
* `requests`: Used by `utility_scripts/tuning_scraper_0.2.py` to query the Songsterr API. Only needed if you're using the tuning reconciliation pipeline.

---

## Script Descriptions

### `generate_db.py`

Indexes song metadata from `song.ini` files by scanning a songs directory directly.

* Extracts song metadata (Title, Artist, Album, Year, Charter).
* Parses difficulty levels for standard and Pro instruments.
* Detects available audio stems (`.ogg`).
* Records the RB3-declared tuning offsets (`Guitar Tuning Offset` / `Bass Tuning Offset`) from `song.ini`.
* Exports all collected information to `rb3_songs_db.csv`.

`utility_scripts/build_song_db.py` is an alternative to this script: instead of scanning a directory, it reads an explicit `songlist.txt` (one folder name per line) and indexes only those. It doesn't record the tuning offset columns - use it when you want to index a curated subset rather than everything on disk. Use one or the other, not both, for a given `rb3_songs_db.csv`.

### `rb_parser.py`

The underlying parser module invoked during conversion. It reads `notes.mid` and extracts:

* **Tempo Map & Time Signatures:** Accurately converts MIDI ticks into absolute timestamps (in seconds).
* **Pro Guitar / Pro Bass:** Extracts Expert-tier string/fret notes (string encoded by MIDI note number, fret by velocity), dynamically computed hand-position anchors, and slide/hammer-on/pull-off technique detection - see [Pro Guitar / Bass Technique Detection](#pro-guitar--bass-technique-detection).
* **Pro Keys:** Converts `PART REAL_KEYS_X` pitch data into both a staff-notation file (`notation_keys.json`) and a wire-format arrangement (`arrangements/keys.json`) - the wire format is what a Reader actually scores notes from; the notation file is a supplementary staff view.
* **Pro Drums:** Handles kick and snare directly, and distinguishes cymbal vs. tom hits on the yellow/blue/green lanes using RB3's tom-marker notes (a marker being held means tom; its absence is the cymbal default).
* **Vocals & Lyrics:** Extracts lyric text and vocal note pitch durations.
* **Timeline & Key Signatures:** Maps song sections (`[section ...]` / `[prc_...]`), tempo changes, time signatures, and key/scale signature events (when present in the source MIDI).

### `rb3_converter.py`

Translates a single Rock Band 3 song directory into a `.feedpak` file.

* Calls `rb_parser.py` to extract MIDI elements into temporary JSON files.
* Reads metadata from `song.ini` and builds a `manifest.yaml` (Feedpak spec v1.19.0).
* Resolves guitar/bass tuning - by default from `song.ini`'s `real_guitar_tuning` / `real_bass_tuning` fields, or from a Songsterr cross-reference CSV when one is supplied (see below).
* Bundles `.ogg` stems, cover artwork, and generated JSON charts into a compressed `.feedpak` zip package.
* Automatically cleans up temporary disk files afterwards.

**Optional tuning cross-reference:** pass `--tuning-csv path/to/rb3_songs_db_merged_with_tunings.csv` to look this song up (by folder name) in the reconciled tuning database instead of relying solely on `song.ini`. See [Tuning Reconciliation Pipeline](#tuning-reconciliation-pipeline-utility_scripts) for how that CSV is built and what the reconciliation rule does.

```bash
python rb3_converter.py "./songs/Boston - More Than a Feeling" "./converted_feedpaks" --tuning-csv utility_scripts/rb3_songs_db_merged_with_tunings.csv
```

### `Batch_convert.py`

Automates mass conversions using a song database CSV.

* Filters songs that feature **Pro Guitar** or **Pro Keys**.
* Checks file paths on disk.
* Includes a `--dry-run` flag to preview matching files before performing any conversion.
* Accepts the same optional `--tuning-csv` argument as `rb3_converter.py`. If the main CSV you pass in already has the Songsterr tuning columns (i.e. it's `rb3_songs_db_merged_with_tunings.csv` itself), those are used automatically and `--tuning-csv` isn't needed; pass it separately when your main filter CSV is the plain `rb3_songs_db.csv` and you want to cross-reference tuning from a different file.

---

## Usage Workflow

### 1. Indexing Songs (`generate_db.py`)

1. Run the script:
```bash
python generate_db.py [path_to_songs_directory]

```

*(If `path_to_songs_directory` is omitted, it defaults to the current working directory).*
2. Output: `rb3_songs_db.csv` containing indexed difficulty and metadata.

---

### 2. Single Song Conversion (`rb3_converter.py`)

To convert an individual song folder containing `song.ini` and `notes.mid`:

```bash
python rb3_converter.py /path/to/song_folder /path/to/output_dir

```

**Example:**

```bash
python rb3_converter.py "./songs/Boston - More Than a Feeling" "./converted_feedpaks"

```

Add `--tuning-csv <path>` to cross-reference tuning against a reconciled database instead of `song.ini` alone (see [Tuning Reconciliation Pipeline](#tuning-reconciliation-pipeline-utility_scripts)).

---

### 3. Batch Conversion (`Batch_convert.py`)

Batch converts all Pro-compatible songs indexed in your CSV file.

#### Step 1: Preview files to convert (Dry Run)

Use the `--dry-run` flag to inspect matching files without writing output files:

```bash
python Batch_convert.py rb3_songs_db.csv /path/to/songs_dir /path/to/output_dir --dry-run

```

#### Step 2: Execute Batch Conversion

Run the conversion without `--dry-run`:

```bash
python Batch_convert.py rb3_songs_db.csv /path/to/songs_dir /path/to/output_dir

```

To reconcile tuning against the Songsterr cross-reference database while batch converting:

```bash
python Batch_convert.py rb3_songs_db.csv /path/to/songs_dir /path/to/output_dir --tuning-csv utility_scripts/rb3_songs_db_merged_with_tunings.csv

```

(or just pass `rb3_songs_db_merged_with_tunings.csv` itself as the main CSV argument - its tuning columns are detected automatically and `--tuning-csv` isn't required in that case).

---

## Tuning Reconciliation Pipeline (`utility_scripts/`)

RB3's declared tuning in `song.ini` isn't always accurate. `utility_scripts/` holds a separate three-stage pipeline for cross-referencing it against real-world tunings, ending in a CSV that `rb3_converter.py` / `Batch_convert.py` can consume via `--tuning-csv`. Each stage is optional and independent - run as many or as few as you need.

**Stage 1 — `utility_scripts/build_song_db.py`**
Alternative to `generate_db.py`: builds `rb3_songs_db.csv` from an explicit `songlist.txt` (one song folder name per line) instead of scanning a directory. Use this if you want to index a curated subset.

**Stage 2 — `utility_scripts/SongDBmerge.py`**
Merges `rb3_songs_db.csv` against a manually-curated `rockband_tunings.csv` (song shortname → declared tuning), fuzzy-matching song/folder names (Levenshtein similarity, threshold 0.75). Adds `Guitar Tuning` / `Bass Tuning` columns and writes `rb3_songs_db_merged.csv`, plus an `unmerged_tunings_report.csv` listing any tuning entries that couldn't be confidently matched, for manual review.

```bash
python utility_scripts/SongDBmerge.py
```

**Stage 3 — `utility_scripts/tuning_scraper_0.2.py`**
Queries the Songsterr `/api/search` endpoint for each song in `rb3_songs_db_merged.csv`, picks the best-matching guitar/bass track (by artist/title similarity, view count, and GM instrument ID), and computes each string's semitone offset from standard tuning. Adds `S.SterrGtuning`, `S.SterrBtuning`, and `S.SterrStatus` columns and writes `rb3_songs_db_merged_with_tunings.csv`. Rate-limited (0.5s between requests); rows that couldn't be matched are marked with a status other than `matched*` and printed with a `<-- CHECK` flag during the run.

```bash
python utility_scripts/tuning_scraper_0.2.py
```

**Reconciliation rule** (applied by `rb3_converter.py`'s `resolve_tuning()` when given the resulting CSV via `--tuning-csv`, per string, independently for guitar and bass):

| RB3 tuning vs. Songsterr tuning | Result |
| --- | --- |
| No usable Songsterr value (`Unknown`, blank) | Fall back to the RB3-declared tuning. No flag. |
| Songsterr present, RB3 tuning missing | Use Songsterr as-is. No flag. |
| Different number of strings (e.g. a 7-string Songsterr tab vs. a 6-string RB3 chart) | Use Songsterr as-is. Manifest title gets `(string count mismatch)`. |
| Same number of strings, per-string offset is identical (including all zero, i.e. same tuning) or a uniform shift across every string | Use Songsterr. No flag. |
| Same number of strings, per-string offset differs unevenly | Use Songsterr. Manifest title gets `(check tuning)`. |

Both flags can appear together (e.g. guitar mismatched non-uniformly while bass had a different string count). Filenames stay clean regardless - only the manifest `title` (what shows in the song list) carries the flag.

`rb3_songs_db_merged_with_tunings.csv` can be passed as either the main CSV argument to `Batch_convert.py` (its tuning columns are auto-detected) or as `--tuning-csv` to either script alongside a different main filter CSV.

---

## MIDI Parsing Details

| MIDI Track Name | Extracted Target | Description |
| --- | --- | --- |
| `PART REAL_GUITAR` | `combo.json` | Expert-tier Pro Guitar notes, strings, frets, anchors, slides, and hammer-ons/pull-offs. |
| `PART REAL_BASS` | `bass.json` | Expert-tier Pro Bass notes, strings, frets, anchors, slides, and hammer-ons/pull-offs. |
| `PART REAL_KEYS_X` | `notation_keys.json` + `arrangements/keys.json` | Expert Real Keys split into staff notation and the scored wire-format chart. |
| `PART DRUMS` | `drum_tab.json` | Kick, snare, and tom-marker aware cymbal/tom hits (yellow/blue/green lanes). |
| `PART VOCALS` / `HARM1` | `lyrics.json` / `vocal_pitch.json` | Word timestamps and pitch durations. |
| `EVENTS` | `song_timeline.json` | Song sections, practice markers, tempos, and time signatures. |

---

## Pro Guitar / Bass Technique Detection

RB3's Pro Guitar/Bass MIDI has no reliable native "hand position" marker, so `rb_parser.py` computes hand-position anchors dynamically from the notes actually played, rather than trusting any single MIDI note range for it:

* **Anchors:** chords anchor at their lowest fret (width spanning the full chord shape); single-note runs anchor at the most prevalent non-open fret in a rolling window, with stray outlier reaches excluded from the width so one high note doesn't blow out the zoom box for the whole passage.
* **Slides (`sl` / `slu`):** detected from a dedicated MIDI note (103) whose velocity encodes the destination fret. When the computed destination equals the note's own starting fret - the signature of a charter never setting a real target - it's treated as an open/unpitched slide (`slu`) rather than a pitched one (`sl`).
* **Hammer-ons / pull-offs (`ho` / `po`):** inferred per string from the absence of a pick-attack marker (MIDI note 108) combined with a short gap (≤150ms) since the previous note on the same string. Direction (`ho` for an ascending fret, `po` for descending) comes from comparing the two frets.

These were reverse-engineered empirically against real charts rather than sourced from official documentation, since RB3 doesn't publish a spec for this. They're solid against everything checked so far, but if you spot a chart where the output looks wrong, a MIDI dump of the relevant passage (with a description of what it should look like in-game) is the fastest way to correct it.

---

## Roadmap

* **CON → PH/CH converter.** Everything in this repo currently starts from a Phase Shift/Clone Hero-style open folder (see the note at the top). A separate upstream tool is planned to take an extracted RB3 CON directly - demuxing its single `.mogg` into per-stem `.ogg` files and translating `songs.dta` metadata into a `song.ini` - so this toolkit can be pointed at CON-derived content too. The main risk to watch for there is tuning data: it needs to survive the `.dta` → `.ini` translation intact, since everything downstream (including the [tuning reconciliation pipeline](#tuning-reconciliation-pipeline-utility_scripts)) depends on `real_guitar_tuning` / `real_bass_tuning` being present and correct in the resulting `song.ini`.