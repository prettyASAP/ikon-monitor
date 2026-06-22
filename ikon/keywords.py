"""
Kulcsszó definíciók és forrástípus listák.

A kulcsszavak 3 tierre vannak osztva a várható zajszint alapján.
Új kulcsszó hozzáadásához az alábbi listákat bővítsd – a pipeline
automatikusan felveszi.
"""
from __future__ import annotations

KEYWORDS: dict[str, list[str]] = {
    "tier1_specifikus": [
        # Cégnevek – pontos egyezésnél 40 pont
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
        # Személyek
        "Somodi Hajnalka",
        "Vaszily Miklós",
        # Események
        "Big Picture Conference",
        "Televíziós Újságírók Díja",
        "Magyar Mozgókép Díj",
        "Mozgókép Fesztivál",
    ],
    "tier2_kozepes": [
        # Rövidítések / közepes zajszintű tulajdonnevek – 20 pont (FP nélkül)
        "IKO",
        "Dialogue",
        "Indamedia",
        "TV2",
        "Kovács Gergely",
        "Big Picture",
        "Nielsen közönségmérés",
        # Iparági specifikus kifejezések
        "televíziós műsorgyártás",
        "televíziós produkció",
        "műsorgyártás",
        "filmgyártás",
        "magyar filmgyártás",
        "produkciós cég",
        "executive producer",
    ],
    "tier3_generikus": [
        # Általános iparági kifejezések – 5 pont
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

# ---------------------------------------------------------------------------
# TV, Rádió, Műsorok profil kulcsszavai
# ---------------------------------------------------------------------------

TV_RADIO_KEYWORDS: dict[str, list[str]] = {
    "tier1_specifikus": [
        # Egyedi műsorcímek – minimális FP-kockázat
        "Megasztár",
        "Sztárban Sztár",
        "Sztárban Sztár All Stars",
        "A Nagy Duett",
        "Séfek Séfe",
        "Petőfi TV",
        "Petőfi Rádió",
        "Szerencsekerék",
        "Hal a tortán",
        "Nagy Ő",
        "Zsákbamacska",
        "Legyen Ön is Milliomos",
        "Házasság első látásra",
        "1% Klub",
        "Magyarország Szeretlek",
        "Petőfi Zenei Díj",
        "Vigyázat gyerekkel vagyok",
        "A szemfényvesztő",
        "Vészhelyzet az állatkórházban",
        "Next Topmodell Hungary",
        "Mutasd a hangod",
        "Gáspárék",
        "Szuperpáros",
        "Pénzt vagy éveket",
        "Neked énekelek",
        "Nicsak, kivagyok",
        "Ázsia Express",           # eredeti: "Ázsia Express 1-2 évad" → annotáció eltávolítva
        "50 milliós játszma",
        "Mintaapák",
        "Ninja Warrior",
        "Áll az alku",
        "Bezár a bazár",
    ],
    "tier2_kozepes": [
        # Ismert műsorcímek, de rövid / angolul / köznévként is élhetnek
        "Kincsvadászok",
        "True Crimes",
        "Farm VIP",
        "A Dal",
        # Magyar médiacsoportok – tulajdonosváltás, leépítés, szerkesztőségi hírek
        "Mediaworks",
    ],
    "tier3_generikus": [
        # Egyszavas köznevek – magas FP-kockázat, de monitorizálandók
        # Farm: mezőgazdasági cikkek is egyeznek (~85-95% FP)
        # Piramis: pénzügyi piramisjáték, Egyiptom (~80% FP)
        # Pepe: Schobert Bálint beceneve, de egyben brand/mém (~60% FP)
        # Totem, Kísértés: köznév/kulturális szó (~70-75% FP)
        "Kísértés",
        "Farm",
        "Piramis",
        "Pepe",
        "Totem",
    ],
}

# ---------------------------------------------------------------------------
# TV T3 show-context szűrők  (DS2: required-context FP detekció)
# Ha a cikk NEM tartalmaz ilyen mintát → a T3 egyezés hamis pozitív.
# TV műsorhírek elsősorban bulvárlapokban jelennek meg (DS2: ne büntesse a scoring).
# ---------------------------------------------------------------------------

TV_REQUIRED_CONTEXT: dict[str, str] = {
    # T3 kulcsszavak – show-kontextus hiánya → FP
    "Farm":     r"(műsor|adás|epizód|évad|versenyző|kiesett|szavazás|reality|RTL|TV2|döntő|farm\s+vip|farmos)",
    "Piramis":  r"(műsor|adás|epizód|évad|versenyző|kiesett|szavazás|reality|RTL|TV2|döntő|nyeremény|játékos)",
    "Kísértés": r"(műsor|adás|epizód|évad|versenyző|szavazás|reality|RTL|TV2|viasat|pár|couple)",
    "Pepe":     r"(schobert|gáspár|reality|műsor|RTL|TV2|adás|celeb|sztár|bálint)",
    "Totem":    r"(műsor|adás|epizód|évad|versenyző|kiesett|szavazás|reality|RTL|TV2|törzs|döntő)",
    # T2 magas FP-kockázatú kulcsszavak
    "A Dal":    r"(eurovízi|eurovision|dalverseny|döntő|finálé|győztes|versenyez|felvonul)",
    "True Crimes": r"(rtl|tv2|műsor|adás|epizód|évad|bűnügyi\s+műsor)",
    # T1 grammatikailag kétértelmű show-cím – DS + keywording QA lelet
    # "Nagy Ő" az irodalmi/köznapi "nagy ő" fordulatoktól megkülönböztetendő
    "Nagy Ő":   r"(reality|műsor|RTL|TV2|versenyző|randizik|döntő|flört|bachelor|szavaz|évad|kiesett)",
    # ---------------------------------------------------------------------------
    # HTÉN profil – film-kontextus hiánya → FP (whitelist logika)
    # ---------------------------------------------------------------------------
    # T3: Demjén Ferenc önálló zenészi karrierje ~90-95% FP; csak film-ctx esetén nem FP
    "Demjén Ferenc":   r"(htén|hogyan\s+tudnék\s+élni|film|mozi|musical|kirády|zenés\s+film|premier|moziadaptáci)",
    # T2: ismert sztárok – HTÉN-kontextus nélkül nem releváns a film-monitornak
    "Marics Peti":     r"(htén|hogyan\s+tudnék|film|mozi|kirády|zenés|musical|premier|\bbemutató\b)",
    "Orosz Dénes":     r"(htén|hogyan\s+tudnék|film|mozi|kirády|demjén|musical|premier|\bbemutató\b)",
    "Dyga Zsombor":    r"(htén|hogyan\s+tudnék|film|mozi|kirády|demjén|musical|premier|\bbemutató\b)",
    # T1: "ember" = közszó + "Márk" = gyakori keresztnév → politikai cikkekben is előfordul
    "Ember Márk":      r"(htén|hogyan\s+tudnék|film|mozi|kirády|demjén|musical|premier|\bbemutató\b)",
    # T2: köznyelvi fordulat is ("mindig ugyanúgy csinálja") – whitelist kötelező
    "Mindig ugyanúgy": r"(htén|hogyan\s+tudnék|film|mozi|kirády|musical|premier|\bbemutató\b|zenés)",
    # ---------------------------------------------------------------------------
    # NAPI profil – Life TV / Ozone TV / Media Vivantis
    # ---------------------------------------------------------------------------
    # T2: TV-személyek – Life TV/Ozone TV kontextus nélkül nem releváns
    "Hajdú Péter":   r"(life\s*tv|lifetv|ozone|media\s+vivantis|műsorvezető|televízió|csatorn|műsor)",
    "Gáspár Győző":  r"(life\s*tv|lifetv|vacsora|celebkonyha|műsor|adás|televízió)",
    # T2: klasszikus sorozatcímek – csak ha Life TV-kontextusban kerülnek elő
    "Columbo":       r"(life\s*tv|lifetv|klasszikus\s+sorozat|televíziós\s+legenda|sorozat.*sugároz|visszatér|adás)",
    # T3: ~95% FP; csak Life TV/Ozone TV kontextusban nem FP
    "Kiss Péter":    r"(life\s*tv|lifetv|ozone|műsorvezető|media\s+vivantis|televízió|csatorn)",
    # T3: magas köznyelvi FP – Reality/show-cím kontextus kötelező
    "Beköltözve":    r"(life\s*tv|lifetv|reality|sorozat|műsor|adás)",
    "Van életünk":   r"(life\s*tv|lifetv|sorozat|műsor|adás)",
    "Frizbi":        r"(life\s*tv|lifetv|műsor|adás|sorozat)",
    # T3: "Egyenlítő" = közföldr. terminus → Ozone TV show kontextus nélkül FP
    "Egyenlítő":     r"(ozone|ozone\s*tv|ozone\s+univerz|környezetvédelm|fenntarthatóság|műsor|adás)",
    # T3: "Magnum" = fagylalt + fegyver + TV-sorozat → csak TV-sorozat-kontextusban releváns
    "Magnum":        r"(life\s*tv|lifetv|sorozat|magnum\s+p\.?i|klasszikus|televíziós\s+legenda)",
    # T2: "Propeller" = Media Vivantis online platform, de "propeller" = légcsavar is
    "Propeller":     r"(media\s+vivantis|life\s*tv|lifetv|ozone|platform|portál|online\s+tartalom|streaming|videó)",
    # T2: Life TV brandelt műsorkategóriák – Life TV kontextus nélkül generikus szókapcsolat
    "klasszikus sorozat": r"(life\s*tv|lifetv|ozone|media\s+vivantis)",
    "televíziós legenda": r"(life\s*tv|lifetv|ozone|media\s+vivantis)",
    # ---------------------------------------------------------------------------
    # NAPI profil – TV2 műsorvezetők
    # ---------------------------------------------------------------------------
    "Orsovai Reni":     r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|mokka|celeb|sztár)",
    "Liptai Claudia":   r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|mokka|celeb|sztár)",
    "Sebestyén Balázs": r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|fomo|rádió|celeb|sztár)",
    "Istenes Bence":    r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|mokka|farm|celeb|sztár)",
    "Sarka Kata":       r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|celeb|sztár)",
    "Csobot Adél":      r"(tv2|televízió|műsorvezető|műsor|adás|csatorn|marics|celeb|sztár)",
}

