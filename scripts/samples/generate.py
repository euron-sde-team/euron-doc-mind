"""Generate the demo corpus in samples/: one fictional company, every supported format.

Northwind Robotics builds autonomous warehouse robots. The documents agree with each other
(the budget matches the board deck, the contract matches the customer list), so questions
across files have real answers. Run from apps/api:

    uv run --group samples python ../../scripts/samples/generate.py
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import docx
import openpyxl
from docx.shared import Pt
from openpyxl.styles import Alignment, Font, PatternFill
from pptx import Presentation
from pptx.util import Inches
from pptx.util import Pt as PPt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parents[2] / "samples"
STYLES = getSampleStyleSheet()
BODY = ParagraphStyle("Body", parent=STYLES["BodyText"], fontSize=10.5, leading=15, spaceAfter=6)
H1 = ParagraphStyle(
    "H1",
    parent=STYLES["Heading1"],
    fontSize=18,
    spaceAfter=10,
    textColor=colors.HexColor("#1f2a44"),
)
H2 = ParagraphStyle(
    "H2",
    parent=STYLES["Heading2"],
    fontSize=13,
    spaceBefore=10,
    spaceAfter=6,
    textColor=colors.HexColor("#33415c"),
)


def _bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(text, BODY), leftIndent=12) for text in items],
        bulletType="bullet",
        start="\u2022",
        leftIndent=14,
    )


def _table(rows: list[list[str]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf4")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5cbd8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _pdf(path: Path, title: str, author: str, story: list[object]) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=title,
        author=author,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(story)


def handbook() -> None:
    p = lambda text: Paragraph(text, BODY)  # noqa: E731
    story: list[object] = [
        Paragraph("Northwind Employee Handbook 2026", H1),
        p(
            "Version 4.0, effective 1 January 2026. Owned by People Operations. This handbook applies to every "
            "Northwind Robotics employee in Austin, Berlin and Pune. Where local law gives you more, local law wins."
        ),
        Paragraph("Welcome to Northwind", H2),
        p(
            "Northwind Robotics designs, builds and operates autonomous mobile robots for warehouses. We were founded "
            "in 2019 and today run more than 1,300 robots for over 200 customers. Our mission is to take the walking "
            "out of warehouse work so people can spend their shifts on the jobs that need judgement."
        ),
        p(
            "Every new joiner gets an onboarding buddy for the first 60 days and a 30, 60 and 90 day check-in with "
            "their manager."
        ),
        Paragraph("Working hours and flexibility", H2),
        p(
            "The standard working week is 40 hours. Core collaboration hours are 10:00 to 16:00 in your office's local "
            "time zone; outside core hours you choose when to work, as long as your team can rely on you."
        ),
        p(
            "Overtime for hourly roles must be approved in advance by your manager and is paid at 1.5 times the "
            "normal rate."
        ),
        Paragraph("Remote work", H2),
        p(
            "Northwind is hybrid by default: three days a week in the office and two days wherever you work best. "
            "Fully remote arrangements need approval from your department head and People Operations."
        ),
        p(
            "You may work from another country for up to 30 days in a calendar year. Each trip needs written approval "
            "from your manager and People Operations at least 10 working days before you travel, because tax, visa and "
            "data protection rules differ by country. Robot field work and access to customer sites are not allowed "
            "from abroad."
        ),
        PageBreak(),
        Paragraph("Time off", H2),
        p(
            "<b>Annual leave.</b> Every full-time employee receives 24 working days of paid annual leave per year, "
            "accrued at two days per month. Part-time employees receive a pro-rated amount. Up to 5 unused days may be "
            "carried over into the next year and must be used by 31 March."
        ),
        p(
            "<b>Public holidays.</b> You get the public holidays of the office you are contracted to. The People "
            "Operations calendar lists them every December."
        ),
        p(
            "<b>Sick leave.</b> You receive 10 paid sick days per year. Tell your manager as early as you can on the "
            "first day. A doctor's note is required after three consecutive sick days."
        ),
        p(
            "<b>Parental leave.</b> Primary caregivers receive 26 weeks of fully paid parental leave. Secondary caregivers "
            "receive 12 weeks of fully paid leave. Leave can start up to four weeks before the expected birth or "
            "adoption date and must be taken within 18 months of it. When you return you can work a phased return of "
            "four weeks at 80 percent of your hours on full pay."
        ),
        p(
            "<b>Bereavement leave.</b> Up to 5 paid days for the loss of a close family member, and 2 days for "
            "extended family."
        ),
        p(
            "<b>Requesting leave.</b> Request leave in the HR portal at least two weeks ahead for anything longer than "
            "three days. Your manager approves or declines within three working days."
        ),
        PageBreak(),
        Paragraph("Travel and expenses", H2),
        p(
            "Book all travel through TripDesk so we know where you are if something goes wrong. Choose the most "
            "economical option that gets the job done."
        ),
        _bullets(
            [
                "Flights: economy class for flights under 6 hours. Business class is allowed for flights of 6 hours or "
                "longer, or for overnight flights followed by a working day.",
                "Hotels: up to $220 per night in the United States, 180 euros per night in Europe and 9,000 rupees per "
                "night in India.",
                "Meals: a daily meal allowance of $75 in the United States, 60 euros in Europe and 3,500 rupees in India.",
                "Ground transport: public transport or ride sharing; rental cars need manager approval.",
            ]
        ),
        p(
            "Submit expenses in the finance portal within 30 days of the trip with receipts for anything over $25. "
            "Expenses submitted later than 90 days are not reimbursed."
        ),
        _table(
            [
                ["Item", "United States", "Europe", "India"],
                ["Hotel per night", "$220", "180 euros", "9,000 rupees"],
                ["Meals per day", "$75", "60 euros", "3,500 rupees"],
                ["Receipt required above", "$25", "25 euros", "2,000 rupees"],
            ],
            [55 * mm, 35 * mm, 35 * mm, 35 * mm],
        ),
        Paragraph("Equipment and learning", H2),
        p(
            "You get a laptop on your first day, refreshed every three years, and a one-time home office stipend of "
            "$500. Every employee also has a learning budget of $1,500 per year for courses, books and conferences."
        ),
        PageBreak(),
        Paragraph("Security basics", H2),
        _bullets(
            [
                "Multi-factor authentication is mandatory on every company account.",
                "Use the company password manager; never reuse passwords.",
                "Lock your screen whenever you step away, including in the office.",
                "Report a suspected incident within one hour in the #security channel or at security@northwind.example. "
                "The Security Incident Response Runbook explains severities and who is paged.",
            ]
        ),
        Paragraph("Performance and growth", H2),
        p(
            "Performance reviews happen twice a year, in April and October. Each review covers your goals, how you "
            "worked with others and your growth plan. Promotions are decided in the October cycle."
        ),
        Paragraph("Code of conduct", H2),
        p(
            "Treat colleagues, customers and partners with respect. Harassment and discrimination are never acceptable. "
            "Report concerns to your manager, People Operations or the anonymous ethics line."
        ),
    ]
    _pdf(
        OUT / "Northwind Employee Handbook 2026.pdf",
        "Northwind Employee Handbook 2026",
        "People Operations",
        story,
    )


def contract() -> None:
    p = lambda text: Paragraph(text, BODY)  # noqa: E731
    story: list[object] = [
        Paragraph("Master Services Agreement: Northwind Robotics and Globex Corporation", H1),
        p(
            "This Master Services Agreement (the Agreement) is entered into on 1 July 2026 (the Effective Date) between "
            "Northwind Robotics, Inc. (Northwind) and Globex Corporation (Globex)."
        ),
        Paragraph("1. Services", H2),
        p(
            "Northwind will deploy and operate a fleet of 120 Atlas autonomous mobile robots across Globex's Reno and "
            "Columbus distribution centres, together with the Northwind Fleet software subscription and 24/7 support."
        ),
        Paragraph("2. Term", H2),
        p(
            "The Agreement starts on the Effective Date and runs for an initial term of three years. It renews "
            "automatically for successive one-year terms unless either party gives notice of non-renewal at least 60 "
            "days before the end of the current term."
        ),
        Paragraph("3. Fees", H2),
        p(
            "The total contract value for the initial term is $4.2 million: robot hardware leases of $2.4 million, "
            "software subscriptions of $1.35 million and deployment and support services of $450,000. Invoices are "
            "issued quarterly in advance and are payable within 45 days."
        ),
        Paragraph("4. Service levels", H2),
        p(
            "Northwind commits to 99.9 percent monthly availability of the Fleet software. If availability falls below "
            "the commitment, Globex receives a service credit of 5 percent of that month's software fees for each 0.1 "
            "percent below 99.9 percent, capped at 25 percent of the monthly fees."
        ),
        _table(
            [
                ["Priority", "Definition", "Response", "Target resolution"],
                ["P1", "Fleet stopped at a site", "15 minutes, 24/7", "4 hours"],
                ["P2", "Degraded throughput", "1 hour, 24/7", "1 business day"],
                ["P3", "Question or minor defect", "1 business day", "10 business days"],
            ],
            [18 * mm, 55 * mm, 40 * mm, 40 * mm],
        ),
        PageBreak(),
        Paragraph("5. Termination", H2),
        p(
            "Either party may terminate the Agreement for convenience with 90 days' written notice, but not before the "
            "end of the first 12 months. Either party may terminate for material breach if the breach is not cured "
            "within 30 days of written notice. On termination Northwind will recover its robots within 45 days."
        ),
        Paragraph("6. Data protection", H2),
        p(
            "Operational data from the robots stays in the region where it is collected. Northwind processes Globex "
            "data only to provide the services and deletes it within 60 days of termination unless the law requires "
            "otherwise."
        ),
        Paragraph("7. Liability", H2),
        p(
            "Each party's total liability is capped at the fees paid in the 12 months before the claim, except for "
            "breaches of confidentiality, data protection obligations or gross negligence."
        ),
        Paragraph("8. Governing law", H2),
        p("This Agreement is governed by the laws of the State of Delaware."),
    ]
    _pdf(
        OUT / "Globex Master Services Agreement.pdf",
        "Globex Master Services Agreement",
        "Northwind Legal",
        story,
    )


def board_deck() -> None:
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)
    deck.core_properties.title = "Q3 2026 Board Update"

    def slide(title: str, bullets: list[str], notes: str) -> None:
        s = deck.slides.add_slide(deck.slide_layouts[1])
        s.shapes.title.text = title
        frame = s.placeholders[1].text_frame
        frame.text = bullets[0]
        for line in bullets[1:]:
            frame.add_paragraph().text = line
        for paragraph in frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = PPt(22)
        s.notes_slide.notes_text_frame.text = notes

    cover = deck.slides.add_slide(deck.slide_layouts[0])
    cover.shapes.title.text = "Q3 2026 Board Update"
    cover.placeholders[1].text = "Northwind Robotics, October 2026"
    slide(
        "Quarter highlights",
        [
            "Revenue of $18.4 million, up 32 percent year over year",
            "Annual recurring revenue reached $71.2 million",
            "14 new enterprise customers, including Globex",
            "Atlas v2 pilots running at 3 customer sites",
            "Gross margin improved to 61 percent",
        ],
        "Revenue beat plan by 6 percent. The beat came mostly from software subscriptions, which grew faster than hardware.",
    )

    table_slide = deck.slides.add_slide(deck.slide_layouts[5])
    table_slide.shapes.title.text = "Revenue by segment"
    rows = [
        ["Segment", "Q3 2026 revenue", "Year over year"],
        ["Robot hardware", "$9.1M", "+21%"],
        ["Fleet software subscriptions", "$6.8M", "+58%"],
        ["Deployment and support services", "$2.5M", "+19%"],
        ["Total", "$18.4M", "+32%"],
    ]
    shape = table_slide.shapes.add_table(
        len(rows), 3, Inches(0.8), Inches(1.8), Inches(11.5), Inches(3.2)
    )
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            shape.table.cell(r, c).text = value
    table_slide.notes_slide.notes_text_frame.text = (
        "Software is now 37 percent of revenue, up from 31 percent a year ago."
    )

    slide(
        "Customers",
        [
            "212 customers in total, net revenue retention of 118 percent",
            "Logo churn of 2.1 percent over the last twelve months",
            "Largest new contracts: Globex ($4.2M total contract value) and Initech ($1.9M)",
        ],
        "Both churned logos this quarter were small single-site customers that consolidated warehouses.",
    )
    slide(
        "Product",
        [
            "Atlas v2 on track for general availability in March 2027",
            "Navigation stack v5 cut manual interventions by 41 percent",
            "Fleet software 4.2 shipped multi-floor mapping",
        ],
        "Atlas v2 carries 35 kg, up from 25 kg, which opens the cold storage and beverage segments.",
    )
    slide(
        "Operations",
        [
            "1,340 robots deployed across customer sites",
            "Fleet uptime of 99.4 percent",
            "Average deployment time cut from 21 to 12 days",
        ],
        "Deployment time fell because site mapping is now done remotely from the customer's floor plans.",
    )
    slide(
        "People",
        [
            "Headcount of 286, on track for 300 by year end",
            "Engineering headcount of 132",
            "Attrition of 9 percent, below the 12 percent plan",
        ],
        "Senior robotics hiring is the slowest area; we added a recruiting partner in Berlin.",
    )
    slide(
        "Key risks",
        [
            "LiDAR supply: a single supplier provides all sensors; second supplier to be qualified by Q1 2027",
            "Customer concentration: the top 5 customers are 38 percent of revenue",
            "Regulation: EU AI Act obligations for safety systems; legal review under way",
            "Hiring: senior robotics engineers are slower to hire than planned",
        ],
        "The LiDAR risk is the most urgent. A six-week supplier delay would push about $3 million of Q1 revenue into Q2.",
    )
    slide(
        "Financials",
        [
            "Operating expenses of $13.9 million in the quarter",
            "Cash of $64 million and a runway of 30 months",
            "EBITDA margin of minus 12 percent, improving from minus 19 percent",
        ],
        "We expect EBITDA break-even in the second half of FY2027 if the budget is approved as proposed.",
    )
    slide(
        "Decisions requested from the board",
        [
            "Approve the FY2027 operating budget",
            "Approve a second LiDAR supplier contract of up to $3 million",
        ],
        "The FY2027 budget plans revenue of $96 million and 96 new hires.",
    )
    deck.save(OUT / "Q3 2026 Board Update.pptx")


def budget() -> None:
    wb = openpyxl.Workbook()
    wb.properties.title = "FY2027 Operating Budget"
    money, pct = '"$"#,##0', "0.0%"
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="E8ECF4")

    summary = wb.active
    summary.title = "Summary"
    summary.append(["Metric", "FY2026 forecast", "FY2027 budget"])
    for row in (
        ["Revenue", 68_500_000, 96_000_000],
        ["Gross margin", 0.60, 0.63],
        ["Total operating expenses", 47_900_000, 62_400_000],
        ["EBITDA", -6_800_000, -1_900_000],
        ["Year-end headcount", 300, 382],
    ):
        summary.append(row)
    for r in (2, 4, 5):
        for c in (2, 3):
            summary.cell(r, c).number_format = money
    for c in (2, 3):
        summary.cell(3, c).number_format = pct

    opex = wb.create_sheet("Opex by department")
    opex.append(["Department", "FY2026 forecast", "FY2027 budget", "Change"])
    for name, before, after in (
        ("Engineering", 21_400_000, 27_600_000),
        ("Sales", 8_900_000, 10_600_000),
        ("Marketing", 4_900_000, 6_800_000),
        ("Customer success", 3_100_000, 4_200_000),
        ("Manufacturing operations", 4_600_000, 7_600_000),
        ("General and administrative", 5_000_000, 5_600_000),
    ):
        opex.append([name, before, after, after / before - 1])
    for row in opex.iter_rows(min_row=2):
        row[1].number_format = row[2].number_format = money
        row[3].number_format = pct

    heads = wb.create_sheet("Headcount plan")
    heads.append(["Department", "Current headcount", "Planned hires FY2027", "Year-end FY2027"])
    for name, now, hires in (
        ("Engineering", 132, 48),
        ("Sales", 54, 18),
        ("Marketing", 22, 6),
        ("Customer success", 31, 12),
        ("Manufacturing operations", 29, 8),
        ("General and administrative", 18, 4),
    ):
        heads.append([name, now, hires, now + hires])

    capex = wb.create_sheet("Capex")
    capex.append(["Item", "FY2027 budget", "Notes"])
    for row in (
        ["Pilot robot fleet", 2_100_000, "40 Atlas v2 units for customer pilots"],
        ["Test lab equipment", 800_000, "Cold storage test chamber and load rigs"],
        ["Second LiDAR supplier tooling", 600_000, "Qualification and integration"],
        ["Office expansion, Pune", 450_000, "120 additional seats"],
    ):
        capex.append(row)
    for row in capex.iter_rows(min_row=2):
        row[1].number_format = money

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font, cell.fill = bold, fill
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = max(
                16, max(len(str(c.value or "")) for c in column) + 2
            )
            for cell in column:
                cell.alignment = Alignment(vertical="top")
    wb.save(OUT / "FY2027 Operating Budget.xlsx")


def requirements() -> None:
    d = docx.Document()
    d.core_properties.title = "Atlas v2 Product Requirements"
    d.styles["Normal"].font.size = Pt(11)
    d.add_heading("Atlas v2 Product Requirements", level=0)
    d.add_paragraph("Owner: Priya Nair, Product. Status: approved. Version 1.3, 2 September 2026.")
    d.add_heading("Overview", level=1)
    d.add_paragraph(
        "Atlas v2 is the second generation of the Northwind autonomous mobile robot. It extends Atlas into heavier "
        "loads and cold storage while keeping the same fleet software, so existing customers can mix v1 and v2 "
        "robots on one site."
    )
    d.add_heading("Goals", level=2)
    for line in (
        "Carry heavier totes and cases than Atlas v1 to open the beverage and grocery segments.",
        "Run a full warehouse shift on one charge.",
        "Operate in cold storage down to minus 10 degrees Celsius.",
    ):
        d.add_paragraph(line, style="List Bullet")
    d.add_heading("Personas", level=1)
    for line in (
        "Warehouse operations manager: plans shifts and needs predictable throughput.",
        "Floor associate: works next to the robots and needs them to be safe and easy to stop.",
        "Site IT administrator: connects the fleet to the warehouse management system.",
    ):
        d.add_paragraph(line, style="List Bullet")
    d.add_heading("Functional requirements", level=1)
    table = d.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    header = table.rows[0].cells
    header[0].text, header[1].text, header[2].text = "ID", "Requirement", "Target"
    for rid, req, target in (
        ("FR-1", "Payload", "35 kg continuous, up from 25 kg on Atlas v1"),
        ("FR-2", "Battery life", "10 hours of continuous operation on one charge"),
        ("FR-3", "Fast charging", "80 percent charge in 45 minutes"),
        ("FR-4", "Top speed", "2.0 metres per second in open aisles"),
        ("FR-5", "Operating temperature", "Minus 10 to plus 40 degrees Celsius"),
        ("FR-6", "Navigation", "LiDAR plus stereo vision, no floor markers required"),
    ):
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = rid, req, target
    d.add_heading("Non-functional requirements", level=1)
    for line in (
        "Safety: certified to ISO 3691-4 for driverless industrial trucks.",
        "Reliability: mean time between failures of at least 2,000 operating hours.",
        "Availability: 99.5 percent robot availability during scheduled shifts.",
        "Compatibility: managed by Fleet software 4.2 or later alongside Atlas v1.",
    ):
        d.add_paragraph(line, style="List Bullet")
    d.add_heading("Milestones", level=1)
    for line in (
        "Engineering validation test (EVT): November 2026.",
        "Design validation test (DVT): January 2027.",
        "Production validation test (PVT): February 2027.",
        "General availability: March 2027.",
    ):
        d.add_paragraph(line, style="List Number")
    d.add_heading("Open questions", level=1)
    d.add_paragraph(
        "Whether the cold storage variant needs a heated battery enclosure is still being tested. A decision is due "
        "after the EVT cold chamber results."
    )
    d.save(OUT / "Atlas v2 Product Requirements.docx")


def runbook() -> None:
    (OUT / "Security Incident Response Runbook.md").write_text(
        """# Security Incident Response Runbook

