import streamlit as st
import requests

st.title("Завантаження таблиці та перетворення")

uploaded_file = st.file_uploader("Оберіть файл", type=["xlsx", "csv"])

if uploaded_file:
    st.write("Файл вибрано:", uploaded_file.name)

    if st.button("Надіслати файл"):
        with st.spinner("Обробка..."):
            files = {'file': (uploaded_file.name, uploaded_file, uploaded_file.type)}
            response = requests.post("http://localhost:5000/upload", files=files)
            if response.status_code == 200:
                st.success("Файл оброблено")
                st.json(response.json())
            else:
                st.error(f"Помилка: {response.text}")