# DS2: bulvár büntetés kizárva TV show T3 kulcsszavaknál
# (ezekre a bulvársajtó az elsődleges forrás, a penalty kontraproduktív)
TV_T3_SHOW_KEYWORDS: frozenset[str] = frozenset(TV_RADIO_KEYWORDS.get("tier3_generikus", []))

# ---------------------------------------------------------------------------
# HTÉN – „Hogyan tudnék élni nélküled?" profil kulcsszavai
# ---------------------------------------------------------------------------

HTEN_KEYWORDS: dict[str, list[str]] = {
    "tier1_specifikus": [
        # Film teljes cím-variációk – minimális FP-kockázat
        "Hogyan tudnék élni nélküled",
        "Hogyan tudnék élni nélküled?",
        "HTÉN",
        "Hogyan tudnék élni nélküled film",
        "Hogyan tudnék élni nélküled mozi",
        "Hogyan tudnék élni nélküled 2",
        "Hogyan tudnék élni nélküled folytatás",
        "HTÉN 2",
        # IKO-direkt kapcsolat – T1-es cikk mindig releváns
        "Kirády Attila IKO",
        # Filmspecifikus compound kifejezések
        "Demjén musical film",
        "Mindig ugyanúgy film",
        # Kevéssé ismert színészek – alacsony önálló FP-kockázat
        "Kormos Anett",
        "Goda Krisztina",
        "Törőcsik Franciska",
        "Ember Márk",
        "Márkus Luca",
        "Varga-Járó Sára",
        "Brasch Bence",
    ],
    "tier2_kozepes": [
        # Rendező/producer – közepes FP (IKO-s, de önálló cikkei is vannak)
        "Kirády Attila",
        "Kirády Attila producer",
        # Ismert sztárok – TV_REQUIRED_CONTEXT szűri a nem-HTÉN cikkeket
        "Marics Peti",
        "Orosz Dénes",
        "Dyga Zsombor",
        # Demjén-örökség kifejezések – közepes FP, monitoring értékes
        "Demjén-slágerek",
        "Demjén film",
        # Sláger-cím – nagyon magas köznyelvi FP → required context kötelező
        "Mindig ugyanúgy",
    ],
    "tier3_generikus": [
        # Legendás zenész – ~90% FP, csak film-kontextussal nem FP
        "Demjén Ferenc",
    ],
}

