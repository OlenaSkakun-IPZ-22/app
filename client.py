import streamlit as st
import requests

st.title("Завантаження таблиці та перетворення")

uploaded_file = st.file_uploader("Оберіть файл", type=["xlsx", "csv"])

reverse_column_map = {
    'format': 'Format',
    'year': 'Millésime',
    'name': 'Nom',
    'stock': 'Stock',
    'price_ht': 'Prix HT',
    'state': 'Etat',
    'packaging': 'Caissage',
    'parker': 'Parker',
    'category': 'Catégorie',
    'appellation': 'Appellation'
}

if uploaded_file:
    st.write("Файл вибрано:", uploaded_file.name)

    if st.button("Надіслати файл"):
        with st.spinner("Обробка..."):
            files = {'file': (uploaded_file.name, uploaded_file, uploaded_file.type)}
            response = requests.post("http://localhost:5000/upload", files=files)

            if response.status_code == 200:
                st.success("Файл оброблено")

                data = response.json()

                readable_data = []
                for row in data:
                    readable_row = {reverse_column_map.get(k, k): v for k, v in row.items()}
                    readable_data.append(readable_row)

                # Вивід таблиці
                st.dataframe(readable_data)

            else:
                st.error(f"Помилка: {response.text}")
