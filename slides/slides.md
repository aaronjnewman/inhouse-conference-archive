---
marp: true
theme: default
paginate: true
size: 16:9
backgroundColor: "#fbfaf6"
color: "#1a1a1a"
style: |
  @import url('https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,300..900;1,300..900&display=swap');
  section {
    font-family: "Public Sans", "Helvetica Neue", system-ui, sans-serif;
    padding: 50px 70px;
  }
  section.title {
    background: #FFD400;
    color: #000;
    text-align: center;
    justify-content: center;
    font-family: "Public Sans", sans-serif;
  }
  section.title h1 { color: #000; font-size: 3.0em; margin-bottom: .1em; font-weight: 900; letter-spacing: -1px; }
  section.title h1 em { color: #086554; font-style: normal; }
  section.title h2 { color: #000; font-weight: 500; font-size: 1.5em; }
  section.title p  { color: #000; font-weight: 400; font-size: 0.95em; }
  section.title hr { border-color: #000; opacity: 0.4; max-width: 60%; }
  h1 { color: #1a1f3a; border-bottom: 4px solid #FFD400; padding-bottom: 6px; font-weight: 800; }
  h1 em, h1 strong { color: #086554; font-style: normal; }
  h2 { color: #234BA0; font-weight: 700; }
  strong { color: #A72836; }
  blockquote {
    border-left: 6px solid #FFD400;
    padding: 4px 18px;
    color: #333;
    background: #fff8e0;
    font-style: italic;
  }
  code { background: #eee; padding: 2px 5px; border-radius: 3px; font-size: 0.85em; }
  table { font-size: 0.85em; }
  th { background: #234BA0; color: #FFD400; }
  tr:nth-child(even) { background: #f0eee5; }
  .small { font-size: 0.75em; color: #555; }
  .caption { font-size: 0.7em; color: #555; text-align: center; margin-top: 4px; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }
  .quote-card {
    background: #fff;
    border-left: 5px solid #234BA0;
    padding: 10px 16px;
    margin: 8px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    font-size: 0.82em;
  }
  .quote-card .year { color: #A72836; font-weight: 700; margin-right: 8px; }
  .quote-card .authors { display: block; color: #666; font-size: 0.85em; margin-top: 4px; }
---

<!-- _class: title -->
<!-- _backgroundColor: "#FFD400" -->
<!-- _color: "#000" -->
<!-- _paginate: false -->

# 50 Years of In-House

## A computational love-letter to our conference

Aaron J. Newman · 50th Annual Graham Goddard In-House Conference · 2026

---

# Graham Goddard (1938–1987)

![h:520 bg right:42% contain](figures/GrahamGoddard_photo.jpg)

- Dalhousie psychologist + neuroscientist
- Discovered the **kindling model** of epilepsy (Goddard, 1967)
- Built the early Dalhousie animal-learning + neurophysiology group
- Founded what we now call the **In-House Conference**

In 2011, **24 years after his death**, the conference was renamed in his honour.

---

# Where it began — April 1975

![h:580 bg right:54% contain](figures/program_1975.jpg)

The very first In-House: Tuesday April 8 – Wednesday April 9, 1975. **Coffee and donuts at 9:30**, chair: **John Fentress**.

The first ever abstract:
> *C. McNaughton — "Circadian Rhythm in Perforant Path Synaptic Efficacy"*

Note the handwritten *"R. Brown"* in the top corner. **That's the same copy still living on his bookshelf 51 years later.**

---

# Why are we doing this?

After scanning early programs, we have **50 conference programs** sitting in a OneDrive folder.

Half a century of:

- thousands of presentations
- generations of trainees
- decades of departmental memory

…and **zero ability to search any of it.**

> Goal: turn paper, scanned PDFs, and Word documents into a **structured, queryable, archival record** of who did what, and when.

---

# What we want at the end

- A canonical **BibTeX** archive of every presentation, 1975–2026
- A **GitHub repository** with the pipeline + the data
- A **GitHub Pages site** to search, browse, and visualise the corpus
- A long-term deposit in **Dalhousie's Borealis** research-data repository

The corpus then becomes a substrate for:
*authorship networks · topic trends · trainee genealogies · a half-century zeitgeist of the Department*

---

# Acknowledgements

The programs do not exist as a set. They were **rescued** by:

- **Richard Brown** — the principal hoarder-historian, custodian of decades of paper programs
- **Suzanne King** — gap-filling from her own archive
- **Susan Lowerison** — additional gap-filling and document recovery

A genuine **community archaeology** effort. Without their records, none of this exists.

---

# Prior art 

![h:520 bg right:55% contain](figures/klein_graphic.png)

Ray Klein, ~2010 — a hand-drawn plot of **# papers / year** through the first 35 years.

The dotted region pre-1988 was the **paper-only era**; the rest was scraped from emerging electronic programs.

*Today: the same idea, with 16 extra years of data and a "few" more data points.*

---

# The source material is… **a challenge**

| Decade | Format |
|---|---|
| 1975 | typewritten, photocopied, scanned, OCR'd through tears |
| 1976–2001 | scanned PDFs of typewritten or word-processed pages |
| 2002 | original PDF unreadable; only pre-OCR'd `.txt` survives |
| 2003–2013 | `.doc` files (some of which Word itself refuses to open) |
| 2014–2026 | mostly PDF, a stray `.docx` and `.rtf` |

Richard's hand-written notes created further challenge for OCR.
50 years of file formats. Inconsistent formatting.  

The OCR for **1975** alone produced gems like:

> *"Mus l<usicus."* — J. C. Fentress, 1977
> *"f:lart·;n, H.L"* — somebody named Martin, probably

---

# The Challenge for OCR (and a personal favourite)

![h:580 bg right:55% contain](figures/program_1975b.png)

Rodger's **"The Present State of Rodger's Stats"** (1975) — an abstract written almost entirely in **formulae**. 

> *"H<sub>0</sub> : θ<sub>1</sub> = θ<sub>2</sub> = … = θ<sub>j</sub>"*

…was read as *"H'O : 0'1 = 02 = ... = OJ"*.


---

# Method 1 — Extract

`pipeline/01_extract.py`

- **PDFs** → `pdftotext` (with a custom OCR pass for the 1975–1979 rescans done in May 2026)
- **.doc** → `textutil` (macOS)
- **.docx** → unzip + parse XML
- **.rtf / .txt** → as-is, lightly normalised

Output: one `extracted/YYYY.txt` per year. Reproducible from source. **Throw it away and rebuild any time.**

---

# Method 2 — Parse (this is where the AI comes in)

Each year was a **different format**:

> *Talk #5)* vs *T5.* vs *T5:* vs *5. Author Name* vs `Lastname, Firstname` vs *A-3 (this year!)* vs *asterisk-delimited submission forms*…

The 51-year programmatic record has **fifteen distinct parser dialects.**

So we built one parser per format and a year→dialect dispatch table.

The parser was **co-developed iteratively with Claude.ai**:
*human spots a weird entry → Claude proposes a regex / heuristic → human runs it → human spots the next weird entry → repeat.*

---

# Method 3 — Cleanup with a human-in-the-loop

**Four rounds** of review + automated correction passes:

- `04_diagnose.py` — flags suspicious entries (too-long titles, missing authors, OCR garble)
- `05_review.py` — produces a `review_needed.bib` subset to edit by hand
- `06_diff_review.py` — diffs the human-edited bib into machine-readable patches
- `07_split_entries.py` — splits "two-entries-glued-together-by-OCR" records using reviewer breakpoints

**Hand-edits never touch `records.jsonl`.** They live in `corrections.jsonl`, a sidecar of JSON ops that the exporter re-applies on every rebuild.

→ Fully reproducible. Re-run the whole thing in ~30 seconds. (Human time much longer)

---

# The corpus, by the numbers

<div class="two-col">

<div>

- **2,155** presentations
- **50** conferences (1975–2026, no 2020/21)
- **2,117** unique-ish author keys
- **~98%** have an abstract
- **~220** still flagged for review (10%)

</div>

<div>

Cleanest cuts of the data:
- **1976–2018** — parser reliable, abstracts intact
- **2008–2026** — nearly perfect; great for text mining
- **1975, 2019, 2023** — flagged as lower-confidence

</div>

</div>

> Everything that follows comes from prompted-but-automated analysis of this corpus.
> Errors are mine; OCR's; or, occasionally, Claude's.

---

# The conference has had **five names**

| Years | Name |
|---|---|
| **1975** | *Scholarly Convention, Department of Psychology* |
| **1976–2002** | *N-th Annual In-House Convention, Department of Psychology* |
| **2003–2005** | *Annual Psychology and Neuroscience In-House Convention* |
| **2006–2010** | *Annual Psychology and Neuroscience In-House **Conference*** |
| **2011–present** | *Annual **Graham Goddard** In-House Conference* |

The 1983 program proudly announces itself as the *Eighth Annual*. It was, in fact, the **Ninth**. 

---

# Presentations per year

![w:1080](figures/01_presentations_per_year.png)

<p class="caption">Dotted lines mark 2020 and 2021 (no conference, COVID). The conference counter <em>paused</em> rather than skipped — so 2022 is the 46th, not the 47th. 2026 is the 50th.</p>

---

# Hall of Fame — top 25 contributors

![h:560](figures/02_top_authors.png)

---

# Top presenter, each year

![w:1080](figures/03_top_per_year.png)

<p class="caption">Each dot is the person with the most entries that year. Colour = identity (so streaks pop). Bubble size = count.</p>

---

# Streaks

![w:1080](figures/04_streaks.png)

<p class="caption">Each row is a person; dots are years they presented; bar spans first–to–last appearance. Streak = longest run of <em>consecutive</em> conferences. (2020 and 2021 are treated as not-held, so the streak survives the COVID gap.)</p>

---

# Co-authorship network

![w:1180](figures/05_coauthor_network.png)

<p class="caption">Nodes: authors with ≥6 presentations. Edges: co-authored ≥2 times. Layout: force-directed (Fruchterman–Reingold), seeded for reproducibility.</p>

---

# Title extremes — the **shortest**

<div class="quote-card">
<span class="year">1978</span><strong>"Induced Anisocoria"</strong>
<span class="authors">— J. Gardner</span>
</div>

<div class="quote-card">
<span class="year">1980</span><strong>"Dropped Ducks"</strong>
<span class="authors">— L. White & J. Ryon</span>
</div>

<div class="quote-card">
<span class="year">1980</span><strong>"Selective Associations"</strong>
<span class="authors">— K. Shapiro</span>
</div>

<div class="quote-card">
<span class="year">1983</span><strong>"Semantic Priming"</strong>
<span class="authors">— L. Smith & R. Klein</span>
</div>


---

# Title extremes — the **longest**

<div class="quote-card">
<span class="year">1980</span>"Evidence to Support Crow's Reinforcement Hypothesis that Biologically Significant Behavior is Associated with Activity of the Locus Coeruleus and that the Consequent Release of Noradrenaline throughout the Forebrain has the Effect of Strengthening the Efficacy of Recently Active Synapses"
<span class="authors">— G. V. Goddard, T. V. P. Bliss, H. A. Robertson, R. S. Sutherland (40 words)</span>
</div>

<div class="quote-card">
<span class="year">2015</span>"Is there a pharmacological intervention to replace darkness? Preliminary results from a collaborative study (M.I.T) of the use of intraocular injection of tetrodotoxin (TTX) to recover vision in animal models of amblyopia"
<span class="authors">— D. Mitchell, K. Duffy, P. Northrup, M. Fong, M. Bear (34 words)</span>
</div>

<p class="small">Goddard's 1980 title is, somehow, the abstract.</p>

---

# Fun Titles (many more gems in the archive!)

<div class="quote-card">
<span class="year">2005</span><strong>"Doing the Locomotion With the Rat Perifornical Hypothalamus: Who's Excited About Glutamate?"</strong>
<span class="authors">— F. Li, S. Deurveilher, C. Morgan & K. Semba</span>
</div>

<div class="quote-card">
<span class="year">2007</span><strong>"Sex, Drugs, and Abrupt-Onset Distractors: Made You Look!"</strong>
<span class="authors">— N. Saruk, G. Eskes, J. Christie, H. Duncan & R. Klein</span>
</div>

<div class="quote-card">
<span class="year">2007</span><strong>"Stress Responding and Adolescent Development in a Rat Model System: Alley Cats and Hood Rats"</strong>
<span class="authors">— L. Wright, K. Hébert, K. Muir & T. Perrot-Sinal (2008 added: <em>"Alley Cats and Hood Rats, Part II"</em>)</span>
</div>

<div class="quote-card">
<span class="year">2008</span><strong>"Energy Drinks: What Have You Binge Drinking??"</strong>
<span class="authors">— S. Price</span>
</div>

---

# Fun Titles (2)

<div class="quote-card">
<span class="year">2008</span><strong>"Exhibitionist Flasher Uses Wing Mirrors with Fluorescent Fusilli for Sexual Entrapment"</strong>
<span class="authors">— S. Shaw</span>
</div>

<div class="quote-card">
<span class="year">2012</span><strong>"Sex on the Brain: Do Gender and Breeding Condition Affect FoxP2 Expression in Chickadees?"</strong>
<span class="authors">— L. Phillmore, H. MacGillivray, S. Martin & R. Wilson</span>
</div>

<div class="quote-card">
<span class="year">2012</span><strong>"What Are We Really Measuring in Tests of Anxiety in Mice?"</strong>
<span class="authors">— R. E. Brown, R. K. Gunn & T. P. O'Leary (an entire literature distilled to nine words)</span>
</div>

<div class="quote-card">
<span class="year">1977</span><strong>"Mus Musicus."</strong>
<span class="authors">— J. C. Fentress. The whole thing is an extended joke about whether motor patterns have notes, rests, and melodies. Magnificent.</span>
</div>

---

# Departmental milestones, captured

The corpus quietly preserves the Department's own reflections on itself:

<div class="quote-card">
<span class="year">1984</span><strong>"Psychology's In-House Convention: 10 years old and going strong"</strong>
<span class="authors">— R. Klein (the first retrospective, at the 10-year mark)</span>
</div>

<div class="quote-card">
<span class="year">1997</span><strong>"The Hebb-Williams Maze: Fifty Years of Research (1946–1996)"</strong>
<span class="authors">— R. Brown & L. Stanford</span>
</div>

<div class="quote-card">
<span class="year">1998</span><strong>Symposium: "To Hebb and Beyond"</strong>
<span class="authors">— a whole session devoted to the Department's intellectual lineage</span>
</div>

<div class="quote-card">
<span class="year">2006</span><strong>"The History of Psychology at Dalhousie"</strong>
<span class="authors">— L. Boutilier, D. Clark, J. Longard et al.</span>
</div>

---

# Departmental milestones, captured (2)

<div class="quote-card">
<span class="year">2006</span><strong>"We've Come a Long Way in 35 Years"</strong>
<span class="authors">— R. Hoffman</span>
</div>

<div class="quote-card">
<span class="year">2007</span><strong>"Preserving Our History with Digital Video: The Snapshot Project"</strong>
<span class="authors">— R. Hoffman & H. Schellinck</span>
</div>

<div class="quote-card">
<span class="year">2013</span><strong>"A Neo-Hebbian Blueprint for the Integration of Neuro-Psychological Science"</strong>
<span class="authors">— R. M. Klein</span>
</div>

<div class="quote-card">
<span class="year">2023</span><strong>"Revising the Hebb Synapse for the 21st Century"</strong>
<span class="authors">— R. E. Brown</span>
</div>

<div class="quote-card">
<span class="year">2025</span><strong>"50 Years in Psychology (and Neuroscience) at Dalhousie"</strong>
<span class="authors">— R. Klein (the immediate predecessor of *this* talk)</span>
</div>

---

<!-- _class: hebb -->
<style scoped>
section.hebb ul { font-size: 0.85em; margin-top: 0.2em; }
section.hebb p { font-size: 0.85em; margin: 0.3em 0; }
</style>

# The Internet, captured in real time

<style scoped>
section .quote-card { font-size: 0.74em; }
section .quote-card blockquote { margin: 4px 0; padding: 2px 12px; font-size: 0.95em; }
</style>

<div class="quote-card">
<span class="year">1994</span><strong>"Lab, Library, LAN, and (L')Internet"</strong> — R. Hoffman
<blockquote>"This past year has seen the arrival of some exciting new technologies for information access… students can check Novanet for availability of journals, and even order a fax copy of an article <em>over the Internet</em>."</blockquote>
</div>

<div class="quote-card">
<span class="year">1995</span><strong>"Caught in the Web: Psychology on the Internet in 1995"</strong> — R. Hoffman
<blockquote>"Today it is possible to tour the Louvre Museum, book a hotel room in San Francisco, or order fresh Nova Scotia lobsters delivered anywhere in North America, all from your computer workstation. <strong>Tomorrow even more will be possible.</strong> …I will demonstrate a Web site (Home Page) for the Dalhousie Psychology Department."</blockquote>
</div>

<div class="quote-card">
<span class="year">1997</span><strong>"Footprints on the Internet: What Do They Tell Us?"</strong> — R. Hoffman
<blockquote>"The Psychology Department home page officially went on the World-Wide Web on <strong>November 29th, 1996.</strong>"</blockquote>
</div>

---

# Donald O. Hebb — the long shadow

![h:440 bg right:40% contain](figures/Hebb.jpg)

**Donald O. Hebb (1904–1985)** — *The Organization of Behavior* (1949), the "Hebb synapse".

His name is woven through the corpus:

- **80** occurrences of *Hebb* / *Hebbian*
- **27** distinct presentations cite him by name
- Spanning **1985 → 2026**

**Authors who invoke Hebb most:**
R. Brown (13) · L. Stanford (6) · H. Schellinck (4) · R. Darrah (3) · E. Fertan (3) · R. Klein (2) · D. Kelly (2)

---

# What's next

- **GitHub repo** (`inhouse-conference-archive`): pipeline, data, corrections, this talk
- **GitHub Pages**: searchable web UI + interactive visualisations (co-authorship network you can pan around, year-by-year browser, full-text search)
- **Dalhousie Borealis** deposit: permanent, citable DOI for the dataset
- **Further cleanup**: the ~220 flagged entries, author canonicalisation, affiliation extraction
- **Linkage**: PubMed/Scholar lookup to find the *published* versions of these presentations

If you presented something between 1975 and 2026 and you find your name garbled, **come find me afterwards.**

---

<!-- _class: title closing -->
<!-- _backgroundColor: "#FFD400" -->
<!-- _color: "#000" -->
<!-- _paginate: false -->

<style scoped>
section.closing { justify-content: flex-start; padding-top: 40px; }
section.closing h1 { font-size: 2.6em; margin-bottom: 0; }
section.closing h2 { font-size: 1.25em; margin: 0.15em 0; font-weight: 500; }
section.closing p { margin-top: 0.5em; }
section.closing .qr { margin-top: 18px; display: flex; flex-direction: column; align-items: center; }
section.closing .qr img { width: 200px; height: 200px; background: #fff; padding: 6px; border: 2px solid #000; }
section.closing .qr .cap { font-size: 0.75em; margin-top: 6px; }
</style>

# Thank you

## Richard Brown · Suzanne King · Susan Lowerison
## …and 50 years of presenters

aaron.newman@dal.ca · github.com/aaronjnewman/inhouse-conference-archive

<div class="qr">

![w:200](figures/qr_github.png)

<span class="cap">github.com/aaronjnewman/inhouse-conference-archive</span>

</div>