# DS2: bulvár büntetés kizárva HTÉN film T3 kulcsszavaknál is
# (filmpremier-hírek elsősorban szórakoztató/bulvár médiában jelennek meg)
HTEN_T3_FILM_KEYWORDS: frozenset[str] = frozenset(HTEN_KEYWORDS.get("tier3_generikus", []))

# ---------------------------------------------------------------------------
# NAPI profil – Media Vivantis: Life TV + Ozone TV
# ---------------------------------------------------------------------------

NAPI_KEYWORDS: dict[str, list[str]] = {
    "tier1_specifikus": [
        # Media Vivantis cégcsoport – teljes/compound nevek, egyedi
        "Media Vivantis Műsorszolgáltató Zrt",
        "Media Vivantis médiacsoport",
        "Media Vivantis televízió",
        # Life TV – saját gyártás és premier jellegű compound kifejezések
        "Life TV saját gyártás",
        "Life TV premier",
        # Ozone TV – saját gyártás + branded platform
        "Ozone TV saját gyártás",
        "Ozone Univerzum",
        # Egyedi műsorcímek – alacsony FP-kockázat
        "Vacsorakirály",
        "Rex Kanadában",
        "Hogyan készül? Megmutatjuk!",
        # Media Vivantis tulajdonos – korábban iko_ceg UNIQUE-konfliktus
        "Vaszily Miklós",
    ],
    "tier2_kozepes": [
        # Media Vivantis rövidebb névalak
        "Media Vivantis",
        # Life TV – csatorna és műsor-monitoring
        "Life TV",
        "LifeTV",
        "Life TV műsor",
        "Life TV nézettség",
        # Ozone TV – csatorna és műsor-monitoring
        "Ozone TV",
        "OzoneTV",
        "Ozone TV műsor",
        "Ozone TV nézettség",
        # Ozone-kapcsolódó tartalomtípusok
        "Ozone magazin",
        "környezetvédelmi műsor",
        "fenntarthatósági műsor",
        # Személyek – required context szükséges (magas FP)
        "Hajdú Péter",
        "Gáspár Győző",
        # TV2 műsorvezetők – required context: tv2/televízió/műsorvezető/celeb kontextus kötelező
        "Orsovai Reni",
        "Liptai Claudia",
        "Sebestyén Balázs",
        "Istenes Bence",
        "Sarka Kata",
        "Csobot Adél",
        # Klasszikus sorozatcímek – required context szükséges
        "Columbo",
        # Media Vivantis online platform – egyedi szó de "propeller" = légcsavar is
        "Propeller",
        # Brandelt Life TV műsorkategóriák – required context kötelező
        "klasszikus sorozat",
        "televíziós legenda",
        # Magyar médiacsoportok – tulajdonosváltás, leépítés, szerkesztőségi hírek
        "Mediaworks",
        # Médiaipari személyek – korábban iko_ceg UNIQUE-konfliktus
        "Kovács Gergely",
        "Nielsen közönségmérés",
        # Life TV saját domainje – URL megjelenése önmagában elegendő kontextus
        "lifetv.hu",
    ],
    "tier3_generikus": [
        # Személynév, rendkívül magas FP (~95%) – required context kötelező
        "Kiss Péter",
        # Köznyelvi fordulatok, show-cím csak Life TV kontextusban releváns
        "Beköltözve",
        "Van életünk",
        "Frizbi",
        # Ozone TV show, de "Egyenlítő" = közföldr. terminus (~80% FP)
        "Egyenlítő",
        # TV-sorozat, de "Magnum" = fagylalt/fegyver is (~90% FP)
        "Magnum",
        # Általános médiaipari kifejezések – korábban iko_ceg UNIQUE-konfliktus
        "nézettség",
        "televíziós piac",
        "magyar televíziózás",
        "médiapiac",
        "televíziós reklámpiac",
        "csatornaindítás",
        "csatorna-megújulás",
        "műsorstruktúra",
        "nézettségi adatok",
        "televíziós közönségarány",
        # Generikus műfaj/köznév szavak – required context szűri a Life TV-n kívüli találatokat
        "akció",
        "bulvár",
        "bűnügy",
        "celebek",
        "detektív",
        "életmód",
        "főzés",
        "gasztronómia",
        "Hawaii",
        "humor",
        "interjú",
        "Kábeltévé",
        "kikapcsolódás",
        "krimi",
        "közösség",
        "magánélet",
        "média",
        "műsor",
        "nosztalgia",
        "nyomozás",
        "otthon",
        "Produkció",
        "recept",
        "retro",
        "Saját gyártás",
        "sorozat",
        "szórakoztatás",
        "sztárok",
        "televízió",
        "televíziós tartalom",
        "vacsora",
        "vendégek",
        "család",
        "beszélgetés",
    ],
}

