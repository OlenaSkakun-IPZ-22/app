import streamlit as st
import requests
import pandas as pd
from io import BytesIO
st.set_page_config(page_title="Обробка Excel/CSV", layout="wide")
st.title("Завантаження і конвертація таблиць")

uploaded_files = st.file_uploader(
    "Оберіть один або кілька файлів (.xlsx, .csv)",
    type=["xlsx", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button(" Надіслати файли на сервер"):
        with st.spinner("Обробка файлів..."):
            files = [("files", (f.name, f, f.type)) for f in uploaded_files]
            try:
                response = requests.post("http://localhost:5000/upload", files=files)
                if response.status_code == 200:
                    results = response.json()
                    for filename, data in results.items():
                        st.subheader(f"{filename}")
                        if isinstance(data, list) and all(isinstance(row, dict) for row in data):
                            df = pd.DataFrame(data)
                            if df.empty:
                                st.warning("Таблиця порожня або має лише пусті значення.")
                            else:
                                st.dataframe(df)

                                towrite = BytesIO()
                                df.to_excel(towrite, index=False, sheet_name="Sheet1")
                                towrite.seek(0)
                                st.download_button(
                                    label="⬇ Завантажити таблицю Excel",
                                    data=towrite,
                                    file_name=f"{filename}_cleaned.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                        else:
                            st.error(" Помилка при обробці:")
                            st.json(data)
                else:
                    st.error(f"Сервер повернув код {response.status_code}")
            except requests.exceptions.ConnectionError:
                st.error(" Не вдалося підключитись до сервера. Перевір, чи запущено `app.py`")
