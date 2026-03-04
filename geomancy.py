#!/usr/bin/env python3
"""
Geomantic Divination Engine — /dev/urandom Oracle

Reads 2 bytes of entropy from /dev/urandom to generate a complete shield chart
using the traditional Western geomantic system. All figures beyond the four
Mothers are derived deterministically via transposition and XOR.

The entropy comes from hardware interrupts, disk timing jitter, network noise,
and other physical processes. Whether that's "random" or "meaningful" is
between you and the universe.
"""

import hashlib
import io
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# ANSI color codes
# ─────────────────────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Role colors
C_MOTHER = "\033[36m"       # Cyan
C_DAUGHTER = "\033[35m"     # Magenta
C_NIECE = "\033[33m"        # Yellow
C_WITNESS = "\033[97m"      # Bright white
C_JUDGE = "\033[1;93m"      # Bold bright yellow
C_RECONCILER = "\033[1;96m" # Bold bright cyan

# Element colors for dots
C_FIRE = "\033[31m"         # Red
C_WATER = "\033[34m"        # Blue
C_AIR = "\033[33m"          # Yellow
C_EARTH = "\033[32m"        # Green

ELEMENT_COLORS = {
    "Fire": C_FIRE,
    "Water": C_WATER,
    "Air": C_AIR,
    "Earth": C_EARTH,
}

# ─────────────────────────────────────────────────────────────────────────────
# The 16 Geomantic Figures
# ─────────────────────────────────────────────────────────────────────────────
# Bits are Fire (MSB), Air, Water, Earth (LSB). 1 = single dot, 0 = double.
# Cross-referenced with Digital Ambler and Greer's Art and Practice of Geomancy.

