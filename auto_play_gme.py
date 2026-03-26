#!/usr/bin/env python3
"""
auto_play_gme.py – Automatischer Spieltest für Tiptoi GME-Dateien

Extrahiert alle aktiven OIDs aus der GME/YAML, füttert sie an `tttool play`
und analysiert die Reaktionen. Erkennt Spiele und testet deren Startsequenzen.

Verwendung:
  python3 auto_play_gme.py buch.gme                    # Alle OIDs testen
  python3 auto_play_gme.py buch.gme --games             # Nur Spiele testen
  python3 auto_play_gme.py buch.gme --oids 1,5,10-20    # Bestimmte OIDs
  python3 auto_play_gme.py buch.gme --verbose            # Zeigt jede Reaktion
  python3 auto_play_gme.py buch.gme --json               # JSON-Ausgabe

Voraussetzungen:
  - tttool ≥ 1.11
  - Python 3.10+
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from collections import defaultdict

TTTOOL = os.environ.get("TTTOOL", str(Path.home() / ".local/bin/tttool"))

def _set_tttool(path: str):
    global TTTOOL
    TTTOOL = path

# ── Farben ────────────────────────────────────────────────────────────────────

RED    = "\033[0;31m"
GREEN  = "\033[0;32m"
YELLOW = "\033[0;33m"
BLUE   = "\033[0;34m"
BOLD   = "\033[1m"
NC     = "\033[0m"

def color_enabled():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def c(code, text):
    return f"{code}{text}{NC}" if color_enabled() else text


# ── GME-Binäranalyse ──────────────────────────────────────────────────────────

def read_oid_range(gme_path: Path) -> tuple[int, int]:
    """Liest den OID-Bereich (first_oid, last_oid) aus dem GME-Header."""
    data = gme_path.read_bytes()
    r32 = lambda d, o: struct.unpack_from('<I', d, o)[0]
    main_off = r32(data, 0)
    last_oid  = r32(data, main_off)
    first_oid = r32(data, main_off + 4)
    return first_oid, last_oid


def read_active_oids(gme_path: Path) -> list[int]:
    """Liest aktive OIDs (die einen Jump-Table-Eintrag != 0xFFFFFFFF haben)."""
    data = gme_path.read_bytes()
    r32 = lambda d, o: struct.unpack_from('<I', d, o)[0]
    main_off = r32(data, 0)
    last_oid  = r32(data, main_off)
    first_oid = r32(data, main_off + 4)

    active = []
    for i in range(first_oid, last_oid + 1):
        idx = i - first_oid
        ptr = r32(data, main_off + 8 + idx * 4)
        if ptr != 0xFFFFFFFF:
            active.append(i)
    return active


# ── YAML-Analyse ──────────────────────────────────────────────────────────────

def extract_yaml_games(yaml_path: Path) -> dict:
    """Extrahiert Spiel-Definitionen aus der tttool-YAML.

    Sucht nach:
      - games: Abschnitt (benannte Spiele mit Start-OIDs)
      - scriptcodes: Abschnitt (OID → Script-Zuordnung)
      - Bekannte Spielmuster (J(), P(), G() Befehle in Scripts)

    Gibt zurück: {
        "game_oids": [OIDs die Spiele starten],
        "game_names": {OID: Name},
        "answer_oids": [OIDs die als Antwort-Felder dienen könnten],
    }
    """
    result = {
        "game_oids": [],
        "game_names": {},
        "answer_oids": [],
    }

    if not yaml_path.exists():
        return result

    text = yaml_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Spiel-OIDs: Zeilen mit $game_start, Game, Spiel, Quiz etc.
    # tttool YAML hat scriptcodes: Abschnitt mit OID: [Aktionen]
    in_scripts = False
    current_oid = None
    game_pattern = re.compile(
        r'(game|spiel|quiz|rätsel|würfel|start|spielen)',
        re.IGNORECASE
    )
    # Suche nach OIDs mit Spielkommandos (J, P, G Befehle)
    game_cmd_pattern = re.compile(r'\b[JPG]\(')

    for line in lines:
        stripped = line.strip()

        # scriptcodes: Abschnitt erkennen
        if stripped.startswith("scriptcodes:") or stripped.startswith("scripts:"):
            in_scripts = True
            continue

        if in_scripts:
            # Neuer OID-Eintrag: "  42:" oder "  - 42:"
            oid_match = re.match(r'^\s+(\d+):', stripped)
            if oid_match:
                current_oid = int(oid_match.group(1))

            # Spielkommandos in der Zeile?
            if current_oid and game_cmd_pattern.search(stripped):
                if current_oid not in result["game_oids"]:
                    result["game_oids"].append(current_oid)

            # Nächster Top-Level-Schlüssel → Scripts-Block vorbei
            if not stripped.startswith("-") and not stripped.startswith("#") and ":" in stripped and not stripped[0].isspace():
                if not stripped.startswith("scriptcodes") and not stripped.startswith("scripts"):
                    in_scripts = False
                    current_oid = None

    return result


# ── tttool play Wrapper ───────────────────────────────────────────────────────

def run_tttool_play(gme_path: Path, oids: list[int], timeout_per_oid: float = 2.0) -> dict:
    """Füttert OIDs an `tttool play` und analysiert die Ausgabe.

    Gibt zurück: {
        oid: {
            "response": [Zeilen der Antwort],
            "plays_audio": bool,
            "audio_files": [referenzierte Audio-Indices],
            "has_error": bool,
            "is_game_action": bool,
            "raw": str,
        }
    }
    """
    # Alle OIDs als Zeilenblock vorbereiten
    oid_input = "\n".join(str(o) for o in oids) + "\n"

    try:
        proc = subprocess.run(
            [TTTOOL, "play", str(gme_path)],
            input=oid_input,
            capture_output=True,
            text=True,
            timeout=max(10, len(oids) * timeout_per_oid),
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return {oid: {"response": ["TIMEOUT"], "plays_audio": False,
                      "audio_files": [], "has_error": True,
                      "is_game_action": False, "raw": "TIMEOUT"} for oid in oids}
    except FileNotFoundError:
        print(f"{c(RED, '✗')} tttool nicht gefunden: {TTTOOL}", file=sys.stderr)
        sys.exit(1)

    return parse_play_output(output, oids)


def parse_play_output(output: str, oids: list[int]) -> dict:
    """Parst die Ausgabe von `tttool play` und ordnet sie den OIDs zu.

    tttool play gibt pro OID-Eingabe Zeilen aus wie:
      - "Ting" oder "Playing" + Dateiname/Index → Audio wird abgespielt
      - "Nothing known about OID X" → OID nicht belegt
      - "Jumping to ..." → Spiel-Sprung
      - "Setting register ..." → Spiel-Zustandsänderung
      - Leere Zeile oder Prompt → keine Reaktion
    """
    results = {}
    lines = output.splitlines()

    # Muster für bekannte Ausgaben
    audio_pattern = re.compile(
        r'(?:playing|ting|audio)\s+(?:file\s+)?["\']?(\w+)["\']?',
        re.IGNORECASE
    )
    nothing_pattern = re.compile(
        r'nothing\s+known|unknown\s+oid|no\s+script|invalid|not\s+found',
        re.IGNORECASE
    )
    game_action_pattern = re.compile(
        r'(?:jump|set|register|game|conditional|timer|cancel|random)',
        re.IGNORECASE
    )
    audio_index_pattern = re.compile(r'(\d+)')

    # Die Ausgabe den OIDs zuordnen
    # Strategie: tttool gibt ein Prompt aus (z.B. "> " oder "? "),
    # gefolgt vom eingegebenen OID, dann die Reaktion bis zum nächsten Prompt
    #
    # Fallback: Zeilen gleichmäßig auf OIDs aufteilen nach Prompt-Markern

    # Versuche zuerst Prompt-basierte Zuordnung
    # Typische Prompts: "> 42", "? 42", "42:", einfach die OID-Nummer am Zeilenanfang
    segments = []
    current_segment = []
    current_oid_idx = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Prüfe ob die Zeile einem neuen OID-Eingabe-Echo entspricht
        # tttool echo: die eingetippte Zahl, oft nach einem Prompt-Zeichen
        matched_new_oid = False
        if current_oid_idx < len(oids):
            oid_str = str(oids[current_oid_idx])
            # Zeile ist genau die OID-Nummer (mit optionalem Prompt davor)
            clean = re.sub(r'^[>?\s]+', '', stripped)
            if clean == oid_str or stripped == oid_str:
                # Vorheriges Segment speichern
                if current_oid_idx > 0:
                    segments.append(current_segment)
                current_segment = []
                current_oid_idx += 1
                matched_new_oid = True
                continue

        if not matched_new_oid:
            current_segment.append(stripped)

    # Letztes Segment
    if current_segment:
        segments.append(current_segment)

    # Wenn weniger Segmente als OIDs → unmatched OIDs hinzufügen
    while len(segments) < len(oids):
        segments.append([])

    # Wenn gar keine Segmentierung klappte (tttool gibt manchmal kein Echo),
    # versuche die Ausgabe anhand von bekannten Mustern aufzuteilen
    if current_oid_idx <= 1 and len(lines) > 2:
        # Fallback: alle Zeilen nach Leerzeilen / Prompt-Zeilen splitten
        segments = []
        current_segment = []
        for line in lines:
            stripped = line.strip()
            # Prompt-Zeichen als Segment-Trenner
            if re.match(r'^[>?]\s*$', stripped) or stripped == "":
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []
            else:
                current_segment.append(stripped)
        if current_segment:
            segments.append(current_segment)

        # Auffüllen
        while len(segments) < len(oids):
            segments.append([])

    # Jetzt jedes Segment analysieren
    for i, oid in enumerate(oids):
        seg_lines = segments[i] if i < len(segments) else []
        raw = "\n".join(seg_lines)

        plays_audio = False
        audio_files = []
        has_error = False
        is_game_action = False

        for sl in seg_lines:
            # Audio-Wiedergabe erkennen
            if audio_pattern.search(sl):
                plays_audio = True
                # Audio-Index extrahieren
                idx_match = audio_index_pattern.findall(sl)
                audio_files.extend(int(x) for x in idx_match)

            # Auch einfache Zeilen die nur eine Zahl sind (Audio-Index)
            # tttool gibt manchmal nur den Index aus
            if re.match(r'^\d+$', sl.strip()):
                plays_audio = True
                audio_files.append(int(sl.strip()))

            # "Nichts bekannt" → OID inaktiv
            if nothing_pattern.search(sl):
                has_error = True

            # Spielaktion
            if game_action_pattern.search(sl):
                is_game_action = True

        results[oid] = {
            "response": seg_lines,
            "plays_audio": plays_audio,
            "audio_files": audio_files,
            "has_error": has_error,
            "is_game_action": is_game_action,
            "raw": raw,
        }

    return results


# ── Spieltest-Sequenzen ───────────────────────────────────────────────────────

def test_game_sequences(gme_path: Path, game_oids: list[int],
                        all_active_oids: list[int],
                        verbose: bool = False) -> list[dict]:
    """Testet Spiel-Startsequenzen.

    Für jeden Spiel-OID:
      1. Sende den Start-OID
      2. Sende 3-5 zufällige aktive OIDs als "Antworten"
      3. Prüfe ob das Spiel reagiert (Audio, Zustandsänderungen)

    Gibt eine Liste von Test-Ergebnissen zurück.
    """
    import random
    results = []

    # Potenzielle Antwort-OIDs (alle aktiven OIDs die nicht selbst Spiel-Starts sind)
    answer_candidates = [o for o in all_active_oids if o not in game_oids]

    for game_oid in game_oids:
        # Sequenz: Start-OID → 5 zufällige Antwort-OIDs
        if answer_candidates:
            answers = random.sample(
                answer_candidates,
                min(5, len(answer_candidates))
            )
        else:
            answers = []

        sequence = [game_oid] + answers

        if verbose:
            print(f"  {c(BLUE, 'ℹ')} Spiel-OID {game_oid}: Sequenz {sequence}")

        play_results = run_tttool_play(gme_path, sequence)

        # Auswertung
        start_result = play_results.get(game_oid, {})
        start_ok = start_result.get("plays_audio", False) or start_result.get("is_game_action", False)

        answer_responses = 0
        for ans_oid in answers:
            r = play_results.get(ans_oid, {})
            if r.get("plays_audio") or r.get("is_game_action"):
                answer_responses += 1

        test = {
            "game_oid": game_oid,
            "sequence": sequence,
            "start_responds": start_ok,
            "start_raw": start_result.get("raw", ""),
            "answer_responses": answer_responses,
            "answers_tested": len(answers),
        }
        results.append(test)

    return results


# ── OID-Range Parser (für --oids Argument) ────────────────────────────────────

def parse_oid_spec(spec: str) -> list[int]:
    """Parst OID-Spezifikation wie '1,5,10-20,42'."""
    oids = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            oids.extend(range(int(a), int(b) + 1))
        else:
            oids.append(int(part))
    return sorted(set(oids))


# ── Hauptroutine ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Automatischer Spieltest für Tiptoi GME-Dateien",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
TESTS
  A) OID-Scan       Alle aktiven OIDs an tttool play senden und Reaktion
                    klassifizieren: ♪ Audio, ⚙ Spielaktion, · still, ✗ Fehler
  B) Spiel-Sequenz  Spiel-OIDs aus YAML erkennen (J/P/G-Befehle), Start-OID
                    + zufällige Antwort-OIDs senden, Reaktion prüfen

BEISPIELE
  %(prog)s Feuerwehr.gme                   Alle aktiven OIDs testen
  %(prog)s Feuerwehr.gme -v                Detailausgabe pro OID
  %(prog)s Feuerwehr.gme -g                Nur Spiel-OIDs + Sequenztest
  %(prog)s Feuerwehr.gme --oids 1,5,10-20  Bestimmte OIDs testen
  %(prog)s Feuerwehr.gme -j                JSON-Ausgabe (für Scripting)
  %(prog)s Feuerwehr.gme -j -v             JSON mit per-OID Details

EXIT-CODES
  0  Alle Tests bestanden
  1  Mindestens ein Spiel reagiert nicht auf Start-OID
  2  Schwere Fehler (>50%% der OIDs fehlerhaft)

UMGEBUNGSVARIABLEN
  TTTOOL  Pfad zu tttool (Standard: ~/.local/bin/tttool)

INTEGRATION
  Wird automatisch von test_gme.sh --auto-play aufgerufen.
  Kann auch standalone oder in CI-Pipelines verwendet werden.
""",
    )
    parser.add_argument("gme", help="Pfad zur GME-Datei")
    parser.add_argument(
        "--games", "-g",
        action="store_true",
        help="Nur Spiel-OIDs testen (Sequenztest mit Antworten)",
    )
    parser.add_argument(
        "--oids",
        type=str,
        default=None,
        metavar="SPEC",
        help="Bestimmte OIDs testen (z.B. '1,5,10-20,42')",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Detaillierte Ausgabe pro OID (Kategorie + Rohausgabe)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Ergebnis als JSON ausgeben (für Weiterverarbeitung)",
    )
    parser.add_argument(
        "--tttool",
        default=None,
        metavar="PFAD",
        help=f"Pfad zu tttool (Standard: {TTTOOL})",
    )
    parser.add_argument(
        "--yaml",
        default=None,
        metavar="PFAD",
        help="Pfad zur exportierten YAML (wird sonst automatisch erzeugt)",
    )
    args = parser.parse_args()

    if args.tttool:
        _set_tttool(args.tttool)

    gme_path = Path(args.gme)
    if not gme_path.exists():
        print(f"Fehler: {gme_path} nicht gefunden", file=sys.stderr)
        sys.exit(1)

    # ── OID-Bereich lesen ─────────────────────────────────────────────────
    first_oid, last_oid = read_oid_range(gme_path)
    active_oids = read_active_oids(gme_path)

    if not args.json:
        print(f"{c(BOLD, '═══ Auto-Play: ' + gme_path.name + ' ═══')}")
        print(f"  OID-Bereich:   {first_oid} – {last_oid}")
        print(f"  Aktive OIDs:   {len(active_oids)} von {last_oid - first_oid + 1}")

    # ── YAML für Spielerkennung ───────────────────────────────────────────
    yaml_path = None
    game_info = {"game_oids": [], "game_names": {}, "answer_oids": []}

    if args.yaml:
        yaml_path = Path(args.yaml)
    else:
        # Temporäre YAML erzeugen
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / f"{gme_path.stem}.yaml"
            try:
                subprocess.run(
                    [TTTOOL, "export", str(gme_path), str(yaml_path)],
                    capture_output=True, text=True, timeout=30,
                )
                if yaml_path.exists():
                    game_info = extract_yaml_games(yaml_path)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # Tests in diesem Block ausführen, solange tmpdir existiert
            _run_tests(args, gme_path, active_oids, game_info)
            return

    # Falls --yaml angegeben
    if yaml_path and yaml_path.exists():
        game_info = extract_yaml_games(yaml_path)

    _run_tests(args, gme_path, active_oids, game_info)


