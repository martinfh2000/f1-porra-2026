import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

def conectar_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds).open("Base de Datos F1 2026")

@st.cache_data(ttl=300)
def obtener_datos_maestros():
    try:
        sh = conectar_sheet()
        # Calendario
        df_cal = pd.DataFrame(sh.worksheet("calendario").get_all_records())
        tz = pytz.timezone('Europe/Madrid')
        def parse(d):
            try: return tz.localize(datetime.strptime(str(d), "%d/%m/%Y %H:%M:%S"))
            except: 
                try: return tz.localize(datetime.strptime(str(d), "%d/%m/%Y %H:%M"))
                except: return None
        df_cal['fecha_dt'] = df_cal['fecha_limite'].apply(parse)
        
        # Usuarios
        df_u = pd.DataFrame(sh.worksheet("usuarios").get_all_records())
        if not df_u.empty: 
            df_u['usuario'] = df_u['usuario'].astype(str)
            if 'liga_privada' not in df_u.columns: df_u['liga_privada'] = ""
            
        # Pilotos
        try: df_p = pd.DataFrame(sh.worksheet("pilotos").get_all_records())
        except: return df_cal, df_u, pd.DataFrame() # Fallback vacío
        
        return df_cal, df_u, df_p
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60)
def obtener_datos_resultados():
    try:
        sh = conectar_sheet()
        return (pd.DataFrame(sh.worksheet("resultados_oficiales").get_all_records()),
                pd.DataFrame(sh.worksheet("pronosticos_carrera").get_all_records()),
                pd.DataFrame(sh.worksheet("pronosticos_mundial").get_all_records()))
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- Funciones de Escritura (Sin Caché) ---
def guardar_apuesta(u, ide, enc, tipo):
    try:
        sh = conectar_sheet()
        ws = sh.worksheet("pronosticos_mundial" if tipo=="mundial" else "pronosticos_carrera")
        dat = ws.get_all_values()
        f = -1
        for i in range(1, len(dat)):
            if dat[i][0] == u and dat[i][1] == ide: f=i+1; break
        if f>0: ws.update_cell(f, 3, str(datetime.now())); ws.update_cell(f, 4, enc)
        else: ws.append_row([u, ide, str(datetime.now()), enc])
        obtener_datos_resultados.clear()
        return True
    except: return False

def guardar_resultado(fila):
    try:
        sh = conectar_sheet(); sh.worksheet("resultados_oficiales").append_row(fila)
        obtener_datos_resultados.clear(); return True
    except: return False

def registrar_usuario_nuevo(u, p, l):
    try:
        _, df_u, _ = obtener_datos_maestros()
        if not df_u.empty and u in df_u['usuario'].astype(str).tolist(): return False, "Usuario existe"
        conectar_sheet().worksheet("usuarios").append_row([u, p, "pendiente", l.upper() if l else ""])
        obtener_datos_maestros.clear(); return True, "Enviado"
    except: return False, "Error"

def unirse_liga(u, l):
    try:
        sh = conectar_sheet(); ws = sh.worksheet("usuarios"); c = ws.find(u)
        curr = ws.cell(c.row, 4).value or ""; ls = [x.strip().upper() for x in curr.split(",") if x.strip()]
        if l.upper() in ls: return False, "Ya estás dentro"
        ls.append(l.upper()); ws.update_cell(c.row, 4, ", ".join(ls))
        obtener_datos_maestros.clear(); return True, "Unido"
    except: return False, "Error"

def aprobar_usuario(u):
    try:
        sh = conectar_sheet(); ws = sh.worksheet("usuarios")
        ws.update_cell(ws.find(u).row, 3, "user"); obtener_datos_maestros.clear(); return True
    except: return False

def borrar_usuario(u):
    try:
        sh = conectar_sheet(); ws = sh.worksheet("usuarios")
        ws.delete_rows(ws.find(u).row); obtener_datos_maestros.clear(); return True
    except: return False