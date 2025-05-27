from flask import Flask, request, jsonify
import pandas as pd
import os
import re
import logging
from datetime import datetime
import csv
import io
import traceback 

os.makedirs("logs", exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = Flask(__name__)

column_patterns = {
    r"\bwine\b|\bproduct\b|\bdescription\b|\bnom\b": "wine_name",
    r"\bproducer\b|\borigin\b|\bdomaine\b|\bchateau\b": "producer",
    r"\b(appellation|denomination)\b": "denomination",
    r"\b(region)\b": "region",
    r"\b(country)\b": "country",
    r"\b(color|couleur)\b": "color",
    r"\b(stock|qty|quantit|avail)\b": "stock",
    r"\b(format|size|bottle|cl|volume)\b": "bottle_size",
    r"\b(price|prix|prix ht|chf|eur|usd|gbp)\b": "price",
    r"\b(millésime|year|vintage)\b": "year"
}

def normalize_columns(columns):
    result = []
    for col in columns:
        col_str = str(col).lower().strip()
        col_str = col_str.replace('\n', ' ').replace('\r', '').replace('  ', ' ') 
        matched = False
        for pattern, replacement in column_patterns.items():
            if re.search(pattern, col_str):
                col_str = replacement
                matched = True
                break
        result.append(col_str if matched else str(col).strip()) 
    return result

def make_columns_unique(cols):
    seen = {}
    result = []
    for col in cols:
        col_name = str(col) 
        if col_name not in seen:
            seen[col_name] = 1
            result.append(col_name)
        else:
            seen[col_name] += 1
            result.append(f"{col_name}_{seen[col_name]}")
    return result

def find_best_header_row(df_raw, filename=""):
    header_keywords = ['name', 'region', 'price', 'vintage', 'quantity', 'type', 'country',
                       'article', 'prix', 'quantité', 'description', 'producer', 'year', 'stock', 'format']
    best_match_count = 0
    best_header_idx = -1

    if df_raw.empty:
        logging.warning(f"{filename}: df_raw is empty in find_best_header_row.")
        return 0 

    for idx, row in df_raw.head(20).iterrows():
        try:
            match_count = sum(
                1 for cell in row if isinstance(cell, str) and any(k in cell.lower() for k in header_keywords)
            )
            if match_count > best_match_count:
                best_match_count = match_count
                best_header_idx = idx
        except Exception as e:
            logging.warning(f"{filename}: Error processing row {idx} in find_best_header_row: {e}")
            continue

    if best_match_count >= 2: 
        logging.info(f"{filename}: Best header row found at index {best_header_idx} with {best_match_count} keyword matches.")
        return best_header_idx
    try:
        fallback_df = df_raw.dropna(how='all')
        if not fallback_df.empty:
            fallback_idx = fallback_df.index[0]
            logging.info(f"{filename}: No strong keyword match for header. Falling back to first non-empty row at index {fallback_idx}.")
            return fallback_idx
    except IndexError:
        logging.warning(f"{filename}: Could not find any non-empty row for fallback header.")
    
    logging.info(f"{filename}: Defaulting header to row 0 as no better option found.")
    return 0


def try_read_csv_with_encoding(file, filename, encodings=["utf-8", "ISO-8859-1", "cp1252", "utf-16-be", "utf-16", "utf-16-le"]):
    common_delimiters = [',', ';', '\t', '|']
    
    for enc in encodings:
        logging.info(f"{filename}: Attempting to read with encoding: {enc}")
        try:
            file.seek(0)
            sample_bytes = file.read(4096) 
            if not sample_bytes:
                logging.warning(f"{filename}: File is empty or unreadable (encoding {enc}).")
                continue
            
            sample_content = ""
            try:
                sample_content = sample_bytes.decode(enc)
            except UnicodeDecodeError:
                logging.warning(f"{filename}: UnicodeDecodeError with {enc} on sample. Trying errors='ignore'.")
                sample_content = sample_bytes.decode(enc, errors='ignore')
            
            delimiters_to_try = []
            try:
                dialect = csv.Sniffer().sniff(sample_content)
                detected_delimiter = dialect.delimiter
                logging.info(f"{filename}: Sniffer detected delimiter '{detected_delimiter}' for encoding {enc}.")
                delimiters_to_try.append(detected_delimiter)
            except csv.Error as sniff_error:
                logging.warning(f"{filename}: CSV Sniffer failed for encoding {enc}: {sniff_error}. Will try common delimiters.")
            for d in common_delimiters:
                if d not in delimiters_to_try:
                    delimiters_to_try.append(d)

            for delim in delimiters_to_try:
                logging.info(f"{filename}: Trying delimiter '{delim}' with encoding {enc}.")
                try:
                    file.seek(0) 
                    full_content_bytes = file.read()
                    full_content_str = ""
                    try:
                        full_content_str = full_content_bytes.decode(enc)
                    except UnicodeDecodeError:
                        full_content_str = full_content_bytes.decode(enc, errors='ignore')

                    buffer = io.StringIO(full_content_str)
                    df = pd.read_csv(buffer, header=None, delimiter=delim, engine="python", on_bad_lines='skip', skipinitialspace=True, quotechar='"')
                    
                    # Check if DataFrame is plausible
                    if not df.empty and df.dropna(how='all').shape[0] > 0:
                        if df.shape[0] > 1 and df.shape[1] > 1:
                             logging.info(f"{filename}: Successfully read CSV with encoding '{enc}' and delimiter '{delim}'. Shape: {df.shape}")
                             return df
                        else:
                            logging.info(f"{filename}: Read with '{enc}','{delim}' resulted in single cell or empty data. Shape: {df.shape}. Trying next.")
                    else:
                        logging.info(f"{filename}: Read with '{enc}','{delim}' resulted in empty or all-NaN DataFrame. Shape: {df.shape}. Trying next.")
                except Exception as e:
                    logging.warning(f"{filename}: Error reading with delimiter '{delim}' and encoding {enc}: {e}")
                    continue 
        except Exception as e:
            logging.warning(f"{filename}: General error with encoding {enc}: {e}")
            continue 
            
    logging.error(f"{filename}: Failed to read CSV with all attempted encodings and delimiters.")
    return pd.DataFrame([{"error": f"Не вдалося прочитати CSV '{filename}' навіть з декількома кодуваннями та роздільниками."}])


def process_file_universal(file, filename):
    logging.info(f"--- Processing file: {filename} ---")
    ext = os.path.splitext(filename)[1].lower()
    df_raw = None
    try:
        if ext == ".csv":
            df_raw = try_read_csv_with_encoding(file, filename)
        elif ext in [".xls", ".xlsx"]:
            file.seek(0)
            df_raw = pd.read_excel(file, header=None)
        else:
            return [{"error": f"{filename}: Unsupported file type '{ext}'"}]

        if isinstance(df_raw, pd.DataFrame) and "error" in df_raw.columns and df_raw.shape[0] == 1:
             logging.error(f"{filename}: try_read_csv_with_encoding returned an error: {df_raw.iloc[0]['error']}")
             return df_raw.to_dict(orient='records')

        if df_raw is None or df_raw.empty:
            logging.error(f"{filename}: File is empty or could not be read into DataFrame.")
            return [{"error": f"{filename}: файл порожній або не вдалося прочитати"}]

        logging.info(f"{filename}: Initial raw DataFrame shape: {df_raw.shape}")

        header_idx = find_best_header_row(df_raw, filename)
        if header_idx >= len(df_raw):
            logging.error(f"{filename}: Calculated header_idx {header_idx} is out of bounds for df_raw length {len(df_raw)}.")
            return [{"error": f"{filename}: індекс заголовка ({header_idx}) виходить за межі таблиці ({len(df_raw)})"}]
        
        logging.info(f"{filename}: Identified header row index: {header_idx}")

        raw_header_series = df_raw.iloc[header_idx]
        raw_header = [str(c).strip() for c in raw_header_series.fillna('').astype(str)]
        logging.info(f"{filename}: Raw header extracted: {raw_header}")
        
        df = df_raw.iloc[header_idx + 1:].copy() 
        df.columns = raw_header 
        df.reset_index(drop=True, inplace=True)

        logging.info(f"{filename}: DataFrame shape after taking data below header: {df.shape}")

        df.dropna(axis=1, how='all', inplace=True)
        logging.info(f"{filename}: DataFrame shape after dropping all-NaN columns: {df.shape}")

        df.columns = normalize_columns(df.columns)
        df.columns = make_columns_unique(df.columns)
        logging.info(f"{filename}: Normalized columns: {df.columns.tolist()}")
        logging.info(f"{filename}: Shape of df before final dropna of rows: {df.shape}")

        df.dropna(axis=0, how='all', inplace=True)
        logging.info(f"{filename}: DataFrame shape after dropping all-NaN rows: {df.shape}")


        if df.empty:
            logging.error(f"{filename}: DataFrame is empty after processing.")
            return [{"error": f"{filename}: таблиця порожня після обробки"}]

        try:
            for col in df.select_dtypes(include=['object']): 
                if df[col].str.contains(',', na=False).any() and df[col].str.match(r'^\s*[\d,.]+\s*$', na=False).any() :
                    df[col] = df[col].str.replace(',', '.', regex=False)
        except Exception as e:
            logging.warning(f"{filename}: Error during global comma to dot replacement: {e}")

        for col_name in df.columns:
            if re.search(r'price(_\d+)?|regular|ht|ttc|\£|\€|\$', str(col_name).lower()):
                try:
                    logging.info(f"{filename}: Processing price column: {col_name}")
                    if col_name in df.columns:
                        series = df[col_name]
                        if series.ndim == 1:
                        
                            cleaned_series = series.astype(str).str.replace(r'[^\d.-]', '', regex=True)
                            cleaned_series = cleaned_series.replace(r'^\.$|^\-$|^\s*$', pd.NA, regex=True) 
                            df[col_name] = pd.to_numeric(cleaned_series, errors='coerce')
                            logging.info(f"{filename}: Price column {col_name} converted to numeric. NaNs: {df[col_name].isnull().sum()}")
                        else:
                            logging.warning(f"{filename}: Column '{col_name}' is not a Series (ndim={series.ndim}). Skipping price conversion.")
                    else:
                        logging.warning(f"{filename}: Price column '{col_name}' not found after column operations. Skipping.")
                except Exception as e:
                    logging.error(f"{filename}: Error processing price column '{col_name}': {e}\n{traceback.format_exc()}")


        def convert_to_json_safe(val):
            if pd.isna(val):
                return None
            return val
        allowed_filters = set(column_patterns.values())
        for param in request.args:
            if param in df.columns and param in allowed_filters:
                value = request.args.get(param).strip().lower()
                if value:
                    df = df[df[param].astype(str).str.lower().str.contains(value, na=False)]


        data = df.to_dict(orient='records')
        safe_data = [{k: convert_to_json_safe(v) for k, v in row.items()} for row in data]

        logging.info(f"{filename}: Successfully processed. Returning {len(safe_data)} records.")
        return safe_data

    except Exception as e:
        tb_str = traceback.format_exc()
        logging.error(f"\n--- Critical Error: {datetime.now()} ---\nFile: {filename}\nError: {str(e)}\nTraceback:\n{tb_str}")
        return [{"error": f"{filename}: КРИТИЧНА ПОМИЛКА ОБРОБКИ - {str(e)}"}]


@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'Файли не надіслані'}), 400

    uploaded_files = request.files.getlist('files')
    if not uploaded_files or not uploaded_files[0].filename :
        return jsonify({'error': 'Список файлів порожній або файл без імені.'}), 400
        
    result = {}
    for file_storage in uploaded_files:
        if file_storage and file_storage.filename:
            filename = file_storage.filename
            result[filename] = process_file_universal(file_storage, filename)
        else:
            logging.warning("Received an empty file or file without a name in the list.")


    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)

