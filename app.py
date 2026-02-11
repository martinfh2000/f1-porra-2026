import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from cryptography.fernet import Fernet
from datetime import datetime
import pytz
import time
import requests

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="F1 2026 Manager", page_icon="🏎️", layout="wide")

# Lista de Pilotos Oficial (Para los desplegables de la porra)
PILOTOS_2026 = [
    "Verstappen", "Hadjar", "Leclerc", "Hamilton", "Norris", "Piastri", 
    "Alonso", "Stroll", "Sainz", "Albon", "Russell", "Antonelli", 
    "Bearman", "Ocon", "Gasly", "Colapinto", "Lawson", "Lindblad", 
    "Checo", "Bottas", "Hulkenberg", "Bortoleto"
]

# --- GESTIÓN DE SESIÓN ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = None
if 'rol_usuario' not in st.session_state:
    st.session_state.rol_usuario = None
if 'mis_ligas' not in st.session_state:
    st.session_state.mis_ligas = []
if 'mi_liga' not in st.session_state:
    st.session_state.mi_liga = ""

# --- CONEXIONES GOOGLE SHEETS ---
def conectar_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open("Base de Datos F1 2026")

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

# --- FUNCIONES API F1 (OPENF1) ---
@st.cache_data(ttl=600)
def obtener_lista_sesiones_finalizadas():
    """Devuelve una lista de diccionarios con las sesiones ya terminadas."""
    try:
        # NOTA: Cambia 'year=2023' por 'year=2026' cuando empiece la temporada real.
        # Usamos 2023/2024 para que veas datos ahora mismo.
        url = "https://api.openf1.org/v1/sessions?year=2025" 
        resp = requests.get(url)
        if resp.status_code != 200: return []
        
        sessions = resp.json()
        now = datetime.now(pytz.utc)
        finalizadas = []
        
        for s in sessions:
            try:
                end_time = datetime.fromisoformat(s['date_end']).replace(tzinfo=pytz.utc)
                if end_time < now:
                    label = f"{s['country_name']} - {s['session_name']}"
                    finalizadas.append({
                        "label": label,
                        "key": s['session_key'],
                        "type": s['session_type'],
                        "date": end_time
                    })
            except: pass
            
        # Ordenamos: La más reciente primero
        finalizadas.sort(key=lambda x: x['date'], reverse=True)
        return finalizadas
    except: return []

@st.cache_data(ttl=600)
def obtener_detalles_sesion(session_key, session_type):
    """Busca tiempos y mapea nombres de pilotos."""
    try:
        # 1. Mapa de Pilotos (Dorsal -> Nombre)
        url_drivers = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
        drivers_resp = requests.get(url_drivers)
        mapa_pilotos = {}
        if drivers_resp.status_code == 200:
            for d in drivers_resp.json():
                if d['driver_number']:
                    mapa_pilotos[d['driver_number']] = d['last_name'].upper()

        # 2. Obtener Resultados
        resultados = []
        
        if session_type == 'Race':
            url_pos = f"https://api.openf1.org/v1/position?session_key={session_key}"
            pos_data = requests.get(url_pos).json()
            df_pos = pd.DataFrame(pos_data)
            
            if not df_pos.empty:
                df_pos['date'] = pd.to_datetime(df_pos['date'])
                # Última posición conocida de cada piloto
                final_positions = df_pos.sort_values('date').drop_duplicates(subset=['driver_number'], keep='last')
                final_positions = final_positions.sort_values('position')
                
                for _, row in final_positions.iterrows():
                    num = row['driver_number']
                    nombre = mapa_pilotos.get(num, f"#{num}")
                    resultados.append({"Pos": row['position'], "Piloto": nombre, "Dato": "Final"})
        else:
            # Libres y Clasificación (Mejor Vuelta)
            url_laps = f"https://api.openf1.org/v1/laps?session_key={session_key}"
            laps_data = requests.get(url_laps).json()
            df_laps = pd.DataFrame(laps_data)
            
            if not df_laps.empty:
                df_laps = df_laps.dropna(subset=['lap_duration'])
                best_laps = df_laps.loc[df_laps.groupby('driver_number')['lap_duration'].idxmin()]
                best_laps = best_laps.sort_values('lap_duration')
                
                pos_counter = 1
                for _, row in best_laps.iterrows():
                    num = row['driver_number']
                    nombre = mapa_pilotos.get(num, f"#{num}")
                    tiempo = f"{row['lap_duration']:.3f}"
                    resultados.append({"Pos": pos_counter, "Piloto": nombre, "Dato": tiempo})
                    pos_counter += 1
                    
        return resultados
    except Exception as e:
        return []

