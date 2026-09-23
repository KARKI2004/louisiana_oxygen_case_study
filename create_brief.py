from pathlib import Path
import json
import pandas as pd
import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "Louisiana_Oxygen_Gap_Case_Study.pdf"
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DV-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
audit = json.loads((ROOT / "audit.json").read_text())
summary = pd.read_csv(ROOT / "summary.csv")
six_hour = summary.loc[summary.gap_hours == 6].set_index("method")
doc = SimpleDocTemplate(str(OUT), pagesize=letter, rightMargin=38, leftMargin=38,
                        topMargin=30, bottomMargin=28)
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Title2", parent=styles["Title"], fontName="DV-Bold",
                          fontSize=17, leading=20, textColor=colors.HexColor("#174f3a"),
                          alignment=TA_LEFT, spaceAfter=5))
styles.add(ParagraphStyle(name="Deck", parent=styles["BodyText"], fontName="DV", fontSize=9.2, leading=12,
                          textColor=colors.HexColor("#4b5563"), spaceAfter=8))
styles.add(ParagraphStyle(name="H", parent=styles["Heading2"], fontName="DV-Bold",
                          fontSize=10.5, leading=12, textColor=colors.HexColor("#174f3a"),
                          spaceBefore=4, spaceAfter=3))
styles.add(ParagraphStyle(name="B", parent=styles["BodyText"], fontName="DV", fontSize=8.6, leading=11,
                          spaceAfter=4))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontName="DV", fontSize=7.2, leading=9,
                          textColor=colors.HexColor("#4b5563")))

story = [
    Paragraph("Missing Data and Low-Oxygen Exposure<br/>in Louisiana Coastal Monitoring", styles["Title2"]),
    Paragraph("Independent methods case study using public hourly USGS observations from Wilkinson Bayou, Louisiana", styles["Deck"]),
    Paragraph("Research question", styles["H"]),
    Paragraph("When consecutive oxygen readings are missing, how well do common methods preserve the daily average, daily minimum, and hours below an exploratory 2 mg/L threshold?", styles["B"]),
    Paragraph("Data and design", styles["H"]),
    Paragraph(f"The public record contains {audit['source_rows']:,} rows from June 2022 to October 2023, including {audit['observed_do_rows']:,} oxygen observations. Training precedes July 1, 2023; testing uses {audit['complete_test_days']} complete days in July-October. Identical interior 1-, 3-, and 6-hour gaps retain observed endpoints. Each duration is repeated 20 times per day. Methods are unfilled data, a training median, linear interpolation, and a random forest.", styles["B"]),
    Image(str(ROOT/"method_comparison.png"), width=7.05*inch, height=2.22*inch),
]

data = [["Six-hour gap", "Average MAE", "Minimum MAE", "Low-hours MAE"]]
for method in ["Unfilled", "Training median", "Linear interpolation", "Random forest"]:
    row = six_hour.loc[method]
    data.append([method, f"{row.daily_mean_mae:.3f} mg/L",
                 f"{row.daily_minimum_mae:.3f} mg/L", f"{row.low_hours_mae:.3f} h/day"])
t = Table(data, colWidths=[1.58*inch, 1.38*inch, 1.38*inch, 1.45*inch], rowHeights=18)
t.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#174f3a")),
    ("TEXTCOLOR",(0,0),(-1,0),colors.white),
    ("FONTNAME",(0,0),(-1,0),"DV-Bold"),
    ("FONTNAME",(0,1),(0,-1),"DV-Bold"),
    ("FONTNAME",(1,1),(-1,-1),"DV"),
    ("FONTSIZE",(0,0),(-1,-1),8),
    ("ALIGN",(1,1),(-1,-1),"RIGHT"),
    ("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#c9d2cd")),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f6f4")]),
    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
]))
story += [t, Spacer(1,6), Paragraph("Finding", styles["H"]),
          Paragraph("In this experiment, interpolation best preserved average oxygen and approximate low-oxygen duration. The random forest produced the smallest daily-minimum error and missed fewer low-oxygen days during six-hour gaps, but it was worse on the other summaries. Every method undercounted low-oxygen hours on average. Method choice therefore depends on the research summary being protected.", styles["B"]),
          Paragraph("Practical value", styles["H"]),
          Paragraph("The workflow helps researchers decide whether incomplete days can support a specific analysis and how reconstructed values should be labeled. Applied to approved Lake Maurepas records, it could test the team's actual sensor frequency, outage patterns, and biologically relevant summaries.", styles["B"]),
          Paragraph("Scope", styles["H"]),
          Paragraph("This coastal salt-marsh station is not Lake Maurepas. Low hours count hourly samples below 2 mg/L, not continuous exposure. Unfilled gaps count only observed low readings. Repeated masks are dependent; simulated interior gaps may differ from real failures. Interpolation is retrospective, the model retains other sensor records (existing gaps use training medians), and 2 mg/L is an exploratory threshold rather than a site-specific standard. Results do not establish ecological impact, causation, regulatory compliance, or a safe gap length.", styles["Small"]),
          Spacer(1,5),
          Paragraph("Source: Mize et al. (2025), USGS data release 10.5066/P13GBADQ. Analysis code, trial results, and full methods are included in the project package.", styles["Small"])]
doc.build(story)
print(OUT)