FIGURES = {
    0b0000: {
        "name": "Populus",
        "english": "The People",
        "keyword": "Gathering",
        "planet": "Moon",
        "element": "Water",
        "meaning": (
            "A crowd, a gathering, the collective. Populus reflects passivity "
            "and receptivity — the situation is shaped by the people around you "
            "rather than by your own action. Nothing is fixed; everything flows."
        ),
        "judge_meaning": (
            "The answer depends on the crowd. You are not the prime mover here — "
            "the situation is diffuse, collective, and changeable. Seek counsel "
            "from others and watch the currents before committing."
        ),
    },
    0b0001: {
        "name": "Tristitia",
        "english": "Sorrow",
        "keyword": "Contraction",
        "planet": "Saturn",
        "element": "Earth",
        "meaning": (
            "Sorrow, heaviness, turning inward. Tristitia is the weight of "
            "earthbound gravity — things sink, settle, compress. Not necessarily "
            "disaster, but a period of difficulty and introspection. Foundations "
            "are being tested."
        ),
        "judge_meaning": (
            "The matter brings sorrow or disappointment. This is not the time "
            "for expansion. Accept the contraction, learn from it, and build "
            "stronger foundations. The answer leans toward no."
        ),
    },
    0b0010: {
        "name": "Albus",
        "english": "The White",
        "keyword": "Clarity",
        "planet": "Mercury",
        "element": "Water",
        "meaning": (
            "Wisdom, clarity, peace of mind. Albus is the still pool that "
            "reflects truly. Thought is clear, perception is accurate, and "
            "careful analysis will serve you well. Favors intellectual and "
            "spiritual pursuits."
        ),
        "judge_meaning": (
            "Clarity prevails. The situation calls for calm thought and careful "
            "discernment rather than bold action. The answer is generally "
            "favorable, especially for matters of learning, counsel, or healing."
        ),
    },
    0b0011: {
        "name": "Fortuna Major",
        "english": "The Greater Fortune",
        "keyword": "Triumph",
        "planet": "Sun",
        "element": "Earth",
        "meaning": (
            "Great fortune, stable and lasting success. Fortuna Major is the "
            "inner power that draws success toward you — achievement through "
            "merit, not luck. Protective, grounding, and deeply favorable."
        ),
        "judge_meaning": (
            "A strongly favorable answer. Success is assured and will endure. "
            "Whatever you are asking about has the weight of destiny behind it. "
            "Proceed with confidence."
        ),
    },
    0b0100: {
        "name": "Rubeus",
        "english": "The Red",
        "keyword": "Turmoil",
        "planet": "Mars",
        "element": "Air",
        "meaning": (
            "Passion, violence, upheaval. Rubeus is Mars at its most chaotic — "
            "tempers flare, situations reverse, and hidden things surface. "
            "Traditionally unfavorable, though it can indicate raw power "
            "and necessary destruction."
        ),
        "judge_meaning": (
            "Danger and disruption. The situation is volatile and likely to "
            "produce harm or reversal. Stop, reconsider, and do not act in "
            "anger. The answer is unfavorable — walk away if you can."
        ),
    },
    0b0101: {
        "name": "Acquisitio",
        "english": "Gain",
        "keyword": "Acquisition",
        "planet": "Jupiter",
        "element": "Air",
        "meaning": (
            "Gain, profit, things coming toward you. Acquisitio is the "
            "inward-pointing figure — wealth, knowledge, and resources flow "
            "in your direction. Strongly favorable for material questions and "
            "business ventures."
        ),
        "judge_meaning": (
            "You will gain what you seek. The answer is favorable, especially "
            "for matters of money, property, or material advancement. What you "
            "acquire now will serve you well."
        ),
    },
    0b0110: {
        "name": "Conjunctio",
        "english": "Conjunction",
        "keyword": "Union",
        "planet": "Mercury",
        "element": "Air",
        "meaning": (
            "Union, meeting, combination. Conjunctio is the crossroads where "
            "things come together — partnerships form, paths converge, contracts "
            "are signed. Favorable for joining but asks: are you sure you want "
            "to be bound?"
        ),
        "judge_meaning": (
            "The matter involves a meeting or joining. The answer depends on "
            "what is being combined — Conjunctio is neutral in itself. Look to "
            "the Witnesses and Mothers for whether this union serves you."
        ),
    },
    0b0111: {
        "name": "Caput Draconis",
        "english": "Head of the Dragon",
        "keyword": "Threshold",
        "planet": "North Node",
        "element": "Earth",
        "meaning": (
            "Beginnings, entrances, crossing a threshold. Caput Draconis is the "
            "open door ahead of you — new ventures, new phases, new cycles. "
            "Favorable for starting things but carries the weight of commitment."
        ),
        "judge_meaning": (
            "A new beginning is indicated. Step through the door. The answer "
            "favors starting something new, entering unfamiliar territory, and "
            "embracing change. What you begin now has momentum."
        ),
    },
    0b1000: {
        "name": "Laetitia",
        "english": "Joy",
        "keyword": "Elation",
        "planet": "Jupiter",
        "element": "Fire",
        "meaning": (
            "Joy, optimism, upward-moving energy. Laetitia is the figure that "
            "points to the sky — laughter, celebration, and genuine happiness. "
            "Favorable for nearly everything, though it can indicate superficial "
            "pleasure that doesn't last."
        ),
        "judge_meaning": (
            "The answer brings joy. The outcome is favorable and will lift your "
            "spirits. Celebrate what is coming, though remember that Laetitia's "
            "energy points upward and may not stay grounded forever."
        ),
    },
    0b1001: {
        "name": "Carcer",
        "english": "Prison",
        "keyword": "Restriction",
        "planet": "Saturn",
        "element": "Earth",
        "meaning": (
            "Restriction, confinement, binding. Carcer is the walls that hold "
            "you in place — for good or ill. It can mean imprisonment and delay, "
            "but also stability, commitment, and the security of strong "
            "boundaries."
        ),
        "judge_meaning": (
            "You are bound. The situation is fixed and resistant to change. "
            "If you want freedom, this is unfavorable. If you want stability "
            "and permanence, Carcer delivers. The answer is no to change, "
            "yes to holding fast."
        ),
    },
    0b1010: {
        "name": "Amissio",
        "english": "Loss",
        "keyword": "Release",
        "planet": "Venus",
        "element": "Fire",
        "meaning": (
            "Loss, things slipping away, letting go. Amissio is the outward-"
            "pointing figure — what you hold escapes your grasp. Unfavorable "
            "for keeping, but sometimes losing is the right move. What leaves "
            "was never truly yours."
        ),
        "judge_meaning": (
            "You will lose what you ask about, or it will slip away. The answer "
            "is unfavorable for possession and gain. But consider: is this loss "
            "a liberation? Sometimes the answer is to let go."
        ),
    },
    0b1011: {
        "name": "Puella",
        "english": "The Girl",
        "keyword": "Harmony",
        "planet": "Venus",
        "element": "Water",
        "meaning": (
            "Beauty, grace, harmony, and receptivity. Puella is Venus at her "
            "most magnetic — attracting rather than pursuing, creating beauty "
            "rather than forcing outcomes. Favorable for love, art, diplomacy, "
            "and anything requiring charm."
        ),
        "judge_meaning": (
            "The answer favors beauty and harmony. Approach the situation with "
            "grace rather than force. Relationships and artistic endeavors "
            "are well-starred. Let things come to you."
        ),
    },
    0b1100: {
        "name": "Fortuna Minor",
        "english": "The Lesser Fortune",
        "keyword": "Swiftness",
        "planet": "Sun",
        "element": "Fire",
        "meaning": (
            "Swift success, but unstable. Fortuna Minor is outward-moving solar "
            "energy — you can achieve what you want, but it may not last. Speed "
            "and external assistance carry the day. Act quickly before the "
            "window closes."
        ),
        "judge_meaning": (
            "Success is possible but fleeting. Move quickly and don't expect "
            "the favorable conditions to persist. The answer is yes, but with "
            "a time limit. Take what you can and don't look back."
        ),
    },
    0b1101: {
        "name": "Puer",
        "english": "The Boy",
        "keyword": "Aggression",
        "planet": "Mars",
        "element": "Fire",
        "meaning": (
            "Boldness, aggression, conflict, and raw courage. Puer is Mars "
            "charging forward — reckless but powerful. Favorable for contests, "
            "battles, and situations requiring force. Unfavorable for patience, "
            "diplomacy, or anything requiring subtlety."
        ),
        "judge_meaning": (
            "Force carries the day. The answer favors bold, direct action — "
            "but be warned that Puer's victories often come with collateral "
            "damage. Strike hard and fast, or reconsider whether force is "
            "truly what's needed."
        ),
    },
    0b1110: {
        "name": "Cauda Draconis",
        "english": "Tail of the Dragon",
        "keyword": "Departure",
        "planet": "South Node",
        "element": "Fire",
        "meaning": (
            "Endings, departures, leaving behind. Cauda Draconis is the door "
            "closing behind you — completion, release, and the severance of old "
            "ties. Favorable for ending things, unfavorable for beginning them."
        ),
        "judge_meaning": (
            "Something is ending. The answer points to completion, departure, "
            "or the need to leave something behind. Do not cling to what is "
            "passing. Close the door cleanly and move on."
        ),
    },
    0b1111: {
        "name": "Via",
        "english": "The Road",
        "keyword": "Journey",
        "planet": "Moon",
        "element": "Water",
        "meaning": (
            "Change, journey, the road itself. Via is pure movement — nothing "
            "stays the same, everything is in transit. Favorable for travel and "
            "change, but indicates instability and the impossibility of standing "
            "still."
        ),
        "judge_meaning": (
            "The answer is change itself. Nothing about this situation will "
            "remain as it is. Whether that's good or bad depends on whether "
            "you want movement or stability. The road is open — walk it."
        ),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Chart Engine
# ─────────────────────────────────────────────────────────────────────────────

def read_entropy(question=""):
    """Read 2 bytes from /dev/urandom, XOR with question hash, return 4 Mothers.

    The question text is hashed and XORed into the entropy so that the exact
    phrasing of the question influences the reading. The entropy from
    /dev/urandom remains the primary source — the question perturbs it.
    """
    with open("/dev/urandom", "rb") as f:
        seed = f.read(2)
    bits = (seed[0] << 8) | seed[1]
    if question:
        h = hashlib.sha256(question.encode("utf-8")).digest()
        bits ^= (h[0] << 8) | h[1]
        bits &= 0xFFFF
    mothers = []
    for i in range(4):
        figure = (bits >> (12 - i * 4)) & 0xF
        mothers.append(figure)
    return mothers


def get_line(figure, line):
    """Get a single line (0=Fire/top, 3=Earth/bottom) from a 4-bit figure."""
    return (figure >> (3 - line)) & 1


def derive_chart(mothers):
    """
    Derive the complete shield chart from 4 Mother figures.
    Returns a list of 16 figures (indices 0-15):
      0-3:   Mothers I-IV
      4-7:   Daughters V-VIII
      8-11:  Nieces IX-XII
      12-13: Witnesses (Right XIII, Left XIV)
      14:    Judge XV
      15:    Reconciler XVI
    """
    chart = list(mothers)  # 0-3: Mothers

    # Daughters V-VIII: transpose the Mothers' rows
    for line in range(4):
        daughter = 0
        for m in range(4):
            bit = get_line(mothers[m], line)
            daughter |= bit << (3 - m)
        chart.append(daughter)

    # Nieces IX-XII: XOR of adjacent pairs
    chart.append(chart[0] ^ chart[1])   # IX  = I ⊕ II
    chart.append(chart[2] ^ chart[3])   # X   = III ⊕ IV
    chart.append(chart[4] ^ chart[5])   # XI  = V ⊕ VI
    chart.append(chart[6] ^ chart[7])   # XII = VII ⊕ VIII

    # Witnesses XIII-XIV: XOR of Niece pairs
    chart.append(chart[8] ^ chart[9])   # XIII = IX ⊕ X (Right Witness)
    chart.append(chart[10] ^ chart[11]) # XIV  = XI ⊕ XII (Left Witness)

    # Judge XV: XOR of Witnesses
    judge = chart[12] ^ chart[13]
    chart.append(judge)

    # Reconciler XVI: Judge ⊕ Mother I
    chart.append(judge ^ chart[0])

    # Sanity check: Judge must have even popcount
    popcount = bin(judge).count("1")
    if popcount % 2 != 0:
        print(f"\033[1;31mBUG: Judge has odd popcount ({popcount}). "
              f"This should be mathematically impossible.\033[0m",
              file=sys.stderr)

    return chart


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

ROLE_LABELS = [
    "I", "II", "III", "IV",           # Mothers
    "V", "VI", "VII", "VIII",         # Daughters
    "IX", "X", "XI", "XII",           # Nieces
    "R.Wit", "L.Wit",                 # Witnesses
    "Judge", "Reconciler",            # Judge & Reconciler
]

ROLE_COLORS = {
    0: C_MOTHER, 1: C_MOTHER, 2: C_MOTHER, 3: C_MOTHER,
    4: C_DAUGHTER, 5: C_DAUGHTER, 6: C_DAUGHTER, 7: C_DAUGHTER,
    8: C_NIECE, 9: C_NIECE, 10: C_NIECE, 11: C_NIECE,
    12: C_WITNESS, 13: C_WITNESS,
    14: C_JUDGE,
    15: C_RECONCILER,
}

LINE_NAMES = ["Fire", "Air", "Water", "Earth"]


def render_figure_lines(figure_bits, element_color=False):
    """Render a figure as a list of 4 strings (one per line), centered in 5 chars."""
    lines = []
    for i in range(4):
        bit = get_line(figure_bits, i)
        if element_color:
            ec = ELEMENT_COLORS[LINE_NAMES[i]]
            if bit:
                lines.append(f"{ec}  ●  {RESET}")
            else:
                lines.append(f"{ec} ● ● {RESET}")
        else:
            if bit:
                lines.append("  ●  ")
            else:
                lines.append(" ● ● ")
    return lines


def render_chart(chart):
    """Render the full shield chart to the terminal."""
    COL_W = 16  # width per figure column (longest name: "Cauda Draconis" = 14)

    def fig_block(idx):
        """Return a list of 6 tuples for one figure: (visible_text, ansi_text, visible_width)."""
        bits = chart[idx]
        info = FIGURES[bits]
        color = ROLE_COLORS[idx]
        label = ROLE_LABELS[idx]
        name = info["name"]

        dot_lines = render_figure_lines(bits, element_color=True)
        result = []
        for dl in dot_lines:
            result.append((dl, 5))  # 5 visible chars + ANSI codes
        name_str = f"{color}{name}{RESET}"
        result.append((name_str, len(name)))
        label_str = f"{DIM}{label}{RESET}"
        result.append((label_str, len(label)))
        return result

    def print_row(indices, indent=0):
        """Print a row of figures side by side, centered per column."""
        blocks = [fig_block(i) for i in indices]
        num_lines = max(len(b) for b in blocks)
        n = len(indices)
        # Total row width in visible chars: n columns of COL_W + (n-1) gaps of 2
        row_w = n * COL_W + (n - 1) * 2
        pad = " " * indent

        for line_idx in range(num_lines):
            line_parts = []
            for col, block in enumerate(blocks):
                if line_idx < len(block):
                    ansi_str, vis_w = block[line_idx]
                else:
                    ansi_str, vis_w = (" " * COL_W, COL_W)

                # Center this item within its COL_W slot
                if vis_w < COL_W:
                    left = (COL_W - vis_w) // 2
                    right = COL_W - vis_w - left
                    line_parts.append(" " * left + ansi_str + " " * right)
                elif vis_w > COL_W:
                    # Wider than column — let it overflow symmetrically
                    overflow = vis_w - COL_W
                    trim_l = overflow // 2
                    trim_r = overflow - trim_l
                    line_parts.append(" " * (-trim_l) + ansi_str + " " * (-trim_r)
                                      if overflow == 0 else ansi_str)
                else:
                    line_parts.append(ansi_str)

            # Join columns, but for lines where items overflow COL_W,
            # we need to recalculate spacing to keep columns centered.
            # Strategy: build the line by placing each item centered at
            # its column's midpoint.
            col_centers = [COL_W // 2 + col * (COL_W + 2) for col in range(n)]
            out_chars = [" "] * row_w
            # We can't easily overlay ANSI strings into a char array,
            # so just join with separator and accept minor overflow on names.
            print(pad + "  ".join(line_parts))

    # Header
    print()
    # Layout widths: 8 cols = 8*16+7*2 = 142, half = 4*16+3*2 = 70
    ROW_W = 8 * COL_W + 7 * 2     # 142
    HALF_W = 4 * COL_W + 3 * 2    # 70

    mothers_label = f"{C_MOTHER}{'─── Mothers ───':^{HALF_W}}{RESET}"
    daughters_label = f"{C_DAUGHTER}{'─── Daughters ───':^{HALF_W}}{RESET}"
    print(f"  {mothers_label}  {daughters_label}")

    # Row 1: Mothers I-IV | Daughters V-VIII
    print_row([0, 1, 2, 3, 4, 5, 6, 7], indent=2)

    # Separator
    print()
    nieces_label = f"{C_NIECE}{'─── Nieces ───':^{ROW_W}}{RESET}"
    print(f"  {nieces_label}")

    # Row 2: Nieces IX-XII (centered under the 8-figure row)
    niece_w = 4 * COL_W + 3 * 2   # 70
    print_row([8, 9, 10, 11], indent=2 + (ROW_W - niece_w) // 2)

    # Separator
    print()
    witnesses_label = f"{C_WITNESS}{'─── Witnesses ───':^{ROW_W}}{RESET}"
    print(f"  {witnesses_label}")

    # Row 3: Witnesses XIII-XIV
    wit_w = 2 * COL_W + 1 * 2     # 34
    print_row([12, 13], indent=2 + (ROW_W - wit_w) // 2)

    # Separator
    print()

    # Row 4: Judge
    judge_label = f"{C_JUDGE}{'━━━ Judge ━━━':^{ROW_W}}{RESET}"
    print(f"  {judge_label}")
    print_row([14], indent=2 + (ROW_W - COL_W) // 2)

    # Row 5: Reconciler
    print()
    reconciler_label = f"{C_RECONCILER}{'( Reconciler )':^{ROW_W}}{RESET}"
    print(f"  {reconciler_label}")
    print_row([15], indent=2 + (ROW_W - COL_W) // 2)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Interpretation
# ─────────────────────────────────────────────────────────────────────────────

def print_interpretation(chart):
    """Print interpretive text for the key figures."""
    width = 78

    def interpret(idx, role_name, color):
        bits = chart[idx]
        fig = FIGURES[bits]
        header = f"{fig['name']} — {fig['english']}"

        print(f"{color}{BOLD}┌{'─' * (width - 2)}┐{RESET}")
        print(f"{color}{BOLD}│ {role_name:<{width - 4}} │{RESET}")
        print(f"{color}{BOLD}│ {header:<{width - 4}} │{RESET}")
        details = f"{fig['keyword']} · {fig['planet']} · {fig['element']}"
        print(f"{color}│ {details:<{width - 4}} │{RESET}")
        print(f"{color}├{'─' * (width - 2)}┤{RESET}")

        # Choose meaning text
        if idx == 14:  # Judge
            text = fig["judge_meaning"]
        elif idx == 15:  # Reconciler
            text = fig["meaning"]  # Use general meaning for Reconciler
        else:
            text = fig["meaning"]

        for line in textwrap.wrap(text, width - 4):
            print(f"{color}│ {line:<{width - 4}} │{RESET}")
        print(f"{color}└{'─' * (width - 2)}┘{RESET}")
        print()

    print(f"\n{BOLD}{'═' * width}{RESET}")
    print(f"{BOLD}{'READING':^{width}}{RESET}")
    print(f"{BOLD}{'═' * width}{RESET}\n")

    interpret(14, "THE JUDGE — The Final Answer", C_JUDGE)
    interpret(12, "RIGHT WITNESS — The Root of the Matter", C_WITNESS)
    interpret(13, "LEFT WITNESS — The Direction Ahead", C_WITNESS)
    interpret(15, "THE RECONCILER — Synthesis of Origin and Outcome", C_RECONCILER)

    # Duplicate detection
    from collections import Counter
    figure_counts = Counter(chart[:15])  # Exclude Reconciler from count
    repeats = {bits: count for bits, count in figure_counts.items() if count > 1}
    if repeats:
        print(f"{BOLD}Notable Repetitions:{RESET}")
        for bits, count in sorted(repeats.items(), key=lambda x: -x[1]):
            fig = FIGURES[bits]
            positions = [ROLE_LABELS[i] for i in range(15) if chart[i] == bits]
            print(f"  {fig['name']} appears {count} times "
                  f"(positions: {', '.join(positions)})")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# Query Log
# ─────────────────────────────────────────────────────────────────────────────

LOG_PATH = Path.home() / ".geomancy_log.json"


def log_reading(question, chart):
    """Append the reading to the query log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "chart": [
            {"position": ROLE_LABELS[i], "figure": FIGURES[chart[i]]["name"]}
            for i in range(16)
        ],
        "judge": FIGURES[chart[14]]["name"],
    }

    log = []
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH) as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    log.append(entry)

    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def save_reading(question, chart):
    """Save the current reading as a Markdown file with ANSI color codes."""
    timestamp = datetime.now()
    slug = timestamp.strftime("%Y%m%d_%H%M%S")
    filename = Path.home() / f"geomancy_reading_{slug}.md"

    # Capture chart + interpretation output
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    if question:
        print(f"**Question:** {question}\n")
    print(f"**Cast:** {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
    render_chart(chart)
    print_interpretation(chart)
    sys.stdout = old_stdout

    with open(filename, "w") as f:
        f.write(f"# Geomantic Reading\n\n")
        f.write("```\n")
        f.write(buf.getvalue())
        f.write("```\n")

    return filename


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

HEADER = f"""{BOLD}
  ╔═══════════════════════════════════════════╗
  ║      GEOMANTIC DIVINATION ENGINE          ║
  ║         /dev/urandom Oracle               ║
  ╚═══════════════════════════════════════════╝{RESET}
"""


def main():
    print(HEADER)

    while True:
        print(f"{DIM}Focus on your question. Type it below (or press Enter to proceed silently).{RESET}")
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

        # Display
        render_chart(chart)
        print_interpretation(chart)

        # Log
        log_reading(question if question else "(silent)", chart)
        print(f"{DIM}Reading logged to {LOG_PATH}{RESET}\n")

        # Loop
        print(f"{DIM}Enter → cast again  |  q → quit  |  s → save & cast again  |  sq → save & quit  |  qd → delete log & quit{RESET}")
        try:
            cmd = input(f"{BOLD}> {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Farewell.{RESET}")
            break

        if cmd == "qd":
            if LOG_PATH.exists():
                LOG_PATH.unlink()
                print(f"\n{DIM}Log deleted. No trace remains.{RESET}")
            print(f"{DIM}Farewell.{RESET}")
            break
        elif cmd == "sq":
            f = save_reading(question if question else None, chart)
            print(f"\n{DIM}Reading saved to {f}{RESET}")
            print(f"{DIM}The chart is cast. Go well.{RESET}")
            break
        elif cmd == "s":
            f = save_reading(question if question else None, chart)
            print(f"\n{DIM}Reading saved to {f}{RESET}")
        elif cmd in ("q", "quit", "exit"):
            print(f"\n{DIM}The chart is cast. Go well.{RESET}")
            break

        print("\n" + "─" * 78 + "\n")


if __name__ == "__main__":
    main()
