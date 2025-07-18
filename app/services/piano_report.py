from fpdf import FPDF
from io import BytesIO
from typing import Optional

class PianoPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Piano Summary Report", border=False, ln=True, align="C")
        self.ln(5)

    def add_key_value(self, label: str, value: Optional[str]):
        if value:
            self.set_font("Arial", "B", 12)
            self.cell(40, 10, f"{label}:", ln=False)
            self.set_font("Arial", "", 12)
            self.cell(0, 10, value, ln=True)

async def generate_piano_summary_pdf(piano: dict) -> BytesIO:
    pdf = PianoPDF()
    pdf.add_page()

    pdf.add_key_value("Brand", piano.get("brand"))
    pdf.add_key_value("Distributor", piano.get("distributor"))
    pdf.add_key_value("Serial Number", piano.get("serial_number"))
    pdf.add_key_value("Year Estimated", str(piano.get("year_estimated")))
    pdf.add_key_value("Category", piano.get("category"))
    pdf.add_key_value("Type", piano.get("type"))
    pdf.add_key_value("Height / Size", f"{piano.get('size_cm')} cm")
    pdf.add_key_value("Number of Notes", str(piano.get("nb_notes")))

    # Modèle hypothétique
    model = piano.get("model_hypothesis", {})
    if model:
        pdf.ln(5)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, "Model Hypothesis", ln=True)
        pdf.add_key_value("Name", model.get("name"))
        pdf.add_key_value("Variant", model.get("variant"))
        pdf.set_font("Arial", "", 12)
        desc = model.get("description")
        if desc:
            pdf.multi_cell(0, 10, desc)

        c