def _run_tests(args, gme_path: Path, active_oids: list[int], game_info: dict):
    """Führt die eigentlichen Tests durch."""

    # ── Welche OIDs testen? ───────────────────────────────────────────────
    if args.oids:
        test_oids = parse_oid_spec(args.oids)
        if not args.json:
            print(f"  Zu testen:     {len(test_oids)} OIDs (manuell)")
    elif args.games:
        test_oids = game_info.get("game_oids", [])
        if not test_oids:
            # Fallback: alle aktiven OIDs testen
            if not args.json:
                print(f"  {c(YELLOW, '⚠')} Keine Spiel-OIDs in YAML erkannt, teste alle aktiven OIDs")
            test_oids = active_oids
        else:
            if not args.json:
                print(f"  Spiel-OIDs:    {len(test_oids)}")
    else:
        test_oids = active_oids
        if not args.json:
            print(f"  Zu testen:     {len(test_oids)} aktive OIDs")

    if not test_oids:
        if not args.json:
            print(f"  {c(RED, '✗')} Keine OIDs zum Testen")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════════
    # Test A: Alle OIDs einzeln durchspielen
    # ══════════════════════════════════════════════════════════════════════

    if not args.json:
        print(f"\n{c(BOLD, '── OID-Scan ──')}")
        print(f"  Sende {len(test_oids)} OIDs an tttool play ...")

    play_results = run_tttool_play(gme_path, test_oids)

    # Statistik
    stats = {
        "total": len(test_oids),
        "plays_audio": 0,
        "game_actions": 0,
        "no_response": 0,
        "errors": 0,
        "audio_only": 0,
    }
    per_oid = {}

    for oid in test_oids:
        r = play_results.get(oid, {})
        category = "silent"

        if r.get("has_error"):
            stats["errors"] += 1
            category = "error"
        elif r.get("plays_audio") and r.get("is_game_action"):
            stats["plays_audio"] += 1
            stats["game_actions"] += 1
            category = "audio+game"
        elif r.get("plays_audio"):
            stats["plays_audio"] += 1
            stats["audio_only"] += 1
            category = "audio"
        elif r.get("is_game_action"):
            stats["game_actions"] += 1
            category = "game"
        else:
            stats["no_response"] += 1
            category = "silent"

        per_oid[oid] = {
            "category": category,
            "audio_files": r.get("audio_files", []),
            "raw": r.get("raw", ""),
        }

        if args.verbose and not args.json:
            symbol = {
                "audio": c(GREEN, "♪"),
                "game": c(BLUE, "⚙"),
                "audio+game": c(GREEN, "♪⚙"),
                "error": c(RED, "✗"),
                "silent": c(YELLOW, "·"),
            }.get(category, "?")
            detail = r.get("raw", "").replace("\n", " | ")[:80]
            print(f"    {symbol} OID {oid:4d}: {detail}")

    if not args.json:
        print(f"\n  {c(BOLD, 'Ergebnis OID-Scan:')}")
        print(f"    Getestet:          {stats['total']}")
        if stats["plays_audio"]:
            print(f"    {c(GREEN, '♪')} Audio abgespielt:  {stats['plays_audio']}")
        if stats["game_actions"]:
            print(f"    {c(BLUE, '⚙')} Spiel-Aktionen:   {stats['game_actions']}")
        if stats["audio_only"]:
            print(f"    {c(GREEN, '♪')} Nur Audio:         {stats['audio_only']}")
        if stats["no_response"]:
            print(f"    {c(YELLOW, '·')} Keine Reaktion:    {stats['no_response']}")
        if stats["errors"]:
            print(f"    {c(RED, '✗')} Fehler:            {stats['errors']}")

    # ══════════════════════════════════════════════════════════════════════
    # Test B: Spiel-Sequenzen (wenn Spiel-OIDs erkannt)
    # ══════════════════════════════════════════════════════════════════════

    game_oids = game_info.get("game_oids", [])
    game_results = []

    if game_oids:
        if not args.json:
            print(f"\n{c(BOLD, '── Spiel-Sequenztest ──')}")
            print(f"  {len(game_oids)} Spiel-OIDs erkannt: {game_oids[:10]}"
                  f"{'...' if len(game_oids) > 10 else ''}")

        game_results = test_game_sequences(
            gme_path, game_oids, active_oids, verbose=args.verbose
        )

        games_ok = sum(1 for g in game_results if g["start_responds"])
        games_fail = len(game_results) - games_ok

        if not args.json:
            print(f"\n  {c(BOLD, 'Ergebnis Spieltest:')}")
            for g in game_results:
                if g["start_responds"]:
                    ans = f"{g['answer_responses']}/{g['answers_tested']} Antworten"
                    print(f"    {c(GREEN, '✓')} OID {g['game_oid']}: "
                          f"Start OK, {ans}")
                else:
                    print(f"    {c(RED, '✗')} OID {g['game_oid']}: "
                          f"Keine Reaktion auf Start-OID")

            if games_fail == 0 and games_ok > 0:
                print(f"\n  {c(GREEN, '✓')} Alle {games_ok} Spiele reagieren auf Start-OID")
            elif games_fail > 0:
                print(f"\n  {c(RED, '✗')} {games_fail} von {len(game_results)} "
                      f"Spielen reagieren NICHT")

    # ══════════════════════════════════════════════════════════════════════
    # JSON-Ausgabe
    # ══════════════════════════════════════════════════════════════════════

    if args.json:
        output = {
            "gme": str(gme_path),
            "oid_range": {"first": read_oid_range(gme_path)[0],
                          "last": read_oid_range(gme_path)[1]},
            "active_oids": len(active_oids),
            "stats": stats,
            "game_oids_detected": game_oids,
            "game_results": game_results,
        }
        if args.verbose:
            output["per_oid"] = per_oid
        print(json.dumps(output, indent=2, ensure_ascii=False))

    # ── Exit-Code ─────────────────────────────────────────────────────────
    # 0 = alles ok, 1 = Spiele defekt, 2 = schwere Fehler
    if game_results:
        games_fail = sum(1 for g in game_results if not g["start_responds"])
        if games_fail > 0:
            sys.exit(1)

    if stats["errors"] > stats["total"] * 0.5:
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