Owner: Dana Whitfield, Chief Information Security Officer. Reviewed every quarter.

## Severity levels

| Severity | Examples | Acknowledge within | Who is paged |
| --- | --- | --- | --- |
| SEV1 | Customer data exposed, fleet-wide outage, robot safety incident | 15 minutes | On-call incident commander through PagerDuty service northwind-sev1, then the CISO |
| SEV2 | Single customer site down, suspected account compromise | 1 hour | Security on-call engineer |
| SEV3 | Phishing report, policy violation without data exposure | Next business day | Security team queue |

For a SEV1, page the on-call incident commander through the PagerDuty service northwind-sev1 and notify the CISO
within 30 minutes. If you cannot reach anyone, call the security hotline at +1 512 555 0142.

## Response steps

1. Detect and report. Anyone can declare an incident in the #security channel.
2. Triage. The incident commander confirms the severity and opens an incident document.
3. Contain. Isolate affected accounts, robots or services. Preserve evidence before changing anything.
4. Eradicate. Remove the cause: revoke credentials, patch, or roll back.
5. Recover. Restore service and watch closely for 24 hours.
6. Learn. Hold a blameless postmortem within 5 business days and track every action item to completion.

## Evidence handling

Take screenshots and export logs before restarting anything. Store evidence in the restricted incident folder and
record who accessed it. Never send evidence over chat or personal email.

