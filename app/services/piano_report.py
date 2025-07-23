from fpdf import FPDF
from io import BytesIO
from typing import Optional, List
import os

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

    def add_images_with_labels(self, image_paths: List[str], photo_labels: List[dict]):
        self.set_font("Arial", "B", 13)
        self.cell(0, 10, "Photo Analysis", ln=True)
        self.ln(3)

        img_per_row = 2
        img_width = 90
        img_height = 60
        margin = 10
        y_start = self.get_y()

        for i, (img_path, labels) in enumerate(zip(image_paths, photo_labels)):
            x = self.l_margin + (i % img_per_row) * (img_width + margin)
            y = self.get_y() if i % img_per_row == 0 else y_start

            if os.path.exists(img_path):
                self.image(img_path, x=x, y=y, w=img_width, h=img_height)
            else:
                self.set_xy(x, y)
                self.cell(img_width, img_height, "Image not found", border=1, align="C")

            self.set_xy(x, y + img_height + 2)
            self.set_font("Arial", "", 10)
            label_text = ", ".join([f"{k}: {v}" for k, v in labels.items()])
            self.multi_cell(img_width, 5, label_text, align="L")

            if i % img_per_row == img_per_row - 1:
                self.ln(img_height + 20)
                y_start = self.get_y()

async def generate_piano_summary_pdf(piano: dict, image_paths: List[str], photo_labels: List[dict]) -> BytesIO:
    pdf = PianoPDF()
    pdf.add_page()

    pdf.add_key_value("Brand", piano.get("brand"))
    pdf.add_key_value("Serial Number", piano.get("serial_number"))
    pdf.add_key_value("Year Estimated", str(piano.get("year_estimated")))
    pdf.add_key_value("Category", piano.get("category"))
    pdf.add_key_value("Type", piano.get("type"))
    pdf.add_key_value("Size", f"{piano.get('size_cm')} cm" if piano.get("size_cm") else None)
    pdf.add_key_value("Notes", str(piano.get("nb_notes")))

    model = piano.get("model_hypothesis", {})
    if model:
        pdf.ln(5)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, "Model Hypothesis", ln=True)
        pdf.add_key_value("Name", model.get("name"))
        pdf.add_key_value("Variant", model.get("variant"))
        desc = model.get("description")
        if desc:
            pdf.set_font("Arial", "", 12)
            pdf.multi_cell(0, 10, desc)

    if image_paths and photo_labels:
        pdf.add_page()
        pdf.add_images_with_labels(image_paths, photo_labels)

    # ✅ Génère les bytes du PDF
    pdf_bytes = pdf.output(dest='S').encode('latin-1')  # fpdf retourne du str (latin-1)
    buffer = BytesIO(pdf_bytes)
    buffer.seek(0)
    return buffer

