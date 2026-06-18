KEYWORDS = {
    "tier1_specifikus": [
        "IKO Műsorgyártó Magyarország Kft.",
        "IKO Műsorgyártó",
        "IKO Magyarország",
        "IKO Production",
        "IKO Productions",
        "Dialogue Creatives Kft.",
        "Dialogue Creatives",
        "Dialogue Creative Agency",
        "Dialogue reklámügynökség",
        "Indamedia Sales House",
        "Somodi Hajnalka",
        "Vaszily Miklós",
        "Big Picture Conference",
        "Televíziós Újságírók Díja",
        "Magyar Mozgókép Díj",
        "Mozgókép Fesztivál",
    ],
    "tier2_kozepes": [
        "IKO",
        "Dialogue",
        "Indamedia",
        "TV2",
        "Kovács Gergely",
        "Big Picture",
        "Nielsen közönségmérés",
        "televíziós műsorgyártás",
        "televíziós produkció",
        "műsorgyártás",
        "filmgyártás",
        "magyar filmgyártás",
        "produkciós cég",
        "executive producer",
    ],
    "tier3_generikus": [
        "producer",
        "nézettség",
        "nézettségi adatok",
        "médiapiac",
        "televíziós piac",
        "magyar televíziózás",
        "televíziós reklámpiac",
        "csatornaindítás",
        "csatorna-megújulás",
        "műsorstruktúra",
        "közönségmérés",
        "televíziós közönségarány",
        "content marketing",
        "branded content",
        "natív hirdetés",
        "natív tartalom",
        "szponzorált tartalom",
        "tartalomstratégia",
        "gyártó cég",
    ],
}

# Flat lookup: keyword → tier name
KEYWORD_TIER = {}
for tier, kws in KEYWORDS.items():
    for kw in kws:
        KEYWORD_TIER[kw] = tier

ALL_KEYWORDS = [kw for tier in KEYWORDS.values() for kw in tier]

# Médiaipari kontextus szavak a bónusz pontokhoz
CONTEXT_WORDS = [
    "tv2", "műsor", "produkci", "csatorn", "televízi",
    "nézett", "médiai", "gyártó", "reklám", "adás", "sorozat",
    "iko", "dialogue", "indamedia", "vaszily", "somodi",
]

# Tier 3 kulcsszavak, amelyek médiaipari forrásból jövő cikkeknél
# biztonsági hálóba kerülnek (Felülvizsgálandó, nem Zaj)
TIER3_MEDIA_CORE = {
    "médiapiac", "televíziós piac", "televíziós reklámpiac",
    "nézettség", "nézettségi adatok", "közönségmérés",
    "televíziós közönségarány", "csatornaindítás", "csatorna-megújulás",
    "műsorstruktúra", "magyar televíziózás",
}

# False positive minták: ha ezek EGYEDÜL szerepelnek → nem releváns
FALSE_POSITIVE_PATTERNS = {
    "IKO": [r"ikon(?:ikus|ikonussá|ikusan|ikussá|ná|vá|ja|juk)?\b", r"\bikon\b"],
    "Dialogue": [r"dialogue(?!\s+creative)", r"párbeszéd"],
    "producer": [r"\bproducer\b(?!\s*:?\s*(?:iko|dialogue|tv2|indamedia|vaszily|somodi|kovács))"],
    "Big Picture": [r"big picture(?!\s+conference)"],
    "Kovács Gergely": [r"kovács gergely(?!\s+(?:iko|tv2|vaszily|dialogue|médiaipari|gyártó|műsor))"],
}

# Forrástípus klasszifikáció
# Exact source names as they appear in hirkereso.hu (run scraper and check raw CSV to extend)
SOURCES_MEDIA = {
    # Hírportálok / komoly sajtó
    "444.hu", "24.hu", "hvg.hu", "Telex", "Index", "Index - g", "Index - kf",
    "Infostart", "Origo", "Népszava", "MagyarHang", "MHírlap", "MNemzet",
    "Mandiner", "Demokrata", "Klubrádió", "Hírklikk",
    # Gazdasági / üzleti
    "VG", "Portfólió", "Pénzc.", "Tőzsdefórum", "Mfor", "PiacProfit",
    "Economx", "Forbes", "Privátbankár", "SzMo.hu", "Kontroll.hu",
    # Médiaipar specifikus
    "Médiapiac", "Media1", "Mark&Média", "Kreatív", "Marketing&Media",
    # TV / rádió hír
    "ATV", "Hír TV",
    # Egyéb komoly
    "Ma.hu", "Alon.hu", "DigHungary", "ACNews", "Contextus",
}

SOURCES_BULVAR = {
    "Blikk", "Blikk.", "BorsOnline", "Femcafe", "Life.hu", "Glamour",
    "Femina", "Femina ",  # trailing space variáns
    "Kiskegyed", "NLC", "InStyle", "Rúzs Online", "Dívány", "Elle",
    "Cosmopolitan", "Ripost", "StarFM", "Sassy", "IgényesFfi",
    "Twice", "Metropol", "Bors", "Story", "Hot!", "Sláger FM",
    "Port.hu",  # szórakozás/film oldal
}