# --- FUNCIONES DE LECTURA DE BASE DE DATOS (CACHÉ) ---
@st.cache_data(ttl=300)
def obtener_datos_maestros():
    """Descarga Calendario y Usuarios (5 min caché)"""
    try:
        sh = conectar_sheet()
        ws_cal = sh.worksheet("calendario")
        df_cal = pd.DataFrame(ws_cal.get_all_records())
        
        madrid_tz = pytz.timezone('Europe/Madrid')
        def parse_date(date_str):
            try:
                dt = datetime.strptime(str(date_str), "%d/%m/%Y %H:%M:%S")
                return madrid_tz.localize(dt)
            except:
                try:
                    dt = datetime.strptime(str(date_str), "%d/%m/%Y %H:%M")
                    return madrid_tz.localize(dt)
                except: return None
        df_cal['fecha_dt'] = df_cal['fecha_limite'].apply(parse_date)

        ws_users = sh.worksheet("usuarios")
        df_users = pd.DataFrame(ws_users.get_all_records())
        if not df_users.empty:
            df_users['usuario'] = df_users['usuario'].astype(str)
            df_users['password'] = df_users['password'].astype(str)
            if 'liga_privada' not in df_users.columns: df_users['liga_privada'] = ""
        
        return df_cal, df_users
    except: return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60) 
def obtener_datos_resultados():
    """Descarga Resultados y Apuestas (1 min caché)"""
    try:
        sh = conectar_sheet()
        df_res = pd.DataFrame(sh.worksheet("resultados_oficiales").get_all_records())
        df_bets_c = pd.DataFrame(sh.worksheet("pronosticos_carrera").get_all_records())
        df_bets_m = pd.DataFrame(sh.worksheet("pronosticos_mundial").get_all_records())
        return df_res, df_bets_c, df_bets_m
    except: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- FUNCIONES DE ESCRITURA (SIN CACHÉ) ---

def registrar_usuario_nuevo(user, password, liga_input):
    nombre_liga = liga_input.strip().upper() if liga_input else ""
    try:
        _, df_users = obtener_datos_maestros() 
        if not df_users.empty:
            usuarios_existentes = df_users['usuario'].astype(str).tolist()
            if user in usuarios_existentes:
                return False, "⚠️ Ese nombre de usuario ya existe."
        
        sh = conectar_sheet()
        ws = sh.worksheet("usuarios")
        ws.append_row([user, password, "pendiente", nombre_liga])
        obtener_datos_maestros.clear()
        return True, "✅ Solicitud enviada. Espera aprobación del Admin."
    except Exception as e: return False, f"Error: {e}"

def unirse_a_nueva_liga(usuario, nueva_liga):
    nombre_clean = nueva_liga.strip().upper()
    if not nombre_clean: return False, "Nombre vacío"
    try:
        sh = conectar_sheet()
        ws = sh.worksheet("usuarios")
        cell = ws.find(usuario)
        ligas_actuales_str = ws.cell(cell.row, 4).value
        if not ligas_actuales_str: ligas_actuales_str = ""
        lista_actual = [l.strip().upper() for l in ligas_actuales_str.split(",") if l.strip()]
        if nombre_clean in lista_actual: return False, "Ya estás en esa liga."
        lista_actual.append(nombre_clean)
        ws.update_cell(cell.row, 4, ", ".join(lista_actual))
        obtener_datos_maestros.clear() 
        return True, "¡Unido con éxito!"
    except Exception as e: return False, f"Error: {e}"

def aprobar_usuario(usuario_a_aprobar):
    try:
        sh = conectar_sheet()
        ws = sh.worksheet("usuarios")
        cell = ws.find(usuario_a_aprobar)
        ws.update_cell(cell.row, 3, "user")
        obtener_datos_maestros.clear()
        return True
    except: return False

def borrar_usuario(usuario_a_borrar):
    try:
        sh = conectar_sheet()
        ws = sh.worksheet("usuarios")
        cell = ws.find(usuario_a_borrar)
        ws.delete_rows(cell.row)
        obtener_datos_maestros.clear()
        return True
    except: return False

