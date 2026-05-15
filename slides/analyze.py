"""
Build figures + summary statistics for the 50th-anniversary talk.

Reads ../inhouse_conference.bib (canonical output of the pipeline).
Writes:
    slides/figures/*.png
    slides/stats.json   (numbers + lists that the slides reference)
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib as mpl
import networkx as nx
import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parent
BIB = ROOT / "inhouse_conference.bib"
FIGS = HERE / "figures"
FIGS.mkdir(parents=True, exist_ok=True)

# A clean, friendly look for the figures.
mpl.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#444",
    "axes.labelcolor": "#222",
    "axes.titlesize": 18,
    "axes.titleweight": "bold",
    "axes.titlecolor": "#222",
    "xtick.color": "#444",
    "ytick.color": "#444",
    "font.family": "DejaVu Sans",
    "font.size": 12,
})

DAL_GOLD = "#FFD400"
DAL_BLACK = "#000000"
ACCENT = "#234BA0"   # deep blue
ACCENT2 = "#A72836"  # muted brick
GRID = "#DDDDDD"

# ---------------------------------------------------------------------------
# Bib parsing
# ---------------------------------------------------------------------------

ENTRY_RE = re.compile(r"@\w+\s*\{([^,]+),\s*(.*?)\n\}", re.DOTALL)
FIELD_RE = re.compile(r"\b(\w+)\s*=\s*\{([^{}]*)\}\s*,?", re.DOTALL)


def load_bib():
    text = BIB.read_text(encoding="utf-8", errors="replace")
    records = []
    for m in ENTRY_RE.finditer(text):
        key = m.group(1).strip()
        body = m.group(2)
        fields = {fm.group(1).lower(): fm.group(2).strip() for fm in FIELD_RE.finditer(body)}
        if "year" not in fields:
            continue
        try:
            fields["year"] = int(fields["year"])
        except ValueError:
            continue
        fields["_key"] = key
        records.append(fields)
    return records


def split_authors(author_field: str) -> list[str]:
    if not author_field:
        return []
    parts = [a.strip() for a in re.split(r"\s+and\s+", author_field)]
    return [p for p in parts if p]


# Heuristic surname normalisation that tolerates OCR garble and missing/extra
# initials.  We collapse "McNaughton, B" / "McNaughton, Bruce" / "MCNAUGHTON, B"
# down to a single key.
PUNCT_RE = re.compile(r"[^\w\s]")
SPACE_RE = re.compile(r"\s+")


def normalise_author(raw: str) -> tuple[str, str]:
    """Return (display_name, normalised_key)."""
    s = unicodedata.normalize("NFKD", raw)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.strip().strip(".,;:")
    # When the source field accidentally fused several authors into one
    # comma-form ("Stewart, Simon B. Sherry; Aislin R. Mushquash; ..."),
    # keep only the first author for display + key purposes.
    if ";" in s:
        s = s.split(";", 1)[0].strip()
    # Comma form: "Lastname, F.J."  Take only the first first-name token so a
    # truncated paste of subsequent authors doesn't pollute the display name.
    if "," in s:
        last, _, first = s.partition(",")
        last = last.strip()
        first = first.strip().split()[0] if first.strip() else ""
        # Some 2017 entries came out as "INITIALS, Lastname" (e.g. "NO, Rosen"
        # for Natalie O. Rosen).  Detect: before-comma is short and ALL-CAPS,
        # after-comma looks like a real word.  Then flip.
        if (1 <= len(last) <= 3 and last.isalpha() and last.isupper()
                and len(first) >= 3 and first[:1].isupper() and not first.isupper()):
            last, first = first, last
    else:
        toks = s.split()
        if not toks:
            return raw, ""
        last = toks[-1]
        first = toks[0] if len(toks) > 1 else ""
    last_key = PUNCT_RE.sub("", last).lower()
    last_key = SPACE_RE.sub(" ", last_key).strip()
    first_clean = PUNCT_RE.sub(" ", first).strip()
    initial = first_clean[:1].lower() if first_clean else ""
    if last_key and initial:
        key = f"{last_key}|{initial}"
    else:
        key = last_key
    if first.strip():
        display = f"{last.strip()}, {first.strip().rstrip('.')}"
    else:
        display = last.strip()
    return display, key


GARBLE_RE = re.compile(r"[^A-Za-z\s,\.\-']")


def is_clean_surname(raw: str) -> bool:
    """Drop OCR garble (mainly 1975) — strict purity test."""
    if not raw:
        return False
    last = raw.split(",", 1)[0]
    if len(last) < 2 or len(last) > 25:
        return False
    if GARBLE_RE.search(last):
        return False
    # Must contain at least one vowel-ish letter, otherwise probably noise.
    if not re.search(r"[aeiouyAEIOUY]", last):
        return False
    return True


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def main():
    records = load_bib()

    by_year: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        by_year[r["year"]].append(r)

    years_sorted = sorted(by_year)

    # === 1. Presentations per year line chart ============================
    counts = [(y, len(by_year[y])) for y in years_sorted]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    xs = [y for y, _ in counts]
    ys = [c for _, c in counts]
    ax.plot(xs, ys, color=ACCENT, lw=2.2, marker="o", ms=6,
            markerfacecolor=DAL_GOLD, markeredgecolor=ACCENT)
    # COVID gap
    for missing in (2020, 2021):
        ax.axvline(missing, color=ACCENT2, ls=":", lw=1, alpha=0.6)
    ax.text(2020.5, max(ys) * 0.92, "COVID\n(no conference)",
            ha="center", va="top", fontsize=10, color=ACCENT2)
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of presentations")
    ax.set_title("50 years of In-House Conference presentations")
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_ylim(0, max(ys) * 1.1)
    fig.tight_layout()
    fig.savefig(FIGS / "01_presentations_per_year.png", dpi=160)
    plt.close(fig)

    # === Author tallies ===================================================
    # author_key -> {"display": str, "count": int, "years": set[int]}
    author_info: dict[str, dict] = {}
    # per-year, top presenter
    per_year_authors: dict[int, Counter] = defaultdict(Counter)
    # for co-authorship: list of {year, authors:set[key]} per record
    record_authors: list[tuple[int, list[tuple[str, str]]]] = []

    for r in records:
        year = r["year"]
        authors = split_authors(r.get("author", ""))
        keyed = []
        for a in authors:
            if not is_clean_surname(a):
                continue
            disp, key = normalise_author(a)
            if not key:
                continue
            keyed.append((disp, key))
            per_year_authors[year][key] += 1
            info = author_info.setdefault(key, {"display": disp, "count": 0, "years": set()})
            info["count"] += 1
            info["years"].add(year)
            # Prefer the shortest sane display so that pasted-in author dumps
            # don't pollute the label.
            if 0 < len(disp) < len(info["display"]) or not info["display"]:
                info["display"] = disp
        record_authors.append((year, keyed))

    # === 2. Top-N author histogram ========================================
    TOP_N = 25
    top_authors = sorted(author_info.values(), key=lambda d: d["count"], reverse=True)[:TOP_N]
    fig, ax = plt.subplots(figsize=(10, 8))
    names = [d["display"] for d in top_authors][::-1]
    counts_ = [d["count"] for d in top_authors][::-1]
    bars = ax.barh(names, counts_, color=ACCENT, edgecolor="white")
    # Highlight the top 5 (last 5 in the reversed list)
    for b in bars[-5:]:
        b.set_color(DAL_GOLD)
        b.set_edgecolor(DAL_BLACK)
        b.set_linewidth(0.8)
    for b, c in zip(bars, counts_):
        ax.text(c + 0.5, b.get_y() + b.get_height() / 2, str(c),
                va="center", fontsize=10, color="#333")
    ax.set_xlabel("Total presentations (1975–2025)")
    ax.set_title(f"Hall of Fame — top {TOP_N} contributors")
    ax.grid(axis="x", color=GRID, lw=0.7)
    fig.tight_layout()
    fig.savefig(FIGS / "02_top_authors.png", dpi=160)
    plt.close(fig)

    # === 3. Biggest presenter each year (heatmap-ish dot plot) ============
    yearly_top = []
    for y in years_sorted:
        c = per_year_authors[y]
        if not c:
            continue
        top_key, top_n = c.most_common(1)[0]
        yearly_top.append((y, author_info[top_key]["display"], top_n))

    # Use the same person -> the same colour so streaks pop visually.
    unique_people = list({name for _, name, _ in yearly_top})
    colour_map = {name: plt.cm.tab20(i / max(1, len(unique_people))) for i, name in enumerate(unique_people)}

    fig, ax = plt.subplots(figsize=(12, 6.0))
    for (y, name, n) in yearly_top:
        ax.scatter(y, n, s=80 + 18 * n, color=colour_map[name],
                   edgecolor="#222", lw=0.6, zorder=3)
        ax.text(y, n + 0.25, name.split(",")[0], rotation=90, ha="center",
                va="bottom", fontsize=8, color="#333")
    ax.set_xlabel("Year")
    ax.set_ylabel("Presentations that year")
    ax.set_title("Top contributor each year")
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_ylim(0, max(n for _, _, n in yearly_top) + 4)
    fig.tight_layout()
    fig.savefig(FIGS / "03_top_per_year.png", dpi=160)
    plt.close(fig)

    # === 4. Streaks — longest run of consecutive conferences ==============
    # The conference did not run in 2020 or 2021; treat 2019→2022 as consecutive.
    held = [y for y in years_sorted]  # already excludes 2020/2021 in source
    held_set = set(held)
    sorted_held = sorted(held_set)

    def consecutive_streak(years_present: set[int]) -> int:
        if not years_present:
            return 0
        best = cur = 0
        for y in sorted_held:
            if y in years_present:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    streaks = []
    for key, info in author_info.items():
        s = consecutive_streak(info["years"])
        if s >= 5:
            streaks.append((info["display"], s, sorted(info["years"])))
    streaks.sort(key=lambda t: t[1], reverse=True)
    top_streaks = streaks[:12]

    fig, ax = plt.subplots(figsize=(11, 4.6))
    for i, (name, s, yrs) in enumerate(top_streaks[::-1]):
        ax.barh(name, max(yrs) - min(yrs) + 1, left=min(yrs),
                color="#DDDDDD", edgecolor="none", height=0.55)
        ax.scatter(yrs, [name] * len(yrs), color=ACCENT, s=22, zorder=3)
        ax.text(max(yrs) + 0.4, name, f"streak: {s}", va="center", fontsize=9, color=ACCENT2)
    ax.tick_params(axis="y", labelsize=9)
    ax.set_xlim(1974, 2028)
    ax.set_xlabel("Year")
    ax.set_title("Longest consecutive-attendance streaks")
    ax.grid(axis="x", color=GRID, lw=0.7)
    fig.tight_layout()
    fig.savefig(FIGS / "04_streaks.png", dpi=160)
    plt.close(fig)

    # === 5. Co-authorship network =========================================
    # Edge threshold chosen so the graph is readable but not sparse.
    edge_counts: Counter = Counter()
    for year, keyed in record_authors:
        unique = list({k: d for d, k in keyed}.items())  # key -> display
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                a, b = sorted([unique[i][0], unique[j][0]])
                edge_counts[(a, b)] += 1

    NODE_MIN_PRES = 6   # author must have at least this many presentations
    EDGE_MIN = 2        # at least this many co-authored presentations

    keep_authors = {k for k, info in author_info.items() if info["count"] >= NODE_MIN_PRES}
    G = nx.Graph()
    for k in keep_authors:
        G.add_node(k, label=author_info[k]["display"], count=author_info[k]["count"])
    for (a, b), w in edge_counts.items():
        if w >= EDGE_MIN and a in keep_authors and b in keep_authors:
            G.add_edge(a, b, weight=w)

    # Drop isolates so the picture is about collaboration.
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])

    if G.number_of_nodes() > 0:
        # Keep only the largest connected component so the picture isn't
        # dominated by tiny isolated pairs.
        components = sorted(nx.connected_components(G), key=len, reverse=True)
        H = G.subgraph(components[0]).copy()

        # Render extra-large so a 16:9 slide can use almost the full canvas.
        fig, ax = plt.subplots(figsize=(22, 13))
        pos = nx.spring_layout(H, k=3.2, iterations=600, seed=42, weight="weight")
        node_sizes = [350 + 65 * H.nodes[n]["count"] for n in H.nodes]
        nx.draw_networkx_edges(H, pos, ax=ax,
                               width=[0.7 + 0.7 * H[u][v]["weight"] for u, v in H.edges],
                               edge_color="#9BA7C2", alpha=0.7)
        nx.draw_networkx_nodes(H, pos, ax=ax, node_size=node_sizes,
                               node_color=DAL_GOLD, edgecolors=DAL_BLACK, linewidths=1.0)
        # Label every node — surname only.  Bigger font for the hubs.
        for n in H.nodes:
            x, y = pos[n]
            name = author_info[n]["display"].split(",")[0]
            count = H.nodes[n]["count"]
            size = 14 if count >= 20 else (12 if count >= 9 else 9)
            weight = "bold" if count >= 9 else "normal"
            ax.text(x, y, name, fontsize=size, fontweight=weight,
                    ha="center", va="center", color="#111")
        # Add a little padding so labels at the edge aren't clipped.
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        ax.set_xlim(min(xs) - 0.18, max(xs) + 0.18)
        ax.set_ylim(min(ys) - 0.12, max(ys) + 0.12)
        ax.set_axis_off()
        ax.set_title(
            f"Co-authorship network — main connected component "
            f"({H.number_of_nodes()} authors, ≥{NODE_MIN_PRES} presentations, edges ≥{EDGE_MIN} co-authorships)",
            fontsize=20,
        )
        fig.tight_layout()
        fig.savefig(FIGS / "05_coauthor_network.png", dpi=140)
        plt.close(fig)

    # === 6. Title-length stats ===========================================
    def word_count(s: str) -> int:
        return len(re.findall(r"\b\w+\b", s or ""))

    titled = [r for r in records if r.get("title")]

    def title_clean(t: str) -> bool:
        letters = sum(c.isalpha() for c in t)
        return letters > 0 and (sum(c.isalpha() or c.isspace() for c in t) / len(t) > 0.7)

    clean_titled = [r for r in titled if title_clean(r["title"])]
    # Cap word count at 40 — anything beyond that is almost always a parser
    # concatenation rather than a genuine title (the worst offender was 276
    # words long, the next 80+).  Real long titles in the program top out
    # around the high 20s.
    plausible = [r for r in clean_titled if word_count(r["title"]) <= 40]
    by_len = sorted(plausible, key=lambda r: word_count(r["title"]))
    # Filter out two-word stubs that are clearly truncated abstract fragments
    # (e.g. "Effects of") — require at least one capital-content word.
    shortest = []
    for r in by_len:
        t = r["title"].strip()
        if word_count(t) < 2:
            continue
        if word_count(t) > 5:
            break
        shortest.append(r)
        if len(shortest) >= 5:
            break
    longest = by_len[-5:][::-1]

    # === 7. "Amusing" titles (curated regex over the cleaned set) =========
    AMUSING_PATTERNS = [
        r"\b(rat|rats|mouse|mice|hamster|gerbil|pigeon|cat|cats|kitten|goldfish|chick|squirrel|monkey)\b",
        r"\b(beer|wine|chocolate|cookie|cookies|coffee|alcohol|drinking|drunk)\b",
        r"\b(sex|sexual|erotic|orgasm|porn|love|kiss(ing)?|flirt)\b",
        r"\b(zombie|brain[- ]?eating|cannibal|cannibalism|ghost|haunt(ed|ing)?)\b",
        r"\b(toilet|defecation|poo|urinat|fart|burp|vomit|nausea)\b",
        r"\b(memory of memory|memory for memories|meta-meta|recursion|the the)\b",
        r"\bbut why\b|\bplease\b|\bsorry\b|\boops\b|\bwhoops\b",
        r"\?{2,}|!{2,}",
        r"^\s*[Ww]hy\b",
        r"\b(self-?stimulation|kindling|brain stimulation)\b",
    ]
    AMUSING_RE = re.compile("|".join(AMUSING_PATTERNS), re.IGNORECASE)
    amusing_pool = [r for r in clean_titled
                    if AMUSING_RE.search(r["title"])
                    and 4 <= word_count(r["title"]) <= 25]
    # Deduplicate near-identical titles.
    seen = set()
    amusing = []
    for r in amusing_pool:
        sig = re.sub(r"\W+", "", r["title"]).lower()
        if sig in seen:
            continue
        seen.add(sig)
        amusing.append(r)
    amusing.sort(key=lambda r: r["year"])

    # === 8. Conference-name eras ==========================================
    # Pulled from booktitles.py:
    name_eras = [
        ("1975", "Scholarly Convention"),
        ("1976–2002", "Annual In-House Convention"),
        ("2003–2005", "Annual Psychology & Neuroscience In-House Convention"),
        ("2006–2010", "Annual Psychology & Neuroscience In-House Conference"),
        ("2011–present", "Graham Goddard In-House Conference"),
    ]

    # === Bonus: word-of-the-year over time ================================
    # For every year find the most over-represented content word in titles.
    STOPWORDS = set("""
        a an the and or of in on for with to by from is are was were be been
        being it its as at this that these those into onto under over between
        among within across throughout via vs without we i you he she they
        their our its his her them us him me effect effects role roles
        study studies new not no does do role using used use can may might
        could would should also may have has had which what whose whom whoever
        whose whoever whichever including including not none one two three
        four five six seven eight nine ten preliminary report towards toward
    """.split())

    def normalise_title_words(t: str) -> list[str]:
        return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]+", t)
                if w.lower() not in STOPWORDS and len(w) >= 4]

    global_freq = Counter()
    for r in clean_titled:
        for w in normalise_title_words(r["title"]):
            global_freq[w] += 1

    yearly_word: dict[int, tuple[str, int]] = {}
    for y in years_sorted:
        local = Counter()
        for r in by_year[y]:
            if not title_clean(r.get("title", "")):
                continue
            for w in normalise_title_words(r["title"]):
                local[w] += 1
        if not local:
            continue
        # tf-idf-ish score: local-count / sqrt(global-count) — bumps year-specific words.
        scored = []
        for w, n in local.items():
            if n < 2:
                continue
            score = n / (global_freq[w] ** 0.5)
            scored.append((score, w, n))
        if scored:
            scored.sort(reverse=True)
            yearly_word[y] = (scored[0][1], scored[0][2])

    # === Save stats =======================================================
    def trim_title(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip().rstrip(".")

    stats = {
        "total_records": len(records),
        "years_covered": f"{min(years_sorted)}–{max(years_sorted)} (no 2020/2021)",
        "unique_authors": len(author_info),
        "top_authors": [
            {"name": d["display"], "count": d["count"], "years_span":
             [min(d["years"]), max(d["years"])]}
            for d in top_authors[:10]
        ],
        "yearly_top": [
            {"year": y, "name": name, "count": n} for (y, name, n) in yearly_top
        ],
        "top_streaks": [
            {"name": n, "streak": s, "first": min(yrs), "last": max(yrs)}
            for (n, s, yrs) in top_streaks
        ],
        "shortest_titles": [
            {"year": r["year"], "title": trim_title(r["title"]),
             "authors": r.get("author", ""), "words": word_count(r["title"])}
            for r in shortest
        ],
        "longest_titles": [
            {"year": r["year"], "title": trim_title(r["title"]),
             "authors": r.get("author", ""), "words": word_count(r["title"])}
            for r in longest
        ],
        "amusing_titles": [
            {"year": r["year"], "title": trim_title(r["title"]),
             "authors": r.get("author", "")}
            for r in amusing
        ],
        "name_eras": name_eras,
        "network": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "node_threshold": NODE_MIN_PRES,
            "edge_threshold": EDGE_MIN,
        },
        "yearly_word": [
            {"year": y, "word": w, "count": n}
            for y, (w, n) in sorted(yearly_word.items())
        ],
    }
    (HERE / "stats.json").write_text(json.dumps(stats, indent=2))

    print(f"Wrote {len(records)} records analysed.")
    print(f"Authors: {len(author_info)}; Network: {G.number_of_nodes()} nodes / {G.number_of_edges()} edges.")
    print(f"Streaks ≥5: {len(streaks)}; top streak: {top_streaks[0] if top_streaks else None}")
    print(f"Shortest title words: {word_count(shortest[0]['title'])}")
    print(f"Longest title words: {word_count(longest[0]['title'])}")
    print(f"Amusing pool: {len(amusing_pool)}; final: {len(amusing)}")


if __name__ == "__main__":
    main()
