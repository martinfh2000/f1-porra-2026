import streamlit as st
from cryptography.fernet import Fernet

def get_encryption_key():
    return st.secrets["encryption_key"]["value"].encode()

def encriptar(texto):
    f = Fernet(get_encryption_key())
    return f.encrypt(texto.encode()).decode()

def desencriptar(texto_encriptado):
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(texto_encriptado.encode()).decode()
    except:
        return "Error/Corrupto"