def guardar_apuesta(usuario, id_evento, cadena_encriptada, tipo_apuesta):
    try:
        sh = conectar_sheet()
        if tipo_apuesta == "mundial":
            ws = sh.worksheet("pronosticos_mundial")
        else:
            ws = sh.worksheet("pronosticos_carrera")
            
        data = ws.get_all_values()
        fila_encontrada = -1
        
        for i in range(1, len(data)):
            if data[i][0] == usuario and data[i][1] == id_evento:
                fila_encontrada = i + 1 
                break
        
        if fila_encontrada > 0:
            ws.update_cell(fila_encontrada, 3, str(datetime.now()))
            ws.update_cell(fila_encontrada, 4, cadena_encriptada)
        else:
            ws.append_row([usuario, id_evento, str(datetime.now()), cadena_encriptada])
            
        obtener_datos_resultados.clear()
        return True
    except Exception as e:
        print(f"Error guardando: {e}")
        return False

def guardar_resultado_oficial(fila_datos):
    try:
        sh = conectar_sheet()
        ws = sh.worksheet("resultados_oficiales")
        ws.append_row(fila_datos)
        obtener_datos_resultados.clear()
        return True
    except: return False

# --- LÓGICA DE NEGOCIO ---

def verificar_login(user, password):
    _, df_users = obtener_datos_maestros()
    try:
        usuario_encontrado = df_users[df_users['usuario'] == user]
        if not usuario_encontrado.empty:
            password_real = usuario_encontrado.iloc[0]['password']
            if str(password) == password_real:
                rol = usuario_encontrado.iloc[0]['rol']
                if rol == "pendiente": return False, "pendiente", []
                ligas_str = str(usuario_encontrado.iloc[0]['liga_privada'])
                lista_ligas = [l.strip().upper() for l in ligas_str.split(",") if l.strip()]
                return True, rol, lista_ligas
        return False, None, []
    except: return False, None, []

def verificar_estado_evento(id_evento, df_calendario):
    idx_evento = df_calendario.index[df_calendario['id_evento'] == id_evento].tolist()
    if not idx_evento: return 'ERROR'
    idx = idx_evento[0]
    evento_actual = df_calendario.iloc[idx]
    fecha_limite = evento_actual['fecha_dt']
    ahora = datetime.now(pytz.timezone('Europe/Madrid'))
    if ahora > fecha_limite: return 'CERRADO'
    if idx == 0: return 'ABIERTO'
    if id_evento == 'gp_01': evento_previo = df_calendario.iloc[0]
    else: evento_previo = df_calendario.iloc[idx - 1]
    fecha_limite_previo = evento_previo['fecha_dt']
    if ahora < fecha_limite_previo: return 'PENDIENTE'
    return 'ABIERTO'

def calcular_puntos_carrera(prediccion_lista, resultado_lista):
    puntos = 0
    for i, piloto in enumerate(prediccion_lista):
        if i >= 10: break
        try: pos_real = resultado_lista.index(piloto)
        except: pos_real = -1
        if pos_real == i: puntos += 4
        elif i < 3 and pos_real < 3 and pos_real != -1: puntos += 2
        elif pos_real < 10 and pos_real != -1: puntos += 1
    return puntos

def calcular_puntos_mundial(prediccion_lista, resultado_lista):
    puntos = 0
    for i, piloto in enumerate(prediccion_lista):
        try:
            pos_real = resultado_lista.index(piloto)
            diferencia = abs(i - pos_real)
            if diferencia == 0: puntos += 30
            elif diferencia == 1: puntos += 10
        except: pass
    return puntos

