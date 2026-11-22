"""Country names -> ISO 3166 alpha-2 codes, in code (the tools compare codes: CU, RU, MX, CL...).

The 8B model often writes "Italy" or "Cuban" where the schema asks for "IT" or "CU". Left as is,
a Cuban cigar written "Cuba" would miss the ban and a Mexican tequila would miss the USMCA rate, so
intake output is normalised here before any tool runs (docs/COMPENSATIONS.md).
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# Names pycountry does not resolve exactly: UK nations, demonyms, short and old names.
ALIASES = {
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "northern ireland": "GB",
    "british": "GB",
    "english": "GB",
    "scottish": "GB",
    "welsh": "GB",
    "usa": "US",
    "u.s.": "US",
    "us": "US",
    "united states": "US",
    "america": "US",
    "american": "US",
    "russia": "RU",
    "russian": "RU",
    "cuban": "CU",
    "havana": "CU",
    "habanos": "CU",
    "habano": "CU",
    "mexican": "MX",
    "canadian": "CA",
    "italian": "IT",
    "french": "FR",
    "spanish": "ES",
    "portuguese": "PT",
    "german": "DE",
    "irish": "IE",
    "polish": "PL",
    "dutch": "NL",
    "holland": "NL",
    "the netherlands": "NL",
    "belgian": "BE",
    "swiss": "CH",
    "austrian": "AT",
    "greek": "GR",
    "turkey": "TR",
    "turkish": "TR",
    "japanese": "JP",
    "chinese": "CN",
    "korean": "KR",
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "indian": "IN",
    "thai": "TH",
    "vietnam": "VN",
    "vietnamese": "VN",
    "chilean": "CL",
    "argentinian": "AR",
    "argentine": "AR",
    "peruvian": "PE",
    "colombian": "CO",
    "brazilian": "BR",
    "jamaican": "JM",
    "barbadian": "BB",
    "bajan": "BB",
    "trinidad": "TT",
    "trinidadian": "TT",
    "tobago": "TT",
    "bahamian": "BS",
    "the bahamas": "BS",
    "bahamas": "BS",
    "dominican republic": "DO",
    "dominican": "DO",
    "haitian": "HT",
    "south african": "ZA",
    "australian": "AU",
    "new zealand": "NZ",
    "kiwi": "NZ",
    "israeli": "IL",
    "moroccan": "MA",
    "czech": "CZ",
    "czech republic": "CZ",
    "slovak": "SK",
    "hungarian": "HU",
    "swedish": "SE",
    "norwegian": "NO",
    "danish": "DK",
    "finnish": "FI",
    "ivory coast": "CI",
    "british virgin islands": "VG",
    "bvi": "VG",
    "tortola": "VG",
    "us virgin islands": "VI",
    "st lucia": "LC",
    "saint lucia": "LC",
    "st kitts": "KN",
    "st vincent": "VC",
    "antigua": "AG",
    "curacao": "CW",
    "aruba": "AW",
    "macedonia": "MK",
    "laos": "LA",
    "taiwan": "TW",
    "taiwanese": "TW",
    "iran": "IR",
    "syria": "SY",
    "venezuela": "VE",
    "bolivia": "BO",
    "tanzania": "TZ",
    "moldova": "MD",
    "scotch": "GB",
}
NOT_A_COUNTRY = {
    "duty-free",
    "duty free",
    "dutyfree",
    "cruise ship",
    "ship",
    "airport",
    "unknown",
    "eu",
    "europe",
    "caribbean",
}


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.strip().lower().replace("st.", "st"))


@lru_cache(maxsize=512)
def to_iso2(value: str | None) -> str | None:
    """ISO alpha-2 for a country code, name or demonym; None if it is not a recognisable country."""
    if not value:
        return None
    raw = value.strip()
    if re.fullmatch(r"[A-Za-z]{2}", raw):
        code = raw.upper()
        code = "GB" if code == "UK" else code
        try:
            import pycountry

            return code if pycountry.countries.get(alpha_2=code) else None
        except ImportError:  # pragma: no cover
            return code
    key = _plain(raw)
    if key in NOT_A_COUNTRY:
        return None
    if key in ALIASES:
        return ALIASES[key]
    try:
        import pycountry
    except ImportError:  # pragma: no cover
        return None
    try:
        return pycountry.countries.lookup(key).alpha_2
    except LookupError:
        return None  # no fuzzy matching: it maps "Republic of Korea" to North Korea