# NAPI T3: csak a show/sorozat T3 kulcsszavak mentesek a bulvár penalty alól.
# A médiaipari általánosabb T3 szavak (nézettség, médiapiac stb.) nem szerepelnek
# itt – azokra a bulvár büntetés normálisan alkalmazandó.
NAPI_T3_KEYWORDS: frozenset[str] = frozenset({
    "Kiss Péter", "Beköltözve", "Van életünk", "Frizbi", "Egyenlítő", "Magnum",
})

# Egyesített T3 bulvár-mentességi lista (TV show + HTÉN film + NAPI)
T3_NO_BULVAR_KEYWORDS: frozenset[str] = TV_T3_SHOW_KEYWORDS | HTEN_T3_FILM_KEYWORDS | NAPI_T3_KEYWORDS

# Személy-néveknél a teljes névalaknak (egybefüggő frázisként) meg kell jelennie
# a cikk szövegében – hirkereso.hu tokenizált keresésnél a névkomponensek
# egymástól függetlenül is megjelenhetnek (pl. "Kiss Márió" + "Magyar Péter"
# → hamisan illeszkedik a "Kiss Péter" kulcsszóra).
# Kivétel: Vaszily Miklós – annyira egyedi, hogy önmagában is azonosítja a személyt.
FULL_NAME_REQUIRED: frozenset[str] = frozenset({
    # NAPI profil
    "Kiss Péter",
    "Hajdú Péter",
    "Gáspár Győző",
    "Kovács Gergely",
    # NAPI profil – TV2 műsorvezetők
    "Orsovai Reni",
    "Liptai Claudia",
    "Sebestyén Balázs",
    "Istenes Bence",
    "Sarka Kata",
    "Csobot Adél",
    # HTÉN profil
    "Ember Márk",
    "Marics Peti",
    "Orosz Dénes",
    "Dyga Zsombor",
    "Demjén Ferenc",
})