# ==========================================
#              INTERFAZ DE ACCESO
# ==========================================
if not st.session_state.logged_in:
    st.title("🏎️ F1 2026 Manager")
    
    tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "📝 Registrarse"])
    
    with tab_login:
        l_user = st.text_input("Usuario", key="l_u")
        l_pass = st.text_input("Contraseña", type="password", key="l_p")
        if st.button("Entrar", type="primary"):
            es_valido, rol, ligas = verificar_login(l_user, l_pass)
            if es_valido:
                st.session_state.logged_in = True
                st.session_state.usuario_actual = l_user
                st.session_state.rol_usuario = rol
                st.session_state.mis_ligas = ligas
                st.success(f"Bienvenido {l_user}")
                time.sleep(0.5)
                st.rerun()
            elif rol == "pendiente":
                st.warning("✋ Tu cuenta está **PENDIENTE DE APROBACIÓN**.")
            else:
                st.error("Datos incorrectos.")
    
    with tab_registro:
        st.markdown("### Nueva Cuenta")
        r_user = st.text_input("Usuario (Nick)", key="r_u")
        r_pass = st.text_input("Contraseña", type="password", key="r_p")
        st.write("---")
        r_liga = st.text_input("Liga Inicial (Opcional)", key="r_l")
        
        if r_liga:
            nombre_limpio = r_liga.strip().upper()
            df_cal, df_users = obtener_datos_maestros()
            todas_ligas = []
            if not df_users.empty and 'liga_privada' in df_users.columns:
                 for item in df_users['liga_privada'].astype(str):
                    partes = item.split(",")
                    for p in partes:
                        limpia = p.strip().upper()
                        if limpia: todas_ligas.append(limpia)
            todas_ligas = list(set(todas_ligas))

            if nombre_limpio in todas_ligas: st.info(f"👥 Te unirás a: **{nombre_limpio}**")
            else: st.success(f"✨ Fundarás: **{nombre_limpio}**")

        if st.button("Solicitar Registro"):
            if r_user and r_pass:
                ok, msg = registrar_usuario_nuevo(r_user, r_pass, r_liga)
                if ok: st.info(msg)
                else: st.error(msg)
            else: st.warning("Faltan datos.")

