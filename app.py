from flask import Flask, request, jsonify
import pandas as pd
from dataclasses import dataclass

app = Flask(__name__)

# Структура об'єкта Wine
@dataclass
class Wine:
    format: str
    year: str
    name: str
    stock: int
    price_ht: float
    state: str
    packaging: str
    parker: str
    category: str
    appellation: str

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:

        df_raw = pd.read_excel(file, header=None)

        max_cols = df_raw.apply(lambda x: x.count(), axis=1).idxmax()
        df = pd.read_excel(file, header=max_cols)

        column_map = {
            'Format': 'format',
            'Millésime': 'year',
            'Nom': 'name',
            'Stock': 'stock',
            'Prix HT': 'price_ht',
            'Etat': 'state',
            'Caissage': 'packaging',
            'Parker': 'parker',
            'Catégorie': 'category',
            'Appellation': 'appellation'
        }
        df = df.rename(columns=lambda col: column_map.get(str(col).strip(), str(col).strip()))

        # Фільтрація: лише ті, де є назва вина (або інші ключові)
        df = df[df['name'].notna() & df['price_ht'].notna()]

        wine_fields = Wine.__annotations__.keys()
        filtered_data = []
        for row in df.to_dict(orient="records"):
            filtered_row = {k: row[k] for k in wine_fields if k in row}
            filtered_data.append(Wine(**filtered_row))

        return jsonify([wine.__dict__ for wine in filtered_data])

    except Exception as e:
        return jsonify({'помилка': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