# ---------------------------------------------------------------------------
# IKO kombinált profil (iko_ceg + tv_radio_musorok + hten egybeolvasztva)
# ---------------------------------------------------------------------------

def _merge(*dicts: dict) -> dict:
    """Három profil tier-jeit egyesíti, duplikátumok nélkül (sorrend megtartva)."""
    merged: dict[str, list[str]] = {}
    for d in dicts:
        for tier, kws in d.items():
            seen = set(merged.get(tier, []))
            merged.setdefault(tier, []).extend(kw for kw in kws if kw not in seen)
            seen.update(kws)
    return merged

IKO_COMBINED_KEYWORDS: dict[str, list[str]] = _merge(
    KEYWORDS, TV_RADIO_KEYWORDS, HTEN_KEYWORDS
)

# ---------------------------------------------------------------------------
# Gyors lookup táblák  (DS3: mind a négy profilt tartalmazza)
# ---------------------------------------------------------------------------

KEYWORD_TIER: dict[str, str] = {
    **{kw: tier for tier, kws in KEYWORDS.items() for kw in kws},
    **{kw: tier for tier, kws in TV_RADIO_KEYWORDS.items() for kw in kws},
    **{kw: tier for tier, kws in HTEN_KEYWORDS.items() for kw in kws},
    **{kw: tier for tier, kws in NAPI_KEYWORDS.items() for kw in kws},
}

ALL_KEYWORDS: list[str] = [
    kw for kws in KEYWORDS.values() for kw in kws
] + [
    kw for kws in TV_RADIO_KEYWORDS.values() for kw in kws
] + [
    kw for kws in HTEN_KEYWORDS.values() for kw in kws
] + [
    kw for kws in NAPI_KEYWORDS.values() for kw in kws
]

