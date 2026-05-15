"""
Per-year booktitle lookup for the Dalhousie In-House Conference BibTeX pipeline.
Titles are taken from the title page of each program.  Where OCR quality makes
the title page unreadable the title is inferred from the ordinal sequence and
surrounding years.  All inferred entries are flagged.
"""

from __future__ import annotations

# Ordinal words for the older "Nth Annual" naming era
_ORDINALS = {
    1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth",
    6: "Sixth", 7: "Seventh", 8: "Eighth", 9: "Ninth", 10: "Tenth",
    11: "Eleventh", 12: "Twelfth", 13: "Thirteenth", 14: "Fourteenth",
    15: "Fifteenth", 16: "Sixteenth", 17: "Seventeenth", 18: "Eighteenth",
    19: "Nineteenth", 20: "Twentieth", 21: "Twenty-First",
    22: "Twenty-Second", 23: "Twenty-Third", 24: "Twenty-Fourth",
    25: "Twenty-Fifth", 26: "Twenty-Sixth", 27: "Twenty-Seventh",
    28: "Twenty-Eighth", 29: "Twenty-Ninth",
}

def _ordinal(n: int) -> str:
    if n in _ORDINALS:
        return _ORDINALS[n]
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
    return f"{n}{suffix}"

# Years missing (conference not held)
MISSING_YEARS = {2020, 2021}

# Conference number = year - 1974  (first was 1975 = 1st)
# 2020 and 2021 not held, so:
# 2022 = 46th  (counter paused during COVID, did not skip)
def conference_number(year: int) -> int:
    """Return the ordinal number of the conference for a given year."""
    n = year - 1974
    for my in sorted(MISSING_YEARS):
        if year > my:
            n -= 1
    return n

# Hard-coded titles keyed by year.
# Source column: "verified" = read directly from text; "inferred" = computed.
BOOKTITLES: dict[int, tuple[str, str]] = {
    # year: (title, source)
    1975: (
        "Scholarly Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1976: (
        "Second Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1977: (
        "Third Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1978: (
        "Fourth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1979: (
        "Fifth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1980: (
        "Sixth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1981: (
        "Seventh Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1982: (
        "Eighth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1983: (
        # Program itself prints "Eighth Annual" but ordinal from year sequence is Ninth
        # (1976=Second, 1982=Eighth). Treating as program-typo; using corrected ordinal.
        "Ninth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "inferred",
    ),
    1984: (
        "Tenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1985: (
        "Eleventh Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1986: (
        "Twelfth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1987: (
        "Thirteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1988: (
        "Fourteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1989: (
        "Fifteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1990: (
        "Sixteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1991: (
        "Seventeenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1992: (
        "Eighteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1993: (
        "Nineteenth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1994: (
        "Twentieth Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1995: (
        "Twenty-First Annual In-House Convention, Department of Psychology, Dalhousie University",
        "inferred",  # title page not legible in OCR output
    ),
    1996: (
        "22nd Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1997: (
        "23rd Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1998: (
        "24th Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    1999: (
        "25th Annual In-House Convention, Department of Psychology, Dalhousie University",
        "inferred",  # schedule appears on page 1, no title page in OCR
    ),
    2000: (
        "26th Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    2001: (
        "27th Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    2002: (
        "28th Annual In-House Convention, Department of Psychology, Dalhousie University",
        "verified",
    ),
    2003: (
        "29th Annual Psychology and Neuroscience In-House Convention, Dalhousie University",
        "verified",
    ),
    2004: (
        "30th Annual Psychology and Neuroscience In-House Convention, Dalhousie University",
        "verified",
    ),
    2005: (
        "31st Annual Psychology and Neuroscience In-House Convention, Dalhousie University",
        "verified",  # program prints "31th" but ordinal is 31st
    ),
    2006: (
        "32nd Annual Psychology and Neuroscience In-House Conference, Dalhousie University",
        "verified",
    ),
    2007: (
        "33rd Annual Psychology and Neuroscience In-House Conference, Dalhousie University",
        "verified",
    ),
    2008: (
        "34th Annual Psychology and Neuroscience In-House Conference, Dalhousie University",
        "verified",
    ),
    2009: (
        "35th Annual Psychology and Neuroscience In-House Convention, Dalhousie University",
        "verified",
    ),
    2010: (
        "36th Annual Psychology and Neuroscience In-House Convention, Dalhousie University",
        "verified",
    ),
    2011: (
        "Psychology and Neuroscience 37th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2012: (
        "Psychology and Neuroscience 38th Annual Graham Goddard In-House Conference, Dalhousie University",
        "inferred",  # no title page in PDF
    ),
    2013: (
        "Psychology and Neuroscience 39th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2014: (
        "Psychology and Neuroscience 40th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2015: (
        "Psychology and Neuroscience 41st Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2016: (
        "Psychology and Neuroscience 42nd Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2017: (
        "Psychology and Neuroscience 43rd Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2018: (
        "Psychology and Neuroscience 44th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2019: (
        "Psychology and Neuroscience 45th Annual Graham Goddard In-House Conference, Dalhousie University",
        "inferred",  # docx title page not clearly readable
    ),
    2022: (
        "Psychology and Neuroscience 46th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2023: (
        "Psychology and Neuroscience 47th Annual Graham Goddard In-House Conference, Dalhousie University",
        "inferred",  # tentative schedule only
    ),
    2024: (
        "Psychology and Neuroscience 48th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2025: (
        "Psychology and Neuroscience 49th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
    2026: (
        "Psychology and Neuroscience 50th Annual Graham Goddard In-House Conference, Dalhousie University",
        "verified",
    ),
}


def get_booktitle(year: int) -> tuple[str, str]:
    """Return (booktitle, source) for the given year."""
    if year in BOOKTITLES:
        return BOOKTITLES[year]
    raise KeyError(f"No booktitle configured for year {year}")
