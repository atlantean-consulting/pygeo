#!/usr/bin/env python3
"""
Geomantic House Chart — 12-House Astrological Layout

Maps the 16 shield chart figures to the 12 astrological houses plus
Witnesses, Judge, and Reconciler in a traditional house chart grid.
The houses are arranged counter-clockwise from the ascendant (House 1)
on the left, with derived figures in the center.

House assignments follow the standard Western geomantic tradition:
  Houses 1-4:   Mothers I-IV
  Houses 5-8:   Daughters V-VIII
  Houses 9-12:  Nieces IX-XII
  Center:       Right Witness, Left Witness, Judge, Reconciler
"""

import hashlib
import io
import json
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from geomancy import (
    FIGURES, ROLE_LABELS, read_entropy, derive_chart, get_line,
    render_figure_lines, log_reading, LOG_PATH,
    RESET, BOLD, DIM,
    C_MOTHER, C_DAUGHTER, C_NIECE, C_WITNESS, C_JUDGE, C_RECONCILER,
)

# ─────────────────────────────────────────────────────────────────────────────
# House Significations
# ─────────────────────────────────────────────────────────────────────────────

HOUSES = {
    1:  {"name": "Querent",  "desc": "The self, body, and present circumstances"},
    2:  {"name": "Wealth",   "desc": "Money, possessions, material resources"},
    3:  {"name": "Kindred",  "desc": "Siblings, neighbors, short journeys, letters"},
    4:  {"name": "Home",     "desc": "Family, property, father, foundations"},
    5:  {"name": "Children", "desc": "Pleasure, creativity, gambling, offspring"},
    6:  {"name": "Health",   "desc": "Illness, servants, daily work, small animals"},
    7:  {"name": "Partners", "desc": "Marriage, partnerships, open enemies, contracts"},
    8:  {"name": "Death",    "desc": "Inheritance, transformation, others' resources"},
    9:  {"name": "Journeys", "desc": "Long travel, higher learning, religion, dreams"},
    10: {"name": "Career",   "desc": "Reputation, authority, mother, public standing"},
    11: {"name": "Friends",  "desc": "Hopes, wishes, allies, social groups"},
    12: {"name": "Secrets",  "desc": "Hidden enemies, self-undoing, confinement"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Chart Grid Layout
# ─────────────────────────────────────────────────────────────────────────────

# 4×4 grid matching the traditional house chart sketch:
#   12  11  10   9      (top: houses across)
#    1  LW  RW   8      (center row 1: houses flanking witnesses)
#    2   J   R   7      (center row 2: houses flanking judge/reconciler)
#    3   4   5   6      (bottom: houses across)

GRID = [
    [("house", 12), ("house", 11), ("house", 10), ("house", 9)],
    [("house", 1),  ("center", "LW"), ("center", "RW"), ("house", 8)],
    [("house", 2),  ("center", "J"),  ("center", "R"),  ("house", 7)],
    [("house", 3),  ("house", 4),  ("house", 5),  ("house", 6)],
]

CELL_W = 18  # inner width of each cell

HOUSE_COLORS = {
    1: C_MOTHER, 2: C_MOTHER, 3: C_MOTHER, 4: C_MOTHER,
    5: C_DAUGHTER, 6: C_DAUGHTER, 7: C_DAUGHTER, 8: C_DAUGHTER,
    9: C_NIECE, 10: C_NIECE, 11: C_NIECE, 12: C_NIECE,
}

CENTER_INFO = {
    "LW": (12, C_WITNESS, "L.Witness"),
    "RW": (13, C_WITNESS, "R.Witness"),
    "J":  (14, C_JUDGE, "Judge"),
    "R":  (15, C_RECONCILER, "Reconciler"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Perfection Engine
# ─────────────────────────────────────────────────────────────────────────────
# The modes of perfection determine whether the querent (House 1) obtains
# what they seek (the quesited house). Checked in order from most direct
# to most indirect.

def houses_adjacent(h1, h2):
    """True if houses h1 and h2 (1-12) are adjacent in the wheel."""
    diff = abs(h1 - h2)
    return diff == 1 or diff == 11


def find_figure_in_houses(chart, figure, exclude=None):
    """Return house numbers (1-12) containing the figure, minus exclusions."""
    exclude = exclude or set()
    return [h for h in range(1, 13) if chart[h - 1] == figure and h not in exclude]


def check_perfection(chart, quesited):
    """Check all modes of perfection between House 1 and the quesited house.

    Returns a list of (mode_name, detail_string) tuples for every mode found.
    An empty list means denial — no perfection.
    """
    q1 = chart[0]
    qx = chart[quesited - 1]
    q1_name = FIGURES[q1]["name"]
    qx_name = FIGURES[qx]["name"]
    results = []

    # ── Occupation ──────────────────────────────────────────────────────────
    # Same figure in both houses. Strongest mode; return immediately.
    if q1 == qx:
        results.append(("occupation",
            f"{q1_name} occupies both House 1 and House {quesited}"))
        return results

    # Locate every house where each significator appears
    q1_all = find_figure_in_houses(chart, q1)
    qx_all = find_figure_in_houses(chart, qx)
    # Same lists excluding the original positions
    q1_other = find_figure_in_houses(chart, q1, exclude={1})
    qx_other = find_figure_in_houses(chart, qx, exclude={quesited})

    # ── Conjunction ─────────────────────────────────────────────────────────
    # Querent's figure passes to a house adjacent to the quesited house,
    # or vice versa. The figure approaches the other's doorstep.
    for h in q1_other:
        if houses_adjacent(h, quesited):
            results.append(("conjunction",
                f"{q1_name} (querent) passes to H{h}, "
                f"adjacent to quesited H{quesited}"))
    for h in qx_other:
        if houses_adjacent(h, 1):
            results.append(("conjunction",
                f"{qx_name} (quesited) passes to H{h}, "
                f"adjacent to querent H1"))

    # ── Mutation ────────────────────────────────────────────────────────────
    # Both significators appear in a pair of adjacent houses elsewhere —
    # they meet at a neutral location, away from their original houses.
    for h1 in q1_other:
        for h2 in qx_other:
            if houses_adjacent(h1, h2) and h1 != quesited and h2 != 1:
                results.append(("mutation",
                    f"{q1_name} in H{h1} meets {qx_name} in H{h2}"))

    # ── Translation ─────────────────────────────────────────────────────────
    # A third figure (neither significator) acts as go-between: it appears
    # adjacent to a house with the querent's figure AND adjacent to a house
    # with the quesited figure.
    all_figs = set(chart[:12])
    for f3 in sorted(all_figs - {q1, qx}):
        f3_houses = find_figure_in_houses(chart, f3)
        f3_name = FIGURES[f3]["name"]

        adj_q1 = [(fh, qh) for fh in f3_houses
                  for qh in q1_all if houses_adjacent(fh, qh)]
        adj_qx = [(fh, qh) for fh in f3_houses
                  for qh in qx_all if houses_adjacent(fh, qh)]

        if adj_q1 and adj_qx:
            fh1, qh1 = adj_q1[0]
            fh2, qh2 = adj_qx[0]
            if fh1 == fh2:
                results.append(("translation",
                    f"{f3_name} (H{fh1}) translates between "
                    f"{q1_name} (H{qh1}) and {qx_name} (H{qh2})"))
            else:
                results.append(("translation",
                    f"{f3_name} translates: H{fh1} touches "
                    f"{q1_name} (H{qh1}), H{fh2} touches "
                    f"{qx_name} (H{qh2})"))

    return results


MODE_DESCS = {
    "occupation":  "Direct and immediate. The querent and the quesited are already one.",
    "conjunction": "Approaching contact. The matter comes together directly.",
    "mutation":    "Indirect means. The parties meet through a third circumstance.",
    "translation": "A go-between carries the matter from one party to the other.",
}

MODE_SYMBOLS = {
    "occupation":  "●",
    "conjunction": "◐",
    "mutation":    "◑",
    "translation": "◈",
}


def print_perfection(chart, quesited):
    """Print perfection analysis between House 1 and the quesited house."""
    width = 78
    q1 = chart[0]
    qx = chart[quesited - 1]
    q1_name = FIGURES[q1]["name"]
    qx_name = FIGURES[qx]["name"]
    qx_color = HOUSE_COLORS[quesited]

    print(f"\n{BOLD}{'═' * width}{RESET}")
    print(f"{BOLD}{'PERFECTION ANALYSIS':^{width}}{RESET}")
    print(f"{BOLD}{'═' * width}{RESET}\n")

    print(f"  Querent:   {C_MOTHER}{BOLD}H1{RESET}  {C_MOTHER}{q1_name}{RESET}")
    print(f"  Quesited:  {qx_color}{BOLD}H{quesited}{RESET}  {qx_color}{qx_name}{RESET}")
    print(f"  {DIM}{HOUSES[quesited]['name']}: {HOUSES[quesited]['desc']}{RESET}")
    print()

    results = check_perfection(chart, quesited)

    if not results:
        print(f"  {BOLD}DENIAL{RESET} — No mode of perfection found.")
        print(f"  {DIM}The querent does not obtain what they seek.{RESET}")
        print()
    else:
        seen = set()
        for mode, detail in results:
            sym = MODE_SYMBOLS.get(mode, "•")
            if mode not in seen:
                print(f"  {C_JUDGE}{BOLD}{sym} {mode.upper()}{RESET}")
                print(f"    {DIM}{MODE_DESCS[mode]}{RESET}")
                seen.add(mode)
            print(f"    {detail}")
            print()

    # Judge as confirmation / modification
    judge = chart[14]
    judge_info = FIGURES[judge]
    print(f"  {C_JUDGE}Judge: {judge_info['name']} — {judge_info['keyword']}{RESET}")
    if results:
        print(f"  {DIM}The Judge confirms or modifies the perfection above.{RESET}")
    else:
        print(f"  {DIM}Consult the Judge's meaning for nuance despite denial.{RESET}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Cell Rendering
# ─────────────────────────────────────────────────────────────────────────────

def center_in_cell(text, vis_w):
    """Center text of visible width vis_w within CELL_W characters."""
    if vis_w >= CELL_W:
        return text
    left = (CELL_W - vis_w) // 2
    right = CELL_W - vis_w - left
    return " " * left + text + " " * right


def make_cell(chart, cell_type, cell_value):
    """Build a cell's content as a list of (ansi_text, visible_width) tuples."""
    lines = []

    if cell_type == "house":
        h = cell_value
        idx = h - 1
        bits = chart[idx]
        info = FIGURES[bits]
        color = HOUSE_COLORS[h]

        # House label
        label = f"H{h} · {HOUSES[h]['name']}"
        lines.append((f"{DIM}{label}{RESET}", len(label)))

        # Figure dots (4 lines)
        for dl in render_figure_lines(bits, element_color=True):
            lines.append((dl, 5))

        # Figure name
        name = info["name"]
        lines.append((f"{color}{BOLD}{name}{RESET}", len(name)))

    else:  # center
        lbl = cell_value
        idx, color, full_label = CENTER_INFO[lbl]
        bits = chart[idx]
        info = FIGURES[bits]

        # Center label
        lines.append((f"{color}{BOLD}{full_label}{RESET}", len(full_label)))

        # Figure dots (4 lines)
        for dl in render_figure_lines(bits, element_color=True):
            lines.append((dl, 5))

        # Figure name
        name = info["name"]
        lines.append((f"{color}{name}{RESET}", len(name)))

    return lines


# ─────────────────────────────────────────────────────────────────────────────
# House Chart Rendering
# ─────────────────────────────────────────────────────────────────────────────

def render_house_chart(chart):
    """Render the house chart as a bordered 4×4 grid."""
    # Build all cells
    cells = []
    for row_def in GRID:
        row_cells = []
        for ct, cv in row_def:
            row_cells.append(make_cell(chart, ct, cv))
        cells.append(row_cells)

    # Border strings
    dash = "─" * CELL_W
    dbl = "═" * CELL_W

    # Row separators — center 2×2 uses double borders
    hr_top  = "┌" + "┬".join([dash] * 4) + "┐"
    hr_r0r1 = "├" + dash + "╔" + dbl + "╦" + dbl + "╗" + dash + "┤"
    hr_r1r2 = "├" + dash + "╠" + dbl + "╬" + dbl + "╣" + dash + "┤"
    hr_r2r3 = "├" + dash + "╚" + dbl + "╩" + dbl + "╝" + dash + "┤"
    hr_bot  = "└" + "┴".join([dash] * 4) + "┘"

    separators = [hr_r0r1, hr_r1r2, hr_r2r3]

    # Column separators per row
    # Rows 0, 3: all single │
    # Rows 1, 2: │ on edges, ║ between center cells
    col_sep = {
        0: ["│"] * 5,
        1: ["│", "║", "║", "║", "│"],
        2: ["│", "║", "║", "║", "│"],
        3: ["│"] * 5,
    }

    print()
    print(hr_top)

    for ri, row in enumerate(cells):
        max_lines = max(len(c) for c in row)
        sep = col_sep[ri]

        for li in range(max_lines):
            parts = []
            for ci, cell in enumerate(row):
                if li < len(cell):
                    text, vw = cell[li]
                    parts.append(center_in_cell(text, vw))
                else:
                    parts.append(" " * CELL_W)

            # Build line with appropriate column separators
            line = sep[0]
            for ci in range(4):
                line += parts[ci] + sep[ci + 1]
            print(line)

        if ri < 3:
            print(separators[ri])

    print(hr_bot)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# House Summary Table
# ─────────────────────────────────────────────────────────────────────────────

def print_house_summary(chart):
    """Print a compact table of all 12 houses with their figures."""
    width = 78
    print(f"\n{BOLD}{'═' * width}{RESET}")
    print(f"{BOLD}{'HOUSE SUMMARY':^{width}}{RESET}")
    print(f"{BOLD}{'═' * width}{RESET}\n")

    for h in range(1, 13):
        idx = h - 1
        bits = chart[idx]
        info = FIGURES[bits]
        color = HOUSE_COLORS[h]
        house_info = HOUSES[h]

        # Two-column layout: houses 1-6 left, 7-12 right
        name = info["name"]
        label = f"H{h:>2}  {house_info['name']:<10}"
        print(f"  {color}{label}{RESET}  {name:<16} {DIM}{house_info['desc']}{RESET}")

    print()


# ─────────────────────────────────────────────────────────────────────────────
# Interpretation
# ─────────────────────────────────────────────────────────────────────────────

def interpret_box(chart, idx, role_name, color, width=78):
    """Print a bordered interpretation box for one figure."""
    bits = chart[idx]
    fig = FIGURES[bits]
    header = f"{fig['name']} — {fig['english']}"

    print(f"{color}{BOLD}┌{'─' * (width - 2)}┐{RESET}")
    print(f"{color}{BOLD}│ {role_name:<{width - 4}} │{RESET}")
    print(f"{color}{BOLD}│ {header:<{width - 4}} │{RESET}")
    details = f"{fig['keyword']} · {fig['planet']} · {fig['element']}"
    print(f"{color}│ {details:<{width - 4}} │{RESET}")
    print(f"{color}├{'─' * (width - 2)}┤{RESET}")

    if idx == 14:
        text = fig["judge_meaning"]
    else:
        text = fig["meaning"]

    for line in textwrap.wrap(text, width - 4):
        print(f"{color}│ {line:<{width - 4}} │{RESET}")
    print(f"{color}└{'─' * (width - 2)}┘{RESET}")
    print()


def print_house_focus(chart, house, width=78):
    """Print interpretation for a single house — lightweight focus."""
    idx = house - 1
    interpret_box(chart, idx,
                  f"HOUSE {house} — {HOUSES[house]['name'].upper()} "
                  f"({HOUSES[house]['desc']})",
                  HOUSE_COLORS[house], width)


def print_interpretation(chart):
    """Print interpretive text for key positions."""
    width = 78

    print(f"\n{BOLD}{'═' * width}{RESET}")
    print(f"{BOLD}{'READING':^{width}}{RESET}")
    print(f"{BOLD}{'═' * width}{RESET}\n")

    # Always interpret the querent (House 1)
    interpret_box(chart, 0,
                  f"HOUSE 1 — THE QUERENT ({HOUSES[1]['desc']})",
                  C_MOTHER, width)

    # Judge
    interpret_box(chart, 14,
                  "THE JUDGE — The Final Answer",
                  C_JUDGE, width)

    # Witnesses
    interpret_box(chart, 12,
                  "RIGHT WITNESS — The Root of the Matter",
                  C_WITNESS, width)
    interpret_box(chart, 13,
                  "LEFT WITNESS — The Direction Ahead",
                  C_WITNESS, width)

    # Reconciler
    interpret_box(chart, 15,
                  "THE RECONCILER — Synthesis of Origin and Outcome",
                  C_RECONCILER, width)

    # Duplicate detection
    from collections import Counter
    figure_counts = Counter(chart[:15])
    repeats = {b: c for b, c in figure_counts.items() if c > 1}
    if repeats:
        print(f"{BOLD}Notable Repetitions:{RESET}")
        for bits, count in sorted(repeats.items(), key=lambda x: -x[1]):
            fig = FIGURES[bits]
            positions = []
            for i in range(15):
                if chart[i] == bits:
                    if i < 12:
                        positions.append(f"H{i+1}")
                    else:
                        positions.append(ROLE_LABELS[i])
            print(f"  {fig['name']} appears {count} times "
                  f"(positions: {', '.join(positions)})")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────

def save_house_reading(question, chart):
    """Save the current house chart reading as a Markdown file."""
    timestamp = datetime.now()
    slug = timestamp.strftime("%Y%m%d_%H%M%S")
    filename = Path.home() / f"geomancy_house_{slug}.md"

    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    if question:
        print(f"**Question:** {question}\n")
    print(f"**Cast:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
    render_house_chart(chart)
    print_house_summary(chart)
    print_interpretation(chart)
    sys.stdout = old_stdout

    with open(filename, "w") as f:
        f.write("# Geomantic House Chart Reading\n\n")
        f.write("```\n")
        f.write(buf.getvalue())
        f.write("```\n")

    return filename


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

HEADER = f"""{BOLD}
  ╔═══════════════════════════════════════════╗
  ║         GEOMANTIC HOUSE CHART             ║
  ║           /dev/urandom Oracle             ║
  ╚═══════════════════════════════════════════╝{RESET}
"""

HOUSE_HELP = f"""{DIM}
  House reference:
    1  Querent       5  Children      9  Journeys
    2  Wealth        6  Health       10  Career
    3  Kindred       7  Partners     11  Friends
    4  Home          8  Death        12  Secrets

  Commands after a cast:
    1-12      Focus interpretation on that house
    p7        Focus + perfection analysis for H7
    2 p10     Compound: focus H2, then focus + perfection H10
    s / sq    Save reading / save & quit
    q / qd    Quit / delete log & quit{RESET}
"""


def main():
    print(HEADER)

    while True:
        print(f"{DIM}Focus on your question. Type it below (or press Enter for silence).{RESET}")
        try:
            question = input(f"\n{BOLD}Your question: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Farewell.{RESET}")
            break

        if question:
            print(f"\n{DIM}Casting for: \"{question}\"{RESET}")
        else:
            print(f"\n{DIM}Casting in silence...{RESET}")

        # Read entropy and derive chart
        mothers = read_entropy(question)
        chart = derive_chart(mothers)

        # Display house chart
        render_house_chart(chart)
        print_house_summary(chart)
        print_interpretation(chart)

        # Log
        log_reading(question if question else "(silent)", chart)
        print(f"{DIM}Reading logged to {LOG_PATH}{RESET}\n")

        # Command loop — stays on this chart until cast again or quit
        cast_again = False
        while not cast_again:
            print(f"{DIM}Enter → cast again  |  q → quit  |  s → save  |  sq → save & quit{RESET}")
            print(f"{DIM}1-12 → focus house  |  p7 → focus + perfection  |  h → help{RESET}")
            try:
                cmd = input(f"{BOLD}> {RESET}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{DIM}Farewell.{RESET}")
                return

            if cmd == "qd":
                if LOG_PATH.exists():
                    LOG_PATH.unlink()
                    print(f"\n{DIM}Log deleted. No trace remains.{RESET}")
                print(f"{DIM}Farewell.{RESET}")
                return
            elif cmd == "sq":
                f = save_house_reading(question if question else None, chart)
                print(f"\n{DIM}Reading saved to {f}{RESET}")
                print(f"{DIM}The chart is cast. Go well.{RESET}")
                return
            elif cmd == "s":
                f = save_house_reading(question if question else None, chart)
                print(f"\n{DIM}Reading saved to {f}{RESET}")
            elif cmd in ("q", "quit", "exit"):
                print(f"\n{DIM}The chart is cast. Go well.{RESET}")
                return
            elif cmd in ("h", "help"):
                print(HOUSE_HELP)
            elif cmd == "":
                cast_again = True  # break to outer loop for new cast
            else:
                # Compound command: tokens are house numbers or p<house>
                # e.g. "2 p10" → focus H2, then focus + perfection H10
                tokens = cmd.split()
                focus_done = set()
                perf_done = set()
                any_valid = False

                for token in tokens:
                    if token.startswith("p"):
                        num_part = token[1:]
                        if num_part.isdigit() and 1 <= int(num_part) <= 12:
                            h = int(num_part)
                            any_valid = True
                            if h not in focus_done:
                                focus_done.add(h)
                                print_house_focus(chart, h)
                            if h not in perf_done:
                                perf_done.add(h)
                                print_perfection(chart, h)
                    elif token.isdigit() and 1 <= int(token) <= 12:
                        h = int(token)
                        any_valid = True
                        if h not in focus_done:
                            focus_done.add(h)
                            print_house_focus(chart, h)

                if not any_valid:
                    print(f"\n{DIM}Unknown command. Type h for help.{RESET}")

        print("\n" + "─" * 78 + "\n")


if __name__ == "__main__":
    main()