## Customer communication

Customer Success sends the first customer update for a SEV1 within 2 hours of declaration, after review by Legal.
Updates follow every 4 hours until the incident is resolved.
""",
        encoding="utf-8",
    )


def faq() -> None:
    (OUT / "Customer Support FAQ.html").write_text(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Atlas Customer Support FAQ</title></head>
<body>
<h1>Atlas Customer Support FAQ</h1>
<p>Answers to the questions our support team hears most often. For urgent problems call the 24/7 line.</p>
<h2>How do I reset an Atlas robot?</h2>
<p>Press and hold the power button on the rear panel for 10 seconds until the status ring turns amber. Wait 30
seconds, then press the button once. The robot restarts, relocalises on the site map and reports back to Fleet within
two minutes.</p>
<h2>What does the warranty cover?</h2>
<p>Atlas robots carry a 24-month warranty on parts and labour from the date of deployment. Batteries are covered for
12 months or 1,500 charge cycles, whichever comes first. Damage from forklifts, water or unapproved modifications is
not covered.</p>
<h2>How do firmware updates work?</h2>
<p>Fleet software installs updates during the maintenance window your site sets, one robot at a time, so throughput
never drops by more than 10 percent during an update.</p>
<h2>How do I contact support?</h2>
<ul>
<li>Support portal: open a ticket at any time; P3 tickets are answered within one business day.</li>
<li>Phone: the 24/7 support line is for P1 incidents such as a stopped fleet.</li>
<li>Email: support@northwind.example for billing and account questions.</li>
</ul>
<h2>Can Atlas work in cold storage?</h2>
<p>Atlas v1 is rated for 0 to 40 degrees Celsius. Atlas v2, available from March 2027, operates down to minus 10
degrees Celsius.</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def pilots() -> None:
    rows = [
        [
            "Site",
            "Region",
            "Start date",
            "Robots",
            "Picks per hour",
            "Pick accuracy",
            "Interventions per 1,000 picks",
            "Status",
        ],
        ["Reno, NV", "US West", "2026-05-04", "24", "412", "99.7%", "1.8", "Completed"],
        ["Dallas, TX", "US South", "2026-05-18", "18", "388", "99.5%", "2.4", "Completed"],
        ["Rotterdam", "Europe", "2026-06-01", "30", "455", "99.8%", "1.2", "Completed"],
        ["Pune", "Asia Pacific", "2026-06-15", "12", "361", "99.4%", "3.1", "Completed"],
        ["Columbus, OH", "US Central", "2026-07-06", "20", "401", "99.6%", "2.0", "In progress"],
        ["Hamburg", "Europe", "2026-08-10", "16", "377", "99.5%", "2.6", "In progress"],
    ]
    with (OUT / "warehouse-pilot-results.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def release_notes() -> None:
    (OUT / "Release notes 4.2.txt").write_text(
        f"""NORTHWIND FLEET SOFTWARE 4.2 RELEASE NOTES

Released {date(2026, 9, 21).isoformat()}. Applies to Atlas v1 robots and to Atlas v2 pilot units.

NEW
- Multi-floor mapping: one site map can now span up to 6 floors connected by lifts.
- Zone speed limits: site administrators can set a lower top speed for any zone, for example near packing stations.
- Shift reports: a summary of picks, interventions and charging time is emailed after every shift.

IMPROVED
- Battery scheduling now staggers charging across the fleet, raising robot utilisation by 18 percent.
- Relocalisation after a reset is about twice as fast.

FIXED
- Robots no longer pause at a reflective floor marking near dock doors.
- The fleet map no longer shows a robot twice after a network reconnect.

KNOWN ISSUES
- On sites with more than 200 robots the shift report can arrive up to 30 minutes late.
""",
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (
        handbook,
        contract,
        board_deck,
        budget,
        requirements,
        runbook,
        faq,
        pilots,
        release_notes,
    ):
        build()
    for path in sorted(OUT.iterdir()):
        print(f"{path.stat().st_size:>8,}  {path.name}")


if __name__ == "__main__":
    main()
