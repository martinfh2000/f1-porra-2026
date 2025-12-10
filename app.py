import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from cryptography.fernet import Fernet
from datetime import datetime
import pytz
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="F1 2026 Manager", page_icon="🏎️", layout="wide")

# Lista de Pilotos
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

# --- CONEXIONES ---
def conectar_sheet():
    """Conexión base sin caché para escrituras"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
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

# --- FUNCIONES DE LECTURA OPTIMIZADAS (CACHÉ) ---
# Aquí está la MAGIA. ttl=300 significa "recuerda esto 300 segundos (5 min)"
# Así no molestamos a Google cada vez que haces clic.

@st.cache_data(ttl=300)
def obtener_datos_maestros():
    """Descarga Calendario y Usuarios de una sola vez"""
    try:
        sh = conectar_sheet()
        
        # 1. Calendario
        ws_cal = sh.worksheet("calendario")
        df_cal = pd.DataFrame(ws_cal.get_all_records())
        
        # Procesar fechas del calendario aquí para no hacerlo en cada clic
        madrid_tz = pytz.timezone('Europe/Madrid')
        def parse_date(date_str):
            try:
                dt = datetime.strptime(str(date_str), "%d/%m/%Y %H:%M:%S")
                return madrid_tz.localize(dt)
            except:
                try:
                    dt = datetime.strptime(str(date_str), "%d/%m/%Y %H:%M")
                    return madrid_tz.localize(dt)
                except:
                    return None
        df_cal['fecha_dt'] = df_cal['fecha_limite'].apply(parse_date)

        # 2. Usuarios
        ws_users = sh.worksheet("usuarios")
        df_users = pd.DataFrame(ws_users.get_all_records())
        # Asegurar tipos de datos
        if not df_users.empty:
            df_users['usuario'] = df_users['usuario'].astype(str)
            df_users['password'] = df_users['password'].astype(str)
            if 'liga_privada' not in df_users.columns: df_users['liga_privada'] = ""
        
        return df_cal, df_users
    except Exception as e:
        # Si falla Google, devolvemos DataFrames vacíos para que no pete la app
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=60) # Resultados y apuestas se actualizan cada 1 minuto
def obtener_datos_resultados():
    """Descarga Resultados y Apuestas"""
    try:
        sh = conectar_sheet()
        df_res = pd.DataFrame(sh.worksheet("resultados_oficiales").get_all_records())
        df_bets_c = pd.DataFrame(sh.worksheet("pronosticos_carrera").get_all_records())
        df_bets_m = pd.DataFrame(sh.worksheet("pronosticos_mundial").get_all_records())
        return df_res, df_bets_c, df_bets_m
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- FUNCIONES DE ESCRITURA (NO TIENEN CACHÉ) ---
# Estas siguen llamando a Google directo porque necesitamos guardar YA.

def registrar_usuario_nuevo(user, password, liga_input):
    nombre_liga = liga_input.strip().upper() if liga_input else ""
    try:
        # Para verificar duplicados usamos la caché (rápido)
        _, df_users = obtener_datos_maestros() 
        
        if not df_users.empty:
            usuarios_existentes = df_users['usuario'].astype(str).tolist()
            if user in usuarios_existentes:
                return False, "⚠️ Ese nombre de usuario ya existe."
        
        # Para escribir usamos conexión directa
        sh = conectar_sheet()
        ws = sh.worksheet("usuarios")
        ws.append_row([user, password, "pendiente", nombre_liga])
        
        # Limpiamos caché para que el nuevo usuario aparezca si recargas
        obtener_datos_maestros.clear()
        return True, "✅ Solicitud enviada. Espera aprobación del Admin."
        
    except Exception as e:
        return False, f"Error del sistema: {e}"

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
        if nombre_clean in lista_actual:
            return False, "Ya estás en esa liga."
        lista_actual.append(nombre_clean)
        nuevo_valor = ", ".join(lista_actual)
        ws.update_cell(cell.row, 4, nuevo_valor)
        
        obtener_datos_maestros.clear() # Limpiar caché
        return True, "¡Unido con éxito!"
    except Exception as e:
        return False, f"Error: {e}"

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
            
        # 1. Buscamos si el usuario ya tiene una fila para este evento
        # Traemos todos los datos para buscar en memoria (ahorra llamadas a la API)
        data = ws.get_all_values()
        
        fila_encontrada = -1
        
        # Empezamos en 1 para saltar encabezados (index 0 en python es fila 1 en excel)
        # data[i][0] es usuario, data[i][1] es id_evento
        for i in range(1, len(data)):
            if data[i][0] == usuario and data[i][1] == id_evento:
                fila_encontrada = i + 1 # +1 porque Excel cuenta desde 1
                break
        
        if fila_encontrada > 0:
            # --- MODO ACTUALIZAR (UPDATE) ---
            # Columna 3: Timestamp, Columna 4: Datos
            ws.update_cell(fila_encontrada, 3, str(datetime.now()))
            ws.update_cell(fila_encontrada, 4, cadena_encriptada)
        else:
            # --- MODO NUEVO (INSERT) ---
            ws.append_row([usuario, id_evento, str(datetime.now()), cadena_encriptada])
            
        obtener_datos_resultados.clear() # Limpiar caché para que se vea el cambio
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
    # Usamos datos cacheados para login rápido
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
        col_liga1, col_liga2 = st.columns([3, 1])
        with col_liga1:
            r_liga = st.text_input("Liga Inicial (Opcional)", key="r_l")
        
        if r_liga:
            nombre_limpio = r_liga.strip().upper()
            # Usamos caché para comprobar ligas existentes
            df_cal, df_users = obtener_datos_maestros()
            
            # Obtener ligas únicas del caché
            todas_ligas = []
            if not df_users.empty and 'liga_privada' in df_users.columns:
                 for item in df_users['liga_privada'].astype(str):
                    partes = item.split(",")
                    for p in partes:
                        limpia = p.strip().upper()
                        if limpia: todas_ligas.append(limpia)
            todas_ligas = list(set(todas_ligas))

            if nombre_limpio in todas_ligas:
                st.info(f"👥 Te unirás a: **{nombre_limpio}**")
            else:
                st.success(f"✨ Fundarás: **{nombre_limpio}**")

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
    # Cargar datos maestros (Calendario y usuarios) de la caché
    df_cal, df_users = obtener_datos_maestros()
    if df_cal.empty:
        st.error("Error crítico: No se pudo conectar con la base de datos. Intenta recargar.")
        st.stop()

    # --- BARRA LATERAL ---
    with st.sidebar:
        st.markdown(f"## 👤 {st.session_state.usuario_actual}")
        if st.session_state.rol_usuario == "admin":
            st.warning("🛠️ ADMIN MODE")
            
        st.write("---")
        st.markdown("### 🏆 Mis Ligas")
        if st.session_state.mis_ligas:
            for liga in st.session_state.mis_ligas:
                st.markdown(f"- **{liga}**")
        else:
            st.caption("Solo Global")
            
        with st.expander("➕ Unirse / Crear Liga"):
            nueva_liga_input = st.text_input("Nombre Liga")
            if st.button("Unirse"):
                if nueva_liga_input:
                    ok, msg = unirse_a_nueva_liga(st.session_state.usuario_actual, nueva_liga_input)
                    if ok:
                        st.success(msg)
                        # Actualizar caché y recargar
                        st.rerun() 
                    else:
                        st.error(msg)
        
        st.write("---")
        if st.button("Cerrar Sesión"):
            st.session_state.logged_in = False
            st.session_state.usuario_actual = None
            st.rerun()

    st.title("🏆 Porra F1 2026")

    # --- DEFINICIÓN DE PESTAÑAS ---
    tabs_list = ["📝 Hacer Porra", "📊 Clasificación", "📜 Normas"]
    if st.session_state.rol_usuario == "admin":
        tabs_list.append("⚙️ Resultados")
        tabs_list.append("👥 Usuarios")
    
    tabs = st.tabs(tabs_list)

    # --- TAB 1: HACER PORRA ---
    with tabs[0]:
        st.subheader("Tu predicción")
        lista_eventos = df_cal['nombre_mostrar'].tolist()
        
        # Intentar preseleccionar el primer evento ABIERTO o PENDIENTE
        idx_defecto = 0
        for i, row in df_cal.iterrows():
            estado_temp = verificar_estado_evento(row['id_evento'], df_cal)
            if estado_temp == "ABIERTO":
                idx_defecto = i
                break
        
        evento_seleccionado_nombre = st.selectbox("Gran Premio:", lista_eventos, index=idx_defecto)
        row_evento = df_cal[df_cal['nombre_mostrar'] == evento_seleccionado_nombre].iloc[0]
        id_evento = row_evento['id_evento']
        estado = verificar_estado_evento(id_evento, df_cal)
        
        if estado == 'CERRADO': st.warning(f"🔒 CERRADO (Límite: {row_evento['fecha_limite']})")
        elif estado == 'PENDIENTE': st.info("⏳ PENDIENTE")
        else:
            st.success(f"🟢 ABIERTO hasta: {row_evento['fecha_limite']}")
            if "mundial" in id_evento:
                st.write("Ordena los 22 pilotos.")
                seleccion = st.multiselect("Parrilla:", PILOTOS_2026, default=None)
                if len(seleccion) == 22:
                    if st.button("Enviar Predicción Mundial"):
                        cadena = ",".join(seleccion)
                        encriptado = encriptar(cadena)
                        ok = guardar_apuesta(st.session_state.usuario_actual, id_evento, encriptado, "mundial")
                        if ok: 
                            st.balloons(); st.success("✅ ¡Guardado!")
                        else: st.error("Error al guardar")
                else: st.caption(f"{len(seleccion)}/22 seleccionados")
            else:
                st.write("Top 10 Carrera")
                cols = st.columns(2)
                seleccion_carrera = []
                for i in range(10):
                    with cols[i % 2]:
                        val = st.selectbox(f"P{i+1}", ["-"] + PILOTOS_2026, key=f"p{i}")
                        seleccion_carrera.append(val)
                if "-" not in seleccion_carrera and len(set(seleccion_carrera)) == 10:
                    if st.button("Enviar Porra"):
                        cadena = ",".join(seleccion_carrera)
                        encriptado = encriptar(cadena)
                        ok = guardar_apuesta(st.session_state.usuario_actual, id_evento, encriptado, "carrera")
                        if ok: 
                            st.balloons(); st.success("✅ ¡Guardado!")
                        else: st.error("Error al guardar")
                else: st.warning("Completa los 10 sin repetir.")

    # --- TAB 2: CLASIFICACIÓN ---
    with tabs[1]:
        st.header("Clasificaciones")
        if st.button("🔄 Refrescar"):
            obtener_datos_resultados.clear() # Forzar limpieza de caché
            st.rerun()
        
        # Cargar datos de resultados y apuestas (Con caché de 1 min)
        df_res, df_bets_c, df_bets_m = obtener_datos_resultados()
        
        ranking_global = {}
        
        if not df_res.empty:
            for index, row_res in df_res.iterrows():
                carrera_id = row_res['carrera']
                if not row_res['p1']: continue
                
                res_oficial = [row_res[f'p{i}'] for i in range(1, 23) if f'p{i}' in row_res and row_res[f'p{i}']]
                es_mundial = "mundial" in carrera_id
                
                if es_mundial and not df_bets_m.empty:
                    bets = df_bets_m[df_bets_m['tipo'] == carrera_id]
                elif not es_mundial and not df_bets_c.empty:
                    bets = df_bets_c[df_bets_c['carrera'] == carrera_id]
                else:
                    bets = pd.DataFrame()
                
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
                        else:
                            res_gp.append({"Usuario": user, "Puntos": "⏳"})

                with st.expander(f"🏁 Detalles: {carrera_id}"):
                    st.dataframe(pd.DataFrame(res_gp), use_container_width=True)
                    if apuestas_del_gp:
                        st.caption("🕵️ Ver apuesta completa de:")
                        usuarios_en_gp = list(apuestas_del_gp.keys())
                        usuario_a_espiar = st.selectbox("Seleccionar:", ["-"] + usuarios_en_gp, key=f"spy_{carrera_id}")
                        if usuario_a_espiar != "-":
                            st.markdown(f"**Apuesta de {usuario_a_espiar}**")
                            lista_apostada = apuestas_del_gp[usuario_a_espiar]
                            data_comp = []
                            rango = 22 if es_mundial else 10
                            for i in range(rango):
                                p_apostado = lista_apostada[i] if i < len(lista_apostada) else "-"
                                p_real = res_oficial[i] if i < len(res_oficial) else "-"
                                icon = "❌"
                                if p_apostado == p_real: icon = "✅"
                                elif p_apostado in res_oficial: icon = "⚠️"
                                data_comp.append({"Pos": i+1, "Apuesta": p_apostado, "Real": p_real, "Estado": icon})
                            st.dataframe(pd.DataFrame(data_comp), use_container_width=True)

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

    # --- TAB 3: NORMAS ---
    with tabs[2]:
        st.header("📜 Reglamento Oficial")
        st.markdown("""
        ### 1. Formato
        * **Confidencialidad:** Las porras son ciegas hasta el cierre.
        * **Plazos:** Cierre automático antes de la sesión oficial. Puedes repetir cada una cuantas veces quieras, solo se guarda la ultima apuesta.
        
        ### 2. Puntuación
        **Carrera (Top 10):**
        * **4 pts**: Acierto exacto.
        * **2 pts**: Podio desordenado.
        * **1 pt**: Top 10 desordenado.
        
        **Mundial (22 Pilotos):**
        * **30 pts**: Posición exacta.
        * **10 pts**: Posición +/- 1.
        """)

    # --- TAB 4: ADMIN RESULTADOS ---
    if st.session_state.rol_usuario == "admin":
        with tabs[3]:
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

    # --- TAB 5: ADMIN USUARIOS ---
    if st.session_state.rol_usuario == "admin":
        with tabs[4]:
            st.markdown("### 👥 Control de Acceso")
            if st.button("🔄 Cargar Pendientes"):
                obtener_datos_maestros.clear()
                st.rerun()
            
            # Usar df_users que ya cargamos arriba
            pendientes = df_users[df_users['rol'] == 'pendiente']
            if pendientes.empty:
                st.success("✅ No hay solicitudes.")
            else:
                for index, row in pendientes.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
                    c1.markdown(f"**{row['usuario']}**")
                    c2.caption(f"Ligas: {row['liga_privada']}")
                    if c3.button("✅", key=f"ok_{row['usuario']}"):
                        aprobar_usuario(row['usuario']); st.rerun()
                    if c4.button("❌", key=f"del_{row['usuario']}"):

                        borrar_usuario(row['usuario']); st.rerun()