# ==========================================
#              APP PRINCIPAL
# ==========================================
else:
    df_cal, df_users = obtener_datos_maestros()
    if df_cal.empty:
        st.error("Error crítico: No se pudo conectar con la base de datos. Recarga la página.")
        st.stop()

    with st.sidebar:
        st.markdown(f"## 👤 {st.session_state.usuario_actual}")
        if st.session_state.rol_usuario == "admin":
            st.warning("🛠️ ADMIN MODE")
            
        st.write("---")
        st.markdown("### 🏆 Mis Ligas")
        if st.session_state.mis_ligas:
            for liga in st.session_state.mis_ligas:
                st.markdown(f"- **{liga}**")
        else: st.caption("Solo Global")
        
        with st.expander("➕ Unirse / Crear Liga"):
            nueva_liga_input = st.text_input("Nombre Liga")
            if st.button("Unirse"):
                if nueva_liga_input:
                    ok, msg = unirse_a_nueva_liga(st.session_state.usuario_actual, nueva_liga_input)
                    if ok:
                        st.success(msg)
                        st.rerun() 
                    else: st.error(msg)
        
        st.write("---")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.session_state.usuario_actual = None
            st.rerun()

    st.title("🏆 Porra F1 2026")

    tabs_list = ["📝 Hacer Porra", "📊 Clasificación", "👀 Ver Apuestas", "📡 Live Center", "📜 Normas"]
    if st.session_state.rol_usuario == "admin":
        tabs_list.append("⚙️ Resultados")
        tabs_list.append("👥 Usuarios")
    
    tabs = st.tabs(tabs_list)

    # --- TAB 1: HACER PORRA ---
    with tabs[0]:
        st.subheader("Tu predicción")
        lista_eventos = df_cal['nombre_mostrar'].tolist()
        idx_defecto = 0
        for i, row in df_cal.iterrows():
            if verificar_estado_evento(row['id_evento'], df_cal) == "ABIERTO":
                idx_defecto = i; break
        
        evento_seleccionado_nombre = st.selectbox("Gran Premio:", lista_eventos, index=idx_defecto)
        row_evento = df_cal[df_cal['nombre_mostrar'] == evento_seleccionado_nombre].iloc[0]
        id_evento = row_evento['id_evento']
        estado = verificar_estado_evento(id_evento, df_cal)
        
        # --- CARGAR APUESTA ANTERIOR ---
        _, df_bets_c, df_bets_m = obtener_datos_resultados()
        mi_apuesta_actual = []
        es_mundial = "mundial" in id_evento
        
        if es_mundial:
            if not df_bets_m.empty:
                mi_fila = df_bets_m[(df_bets_m['usuario'] == st.session_state.usuario_actual) & (df_bets_m['tipo'] == id_evento)]
                if not mi_fila.empty:
                    datos = mi_fila.iloc[-1]['datos_encriptados']
                    mi_apuesta_actual = desencriptar(datos).split(",")
        else:
            if not df_bets_c.empty:
                mi_fila = df_bets_c[(df_bets_c['usuario'] == st.session_state.usuario_actual) & (df_bets_c['carrera'] == id_evento)]
                if not mi_fila.empty:
                    datos = mi_fila.iloc[-1]['datos_encriptados']
                    mi_apuesta_actual = desencriptar(datos).split(",")

        if mi_apuesta_actual:
            with st.expander("✅ Ya tienes una apuesta guardada (Click para ver)", expanded=True):
                if es_mundial:
                    df_mi_apuesta = pd.DataFrame(mi_apuesta_actual, columns=["Piloto"])
                    df_mi_apuesta.index += 1
                    st.dataframe(df_mi_apuesta, height=300)
                else:
                    st.info(f"**Top 10 guardado:** {', '.join(mi_apuesta_actual)}")
                st.caption("Usa el formulario de abajo para enviar una nueva si quieres cambiarla.")
        
        if estado == 'CERRADO': st.warning(f"🔒 CERRADO (Límite: {row_evento['fecha_limite']})")
        elif estado == 'PENDIENTE': st.info("⏳ PENDIENTE")
        else:
            st.success(f"🟢 ABIERTO hasta: {row_evento['fecha_limite']}")
            if es_mundial:
                st.write("Ordena los 22 pilotos.")
                seleccion = st.multiselect("Parrilla:", PILOTOS_2026, default=None)
                
                if len(seleccion) == 22:
                    if st.button("Enviar Predicción Mundial"):
                        cadena = ",".join(seleccion)
                        encriptado = encriptar(cadena)
                        ok = guardar_apuesta(st.session_state.usuario_actual, id_evento, encriptado, "mundial")
                        if ok: st.balloons(); st.success("✅ ¡Guardado!")
                        else: st.error("Error al guardar")
                else: st.caption(f"{len(seleccion)}/22 seleccionados")
            else:
                st.write("Top 10 Carrera")
                cols = st.columns(2)
                seleccion_carrera = []
                for i in range(10):
                    with cols[i % 2]:
                        val = st.selectbox(f"P{i+1}", ["-"] + PILOTOS_2026, index=0, key=f"p{i}")
                        seleccion_carrera.append(val)
                if "-" not in seleccion_carrera and len(set(seleccion_carrera)) == 10:
                    if st.button("Enviar Porra"):
                        cadena = ",".join(seleccion_carrera)
                        encriptado = encriptar(cadena)
                        ok = guardar_apuesta(st.session_state.usuario_actual, id_evento, encriptado, "carrera")
                        if ok: st.balloons(); st.success("✅ ¡Guardado!")
                        else: st.error("Error al guardar")
                else: st.warning("Completa los 10 sin repetir.")

    # --- TAB 2: CLASIFICACIÓN ---
    with tabs[1]:
        st.header("Clasificaciones")
        if st.button("🔄 Refrescar"):
            obtener_datos_resultados.clear()
            st.rerun()
        
        df_res, df_bets_c, df_bets_m = obtener_datos_resultados()
        ranking_global = {}
        
        if not df_res.empty:
            for index, row_res in df_res.iterrows():
                carrera_id = row_res['carrera']
                if not row_res['p1']: continue
                res_oficial = [row_res[f'p{i}'] for i in range(1, 23) if f'p{i}' in row_res and row_res[f'p{i}']]
                es_mundial = "mundial" in carrera_id
                
                if es_mundial and not df_bets_m.empty: bets = df_bets_m[df_bets_m['tipo'] == carrera_id]
                elif not es_mundial and not df_bets_c.empty: bets = df_bets_c[df_bets_c['carrera'] == carrera_id]
                else: bets = pd.DataFrame()
                
                apuestas_del_gp = {} 
                res_gp = []
                if not bets.empty:
                    for idx, bet in bets.iterrows():
                        user = bet['usuario']
                        estado_ev = verificar_estado_evento(carrera_id, df_cal)
                        if estado_ev == "CERRADO":
                            pred_str = desencriptar(bet['datos_encriptados'])
                            if pred_str != "Error/Corrupto":
                                pred_list = pred_str.split(",")
                                apuestas_del_gp[user] = pred_list
                                pts = calcular_puntos_mundial(pred_list, res_oficial) if es_mundial else calcular_puntos_carrera(pred_list, res_oficial)
                                ranking_global[user] = ranking_global.get(user, 0) + pts
                                res_gp.append({"Usuario": user, "Puntos": pts})
                        else: res_gp.append({"Usuario": user, "Puntos": "⏳"})

                with st.expander(f"🏁 Detalles: {carrera_id}"):
                    st.dataframe(pd.DataFrame(res_gp), use_container_width=True)

        st.write("---")
        opciones = ["GLOBAL"] + st.session_state.mis_ligas
        idx_defecto = 0
        if st.session_state.mis_ligas:
             primera_liga = st.session_state.mis_ligas[0]
             if primera_liga in opciones: idx_defecto = opciones.index(primera_liga)
        opcion_liga = st.selectbox("🏆 Filtrar Ranking por Liga:", opciones, index=idx_defecto)
        
        if ranking_global:
            df_rank = pd.DataFrame(list(ranking_global.items()), columns=["Piloto", "Puntos"])
            if opcion_liga != "GLOBAL":
                usuarios_liga = []
                for idx, u_row in df_users.iterrows():
                    sus_ligas = [l.strip().upper() for l in str(u_row['liga_privada']).split(",")]
                    if opcion_liga in sus_ligas: usuarios_liga.append(u_row['usuario'])
                df_rank = df_rank[df_rank['Piloto'].isin(usuarios_liga)]
            df_rank = df_rank.sort_values("Puntos", ascending=False).reset_index(drop=True)
            col1, col2 = st.columns([3, 1])
            with col1: st.bar_chart(df_rank.set_index("Piloto"))
            with col2: st.dataframe(df_rank, use_container_width=True)
        else: st.info("Sin datos aún.")

    # --- TAB 3: VER APUESTAS (Con seguridad de errores) ---
    with tabs[2]:
        st.header("🕵️ Espiar Rivales")
        st.info("Aquí podrás ver las apuestas detalladas de otros jugadores una vez cerrado el evento.")

        lista_eventos = df_cal['nombre_mostrar'].tolist()
        evento_spy = st.selectbox("Selecciona Gran Premio:", lista_eventos, key="spy_event")
        
        row_evento = df_cal[df_cal['nombre_mostrar'] == evento_spy].iloc[0]
        id_evento = row_evento['id_evento']
        estado_evento = verificar_estado_evento(id_evento, df_cal)

        if estado_evento != "CERRADO":
            st.warning(f"🔒 Las apuestas para **{evento_spy}** son secretas hasta que cierre el evento.")
            st.caption(f"Cierre previsto: {row_evento['fecha_limite']}")
        else:
            _, df_bets_c, df_bets_m = obtener_datos_resultados()
            es_mundial = "mundial" in id_evento
            
            if es_mundial:
                if df_bets_m.empty: df_filtrado = pd.DataFrame(columns=['usuario'])
                else: df_filtrado = df_bets_m[df_bets_m['tipo'] == id_evento]
            else:
                if df_bets_c.empty: df_filtrado = pd.DataFrame(columns=['usuario'])
                else: df_filtrado = df_bets_c[df_bets_c['carrera'] == id_evento]
            
            if not df_filtrado.empty:
                usuarios_con_apuesta = df_filtrado['usuario'].unique().tolist()
                usuarios_con_apuesta.sort()
            else: usuarios_con_apuesta = []

            if not usuarios_con_apuesta:
                st.warning("Nadie ha apostado en este evento todavía.")
            else:
                usuario_a_ver = st.selectbox("🔍 Selecciona un usuario:", ["- Seleccionar -"] + usuarios_con_apuesta)

                if usuario_a_ver != "- Seleccionar -":
                    st.divider()
                    st.markdown(f"#### 📑 Apuesta de: **{usuario_a_ver}**")
                    
                    fila_user = df_filtrado[df_filtrado['usuario'] == usuario_a_ver].iloc[-1]
                    
                    # Recuperación segura de FECHA
                    fecha_apuesta = "Desconocida"
                    cols_fecha = [c for c in fila_user.index if 'fecha' in str(c).lower() or 'date' in str(c).lower()]
                    if cols_fecha: fecha_apuesta = fila_user[cols_fecha[0]]
                    elif 'fecha' in fila_user: fecha_apuesta = fila_user['fecha']
                    
                    # Recuperación segura de ENCRIPTADO
                    texto_encriptado = fila_user.get('datos_encriptados', '')
                    if not texto_encriptado: texto_encriptado = fila_user.iloc[-1] # Fallback por posición

                    texto_plano = desencriptar(texto_encriptado)
                    
                    if texto_plano == "Error/Corrupto":
                        st.error("Error al desencriptar la apuesta.")
                    else:
                        lista_pilotos = texto_plano.split(",")
                        col_dat, col_tab = st.columns([1, 3])
                        with col_dat:
                            st.caption("📅 Fecha envío:")
                            st.write(fecha_apuesta)
                            st.caption("📍 Evento:")
                            st.write(evento_spy)
                        with col_tab:
                            df_show = pd.DataFrame(lista_pilotos, columns=["Piloto"])
                            df_show.index += 1
                            st.dataframe(df_show, use_container_width=True, height=400)

    # --- TAB 4: LIVE CENTER (Nueva) ---
    with tabs[3]:
        st.header("📡 Live Center F1")
        st.info("Consulta resultados de sesiones anteriores (Libres, Clasificación, etc) usando la API OpenF1.")
        
        if st.button("🔄 Buscar nuevas sesiones"):
            obtener_lista_sesiones_finalizadas.clear()
            st.rerun()

        lista_sesiones = obtener_lista_sesiones_finalizadas()
        
        if not lista_sesiones:
            st.warning("No hay sesiones finalizadas disponibles en la API.")
        else:
            opciones_nombres = [s['label'] for s in lista_sesiones]
            seleccion = st.selectbox("📅 Selecciona Sesión:", opciones_nombres, index=0)
            sesion_elegida = next(s for s in lista_sesiones if s['label'] == seleccion)
            
            st.divider()
            st.subheader(f"Resultados: {sesion_elegida['label']}")
            
            with st.spinner("Descargando telemetría..."):
                datos = obtener_detalles_sesion(sesion_elegida['key'], sesion_elegida['type'])
            
            if datos:
                df_show = pd.DataFrame(datos)
                st.dataframe(
                    df_show.set_index("Pos"), 
                    use_container_width=True,
                    height=500
                )
            else:
                st.warning("Sesión encontrada, pero no hay datos de tiempos disponibles.")

    # --- TAB 5: NORMAS ---
    with tabs[4]:
        st.header("📜 Reglamento Oficial")
        st.markdown("""
        ### 1. Formato
        * **Confidencialidad:** Las porras son ciegas hasta el cierre.
        * **Plazos:** Cierre automático antes de la sesión oficial.
        
        ### 2. Puntuación
        **Carrera (Top 10):**
        * **4 pts**: Acierto exacto.
        * **2 pts**: Podio desordenado.
        * **1 pt**: Top 10 desordenado.
        
        **Mundial (22 Pilotos):**
        * **30 pts**: Posición exacta.
        * **10 pts**: Posición +/- 1.
        """)

    # --- TABS ADMIN ---
    if st.session_state.rol_usuario == "admin":
        with tabs[5]:
            st.markdown("### ⚙️ Panel Resultados")
            ev_cargar = st.selectbox("Evento:", df_cal['id_evento'].tolist())
            res_admin = st.multiselect("Resultado Oficial:", PILOTOS_2026)
            if st.button("Guardar Resultado"):
                fila = [ev_cargar] + res_admin
                while len(fila) < 23: fila.append("")
                fila.append("TRUE")
                ok = guardar_resultado_oficial(fila)
                if ok: st.success("Guardado")
                else: st.error("Error al guardar")

        with tabs[6]:
            st.markdown("### 👥 Control de Acceso")
            if st.button("🔄 Cargar Pendientes"):
                obtener_datos_maestros.clear()
                st.rerun()
            pendientes = df_users[df_users['rol'] == 'pendiente']
            if pendientes.empty: st.success("✅ No hay solicitudes.")
            else:
                for index, row in pendientes.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.markdown(f"**{row['usuario']}**")
                    c2.caption(f"Ligas: {row['liga_privada']}")
                    if c3.button("✅", key=f"ok_{row['usuario']}"):
                        aprobar_usuario(row['usuario']); st.rerun()
                    if c4.button("❌", key=f"del_{row['usuario']}"):

                        borrar_usuario(row['usuario']); st.rerun()
