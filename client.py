import streamlit as st
import requests
import pandas as pd
from io import BytesIO
import re 
import os

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
searchable_column_categories = sorted(list(set(column_patterns.values())))

st.set_page_config(page_title="Глобальний пошук у таблицях", layout="wide")
st.title(" Завантаження та глобальний пошук у таблицях")

uploaded_files = st.file_uploader(
    "Оберіть один або кілька файлів (.xlsx, .csv)",
    type=["xlsx", "csv"],
    accept_multiple_files=True
)

if "tables" not in st.session_state:
    st.session_state.tables = {}
if "last_uploaded_filenames" not in st.session_state:
    st.session_state.last_uploaded_filenames = []

if uploaded_files:
    current_filenames = sorted([f.name for f in uploaded_files])
    if current_filenames != st.session_state.last_uploaded_filenames:
        if st.button("📤 Надіслати файли на сервер", key="upload_button"):
            with st.spinner("Обробка файлів..."):
                files_for_request = [("files", (f.name, f.getvalue(), f.type)) for f in uploaded_files]
                try:
                    response = requests.post("http://localhost:5000/upload", files=files_for_request)
                    
                    if response.status_code == 200:
                        results = response.json()
                        st.session_state.tables.clear() 
                        processed_files_count = 0
                        for filename, data_or_error in results.items():
                            if isinstance(data_or_error, list) and data_or_error and isinstance(data_or_error[0], dict) and "error" not in data_or_error[0]:
                                df = pd.DataFrame(data_or_error)
                                if not df.empty:
                                    st.session_state.tables[filename] = df
                                    processed_files_count +=1
                                else:
                                    st.warning(f"Файл '{filename}' оброблено, але результат - порожня таблиця.")
                            elif isinstance(data_or_error, list) and data_or_error and "error" in data_or_error[0]:
                                st.error(f"Помилка обробки файлу '{filename}': {data_or_error[0]['error']}")
                            else:
                                st.error(f"Неочікувана відповідь для файлу '{filename}': {data_or_error}")
                        
                        if processed_files_count > 0:
                            st.success(f"Successfully processed {processed_files_count} file(s).")
                        st.session_state.last_uploaded_filenames = current_filenames
                        st.rerun() 
                    else:
                        st.error(f" Сервер повернув код {response.status_code}: {response.text}")
                except requests.exceptions.ConnectionError:
                    st.error(" Не вдалося підключитись до сервера. Переконайтеся, що Flask app (`app.py`) запущено.")
                except Exception as e:
                    st.error(f"Сталася помилка під час надсилання файлів: {e}")
    elif not st.session_state.tables and not uploaded_files:
         st.session_state.last_uploaded_filenames = []

if st.session_state.tables:
    st.markdown("---")
    st.subheader("Завантажені та оброблені таблиці:")
    for filename, df in st.session_state.tables.items():
        with st.expander(f" {filename} (рядків: {len(df)})", expanded=False):
            st.dataframe(df, use_container_width=True, height=300)
            
            towrite = BytesIO()
            df.to_excel(towrite, index=False, engine='openpyxl')
            towrite.seek(0)
            st.download_button(
                label=f"⬇ Завантажити {filename} (Excel)",
                data=towrite,
                file_name=f"{os.path.splitext(filename)[0]}_processed.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_{filename}"
            )
    st.markdown("---")
else:
    st.info("Ще не завантажено жодного файлу або файли не були оброблені успішно.")


st.markdown("## Глобальний пошук за категоріями")

search_term = st.text_input(
    "Введіть ключове слово для пошуку:",
    placeholder="Наприклад: Bordeaux або 2015 або Chardonnay"
)

selected_categories = st.multiselect(
    "Оберіть категорії для пошуку (за замовчуванням - всі доступні):",
    options=searchable_column_categories,
    default=[], 
    help="Пошук буде виконано в колонках, що відповідають обраним категоріям (напр., 'wine_name', 'region')."
)

if st.button(" Шукати", key="global_search_button"):
    if search_term and st.session_state.tables:
        all_matches_dfs = []
        search_term_lower = search_term.strip().lower()
        
        categories_to_search = selected_categories if selected_categories else searchable_column_categories

        if not categories_to_search: 
            st.warning("Немає доступних категорій для пошуку.")
        else:
            for filename, df in st.session_state.tables.items():
                row_mask = pd.Series([False] * len(df), index=df.index)

                for original_col_name in df.columns:
                    base_normalized_name = re.sub(r'_\d+$', '', original_col_name)
                    
                    if base_normalized_name in categories_to_search:
                        try:
                            col_as_str = df[original_col_name].astype(str).str.lower()
                            match_in_col = col_as_str.str.contains(re.escape(search_term_lower), na=False)
                            row_mask = row_mask | match_in_col 
                        except Exception as e:
                            st.warning(f"Помилка пошуку в колонці '{original_col_name}' файлу '{filename}': {e}")
                
                current_file_matches = df[row_mask]

                if not current_file_matches.empty:
                    matches_with_filename = current_file_matches.copy()
                    matches_with_filename.insert(0, " Джерело файлу", filename) 
                    all_matches_dfs.append(matches_with_filename)

            if all_matches_dfs:
                final_result_df = pd.concat(all_matches_dfs, ignore_index=True)
                st.success(f" Знайдено {len(final_result_df)} збігів у {len(all_matches_dfs)} таблицях за вибраними категоріями:")
                st.dataframe(final_result_df, use_container_width=True, height=500)

                towrite_results = BytesIO()
                final_result_df.to_excel(towrite_results, index=False, engine='openpyxl')
                towrite_results.seek(0)
                st.download_button(
                    label="⬇ Завантажити результати пошуку (Excel)",
                    data=towrite_results,
                    file_name="global_search_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_search_results"
                )
            else:
                st.info(f" Нічого не знайдено для '{search_term}' у вибраних категоріях.")
    elif not search_term:
        st.warning("Будь ласка, введіть ключове слово для пошуку.")
    elif not st.session_state.tables:
        st.warning("Будь ласка, спочатку завантажте та обробіть файли.")