# ---------------------------------------------------------------------------
# Kontextus szavak (részleges egyezés a szövegben – bónusz pontokhoz)
# ---------------------------------------------------------------------------

CONTEXT_WORDS: list[str] = [
    "tv2", "műsor", "produkci", "csatorn", "televízi",
    "nézett", "médiai", "gyártó", "reklám", "adás", "sorozat",
]

# ---------------------------------------------------------------------------
# Tier 3 médiaipari-specifikus kulcsszavak
# (médiaipari forrásból jövő cikkeknél Felülvizsgálandóba kerülnek)
# ---------------------------------------------------------------------------

TIER3_MEDIA_CORE: frozenset[str] = frozenset({
    "médiapiac",
    "televíziós piac",
    "televíziós reklámpiac",
    "nézettség",
    "nézettségi adatok",
    "közönségmérés",
    "televíziós közönségarány",
    "csatornaindítás",
    "csatorna-megújulás",
    "műsorstruktúra",
    "magyar televíziózás",
})

# ---------------------------------------------------------------------------
# False positive reguláris kifejezések tier2 kulcsszavakhoz
# ---------------------------------------------------------------------------

FALSE_POSITIVE_PATTERNS: dict[str, list[str]] = {
    # IKO: minden IKO...-val kezdődő kulcsszóra a _is_false_positive() kezeli
    # (nagybetűs \bIKO\b hiánya → FP)
    "Dialogue": [
        r"dialogue(?!\s+creative)",
        r"párbeszéd",
    ],
    "producer": [
        r"\bproducer\b(?!\s*:?\s*(?:iko|dialogue|tv2|indamedia|vaszily|somodi|kovács))",
    ],
    "Big Picture": [
        r"big picture(?!\s+conference)",
    ],
    "Kovács Gergely": [
        # Politikai kontextus → FP (MKKP-vezető, nem a TV2 ügyvezetője)
        # A negatív lookahead eltávolítva: névelők (a, az) közbülső szavak miatt tévesen triggelt
        r"kutya\s*párt|mkkp|társelnök|képviselő|politikus|önkormányzat|polgármester|parlamenti|frakció",
    ],
}

# ---------------------------------------------------------------------------
# Forrástípus klasszifikáció
# (hirkereso.hu forrásnév → SourceType)
# ---------------------------------------------------------------------------

SOURCES_MEDIA: frozenset[str] = frozenset({
    # Hírportálok
    "444.hu", "24.hu", "hvg.hu", "Telex", "Index", "Index - g", "Index - kf",
    "Infostart", "Origo", "Népszava", "MagyarHang", "MHírlap", "MNemzet",
    "Mandiner", "Demokrata", "Klubrádió", "Hírklikk",
    # Gazdasági / üzleti
    "VG", "Portfólió", "Pénzc.", "Tőzsdefórum", "Mfor", "PiacProfit",
    "Economx", "Forbes", "Privátbankár", "SzMo.hu", "Kontroll.hu",
    # Médiaipar specifikus
    "Médiapiac", "Media1", "Mark&Média", "Kreatív", "Marketing&Media",
    # TV / rádió hírek
    "ATV", "Hír TV",
    # TV csatorna-portálok (show-hírek elsődleges forrásai – keywording QA lelet)
    "RTL.hu", "rtl.hu", "TV2.hu", "tv2.hu", "Tv2.hu",
    "M1", "M2", "Duna TV", "Duna World", "Petőfi TV",
    # Egyéb komoly
    "Ma.hu", "Alon.hu", "DigHungary", "ACNews", "Contextus",
})

SOURCES_TABLOID: frozenset[str] = frozenset({
    "Blikk", "Blikk.", "BorsOnline", "Femcafe", "Life.hu", "Glamour",
    "Femina",
    "Kiskegyed", "NLC", "InStyle", "Rúzs Online", "Dívány", "Elle",
    "Cosmopolitan", "Ripost", "StarFM", "Sassy", "IgényesFfi",
    "Twice", "Metropol", "Bors", "Story", "Hot!", "Sláger FM",
    # Show/celeb portálok (TV műsortartalom elsőrendű forrásai)
    "Port.hu", "Sztárlexikon", "Bestmagazin", "Poptarisznya",
    "Sztar.hu", "sztar.hu",
})
