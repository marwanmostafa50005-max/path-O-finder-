"""About page — the two-part copy below is EXACT per the build brief (§12)
and must not be altered."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QLabel, QScrollArea, QVBoxLayout, QWidget)

from .. import APP_NAME, SLOGAN, __version__
from . import theme

PHILOSOPHY_TITLE = "The path-O-finder philosophy"
PHILOSOPHY = (
    "I built path-O-finder because of a quiet problem I kept seeing at the "
    "coalface: results come back, they are looked at once, and then — in the rush "
    "of a working week — some of them slip. Not through anyone's carelessness, "
    "but because nothing was watching the results that fall between the "
    "requesting, the reviewing, and the recall. path-O-finder is that watcher. It "
    "is a safety net, not an inspector. Its philosophy is deliberately narrow. "
    "path-O-finder reads the results a practice already receives, notices the "
    "abnormal ones that do not yet show evidence of being actioned, and places "
    "them in front of the treating doctor each morning for a decision. It does "
    "not diagnose. It does not prescribe, and it will never suggest a dose. It "
    "does not overrule anyone's judgement. Where a result is abnormal, it points "
    "to the relevant, current clinical guideline — by name, edition and section — "
    "and leaves the thinking where it belongs: with the clinician. Three "
    "principles are non-negotiable. First, the software is cautious to a fault: "
    "when it is not certain it has read a result correctly, it says so and asks "
    "for human eyes rather than guess. Second, a clinician is always in the loop "
    "— nothing is ever marked 'handled' by the machine; a doctor or nurse signs "
    "off, and the software simply remembers. Third, the data never leaves the "
    "building. path-O-finder runs on the practice's own local server, "
    "disconnected from the internet, and before any analysis is run the clinician "
    "enters their initials — the same discipline we keep at the dispensing bench "
    "and in the drugs register. Every result finds its path, and every path is "
    "one a clinician chose."
)

FOUNDER_TITLE = "About the founder"
FOUNDER = (
    "Marwan Morsy, B.Pharm — AHPRA Reg. PHA0002761764. Marwan is a pharmacy "
    "manager practising in rural New South Wales, with ten years of clinical "
    "pharmacy experience across three health systems. He is credentialed in "
    "non-sterile compounding and immunisation, is an authorised UTI prescriber "
    "under the NSW program, and provides opioid pharmacotherapy services. He "
    "holds a Bachelor of Pharmacy from the Faculty of Pharmacy, Cairo University "
    "— ranked 13th worldwide in Pharmacology & Toxicology (U.S. News & World "
    "Report Best Global Universities, 2026). He is the software architect of "
    "path-O-finder and the clinician who will validate it against real practice "
    "data."
)


class AboutView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(48, 32, 48, 32)
        lay.setSpacing(16)

        logo = QLabel()
        pix = QPixmap(str(theme.logo_path()))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToWidth(360, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(logo)

        title = QLabel(f"{APP_NAME}  ·  v{__version__}")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)

        slogan = QLabel(SLOGAN)
        slogan.setObjectName("subtitle")
        slogan.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(slogan)

        for heading, body in ((PHILOSOPHY_TITLE, PHILOSOPHY), (FOUNDER_TITLE, FOUNDER)):
            h = QLabel(heading)
            h.setObjectName("title")
            lay.addWidget(h)
            b = QLabel(body)
            b.setWordWrap(True)
            b.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(b)

        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
