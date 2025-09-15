# utils/piano_utils.py

def normalize_piano_data(piano: dict) -> dict:
    fields = [
        "brand", "model", "serial_number", "category", "type",
        "size_cm", "nb_notes", "year_estimated",
        "model_dont_know", "size_dont_know", "serial_dont_know"
    ]
    return {k: v for k, v in piano.items() if k in fields}
