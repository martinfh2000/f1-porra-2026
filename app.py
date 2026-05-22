import streamlit as st
import pandas as pd
import time
from streamlit_sortables import sort_items

# --- IMPORTAMOS MÓDULOS PROPIOS ---
from utils.auth import encriptar, desencriptar
from utils.database import (obtener_datos_maestros, obtener_datos_resultados, 
                            guardar_apuesta, guardar_resultado, registrar_usuario_nuevo, 
                            unirse_liga, aprobar_usuario, borrar_usuario)
from utils.api import (obtener_lista_sesiones_finalizadas, obtener_detalles_sesion, 
                       importar_resultado_carrera_api, obtener_clasificacion_mundial)
from utils.logic import verificar_estado_evento, calcular_puntos_carrera, calcular_puntos_mundial

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="F1 Manager", page_icon="🏎️", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'mis_ligas' not in st.session_state: st.session_state.mis_ligas = []

# --- LOGIN ---
def login(u, p):
    _, df_u, _ = obtener_datos_maestros()
    try:
        row = df_u[df_u['usuario']==u].iloc[0]
        if str(p) == str(row['password']):
            return True, row['rol'], [x.strip().upper() for x in str(row['liga_privada']).split(",") if x.strip()]
        return False, None, []
    except: return False, None, []

# ==========================================
#              INTERFAZ
# ==========================================
if not st.session_state.logged_in:
    st.title("🏎️ F1 Manager 2026")
    t1, t2 = st.tabs(["🔑 Entrar", "📝 Crear Cuenta"])
    with t1:
        u = st.text_input("Usuario", key="l_u"); p = st.text_input("Contraseña", type="password", key="l_p")
        if st.button("Iniciar Sesión", type="primary"):
            ok, rol, ligs = login(u, p)
            if ok:
                st.session_state.logged_in=True; st.session_state.usuario_actual=u
                st.session_state.rol_usuario=rol; st.session_state.mis_ligas=ligs
                st.rerun()
            else: st.error("Error credenciales.")
    with t2:
        u = st.text_input("Nuevo Usuario", key="r_u"); p = st.text_input("Nueva Contraseña", type="password", key="r_p")
        l = st.text_input("Liga", key="r_l")
        if st.button("Registrarse"):
            ok, msg = registrar_usuario_nuevo(u, p, l)
            if ok: st.success(msg)
            else: st.error(msg)

else:
    # 1. CARGA DE DATOS
    df_cal, df_users, df_pilotos = obtener_datos_maestros()
    if df_pilotos.empty: st.error("⚠️ Faltan pilotos."); st.stop()
    
    PILOTOS_LISTA = df_pilotos['nombre'].tolist()
    MAPA_NUMEROS = dict(zip(df_pilotos['numero'], df_pilotos['nombre']))

    # 2. SIDEBAR (MEJORADA PARA ADMIN)
    with st.sidebar:
        st.write(f"👤 **{st.session_state.usuario_actual}**")
        
        # Opciones Exclusivas de Admin
        if st.session_state.rol_usuario == "admin":
            st.warning("🛠️ MODO ADMIN ACTIVO")
            # Botón útil para cuando cambies cosas en Excel y no se vean
            if st.button("🧹 Limpiar Caché App"):
                st.cache_data.clear()
                st.success("Caché borrada")
                time.sleep(1)
                st.rerun()
        
        st.write("---")
        st.write("🏆 MIS LIGAS") 
        if not st.session_state.mis_ligas:
            st.caption("Sin ligas privadas")
        for l in st.session_state.mis_ligas: 
            st.write(f"• {l}")
            
        with st.expander("➕ Unirse a Liga"):
            if st.button("Unirse a " + (nl:=st.text_input("Nombre Liga"))): 
                unirse_liga(st.session_state.usuario_actual, nl)
                st.rerun()
        
        st.divider()
        
        # BOTÓN DE LOGOUT ROBUSTO
        if st.button("🚪 Cerrar Sesión", type="primary"):
            # Borramos todas las variables de sesión para evitar conflictos
            for key in st.session_state.keys():
                del st.session_state[key]
            st.rerun()

    st.title("🏆 Porra F1")
    tn = ["📝 Porra", "📊 Ranking", "👀 Apuestas", "📡 Live Center", "📜 Normas"]
    if st.session_state.rol_usuario == "admin": tn.extend(["⚙️ Admin Resultados", "👥 Admin Usuarios"])
    tabs = st.tabs(tn)

    # --- TAB 1: HACER PORRA (SOLO CARRERA Y MUNDIAL) ---
    with tabs[0]:
        evs = df_cal['nombre_mostrar'].tolist(); idx = 0
        for i, r in df_cal.iterrows():
            if verificar_estado_evento(r['id_evento'], df_cal) == "ABIERTO": idx=i; break
        sel = st.selectbox("Gran Premio:", evs, index=idx)
        
        rev = df_cal[df_cal['nombre_mostrar']==sel].iloc[0]
        ide = rev['id_evento']; est = verificar_estado_evento(ide, df_cal)
        es_mundial = "mundial" in ide

        _, dbc, dbm = obtener_datos_resultados()
        
        prev = []
        df_target = dbm if es_mundial else dbc
        col_filtro = 'tipo' if es_mundial else 'carrera'

        if not df_target.empty:
            f = df_target[(df_target['usuario']==st.session_state.usuario_actual) & (df_target[col_filtro]==ide)]
            if not f.empty: prev = desencriptar(f.iloc[-1]['datos_encriptados']).split(",")

        if prev: st.info(f"✅ Apuesta guardada: {prev[0]}, {prev[1]}...")
        
        if est != "ABIERTO": st.warning(f"🔒 {est}")
        else:
            if es_mundial:
                st.subheader("🏆 Ordena el Mundial de Pilotos")
                st.info("Arrastra y suelta los nombres para ordenar tu predicción.")

                # 1. Definimos el orden inicial (Tu apuesta guardada o la lista por defecto)
                # Nos aseguramos de que estén todos los pilotos (por si acaso cambió la lista)
                if prev and len(prev) == len(PILOTOS_LISTA):
                    default_items = prev
                else:
                    default_items = PILOTOS_LISTA

                # 2. WIDGET DE ARRASTRAR Y SOLTAR
                # Esto crea una lista vertical ordenable
                orden_final = sort_items(default_items, direction='vertical')

                # 3. GUARDAR
                if st.button("Guardar Predicción Mundial", type="primary"):
                    # Verificamos que no se haya perdido ningún piloto (seguridad)
                    if len(orden_final) == len(PILOTOS_LISTA):
                        guardar_apuesta(st.session_state.usuario_actual, ide, encriptar(",".join(orden_final)), "mundial")
                        st.balloons()
                        st.success("✅ ¡Orden guardado correctamente!")
                    else:
                        st.error("Error: Faltan pilotos en la lista.")
            else:
                st.write("Top 10 Carrera (Domingo)")
                cols = st.columns(2); sc = []
                for i in range(10): 
                    def_val = prev[i] if prev and len(prev)>i and prev[i] in PILOTOS_LISTA else "-"
                    idx_p = ([ "-"] + PILOTOS_LISTA).index(def_val)
                    sc.append(cols[i%2].selectbox(f"P{i+1}", ["-"]+PILOTOS_LISTA, index=idx_p, key=f"p{i}"))
                if st.button("Guardar") and "-" not in sc and len(set(sc))==10: 
                    guardar_apuesta(st.session_state.usuario_actual, ide, encriptar(",".join(sc)), "carrera")
                    st.balloons(); st.success("Guardado")

    # --- TAB 2: RANKING ---
    with tabs[1]:
        if st.button("🔄 Refrescar"): obtener_datos_resultados.clear(); st.rerun()
        dfr, dbc, dbm = obtener_datos_resultados()
        ptsd = {}
        
        if not dfr.empty:
            for _, r in dfr.iterrows():
                cid = r['carrera']
                if not r['p1']: continue
                ofi = [r[f'p{i}'] for i in range(1,23) if r[f'p{i}']]
                es_mundial = "mundial" in cid
                
                bts = dbm[dbm['tipo']==cid] if es_mundial else dbc[dbc['carrera']==cid]
                
                for _, b in bts.iterrows():
                    if verificar_estado_evento(cid, df_cal)=="CERRADO" or es_mundial: 
                        p = desencriptar(b['datos_encriptados']).split(",")
                        pt = calcular_puntos_mundial(p, ofi) if es_mundial else calcular_puntos_carrera(p, ofi)
                        ptsd[b['usuario']] = ptsd.get(b['usuario'],0)+pt
        
        lig = st.selectbox("Liga:", ["GLOBAL"]+st.session_state.mis_ligas)
        if ptsd:
            rd = pd.DataFrame(list(ptsd.items()), columns=["Usuario", "Puntos"]).sort_values("Puntos", ascending=False)
            if lig != "GLOBAL":
                usl = [u['usuario'] for _, u in df_users.iterrows() if lig in str(u['liga_privada'])]
                rd = rd[rd['Usuario'].isin(usl)]

            rd["Posición"] = range(1, len(rd) + 1)
            rd = rd.set_index("Posición")
          
            #st.bar_chart(rd.set_index("Usuario"));
            st.dataframe(rd, use_container_width=True)

    # --- TAB 3: ESPIAR (SIN FECHA) ---
    with tabs[2]:
        st.header("🕵️ Apuestas")
        spy_ev = st.selectbox("Evento:", df_cal['nombre_mostrar'].tolist(), key="spy")
        row_spy = df_cal[df_cal['nombre_mostrar'] == spy_ev].iloc[0]
        id_spy = row_spy['id_evento']
        
        if verificar_estado_evento(id_spy, df_cal) != "CERRADO":
            st.warning("🔒 Secreto hasta el cierre.")
        else:
            _, dbc, dbm = obtener_datos_resultados()
            es_m = "mundial" in id_spy
            df_f = dbm[dbm['tipo']==id_spy] if es_m else dbc[dbc['carrera']==id_spy]

            if not df_f.empty:
                u_spy = st.selectbox("Usuario:", ["-"]+sorted(df_f['usuario'].unique().tolist()))
                if u_spy != "-":
                    row_u = df_f[df_f['usuario']==u_spy].iloc[-1]
                    dec = desencriptar(row_u['datos_encriptados']).split(",")
                    # SOLO MOSTRAMOS TABLA, SIN HORA
                    st.dataframe(pd.DataFrame(dec, columns=["Piloto"], index=range(1, len(dec)+1)))
            else: st.info("Sin datos.")

    # --- TAB 4: LIVE CENTER (CARRERA + QUALY) ---
    with tabs[3]:
        st.header("📡 Live Center")
        t_ses, t_mun = st.tabs(["🏁 Sesiones (Carrera/Qualy)", "🏆 Mundial"])
        with t_ses:
            if st.button("Buscar"): obtener_lista_sesiones_finalizadas.clear(); st.rerun()
            sess = obtener_lista_sesiones_finalizadas(2026) 
            if sess:
                # Aquí saldrán tanto Carreras como Clasificaciones (pero no Sprints)
                s = st.selectbox("Sesión:", [x['label'] for x in sess])
                obj = next(x for x in sess if x['label']==s)
                
                with st.spinner("Cargando resultados..."):
                    res = obtener_detalles_sesion(obj['round'], obj['year'], obj['type'])
                
                # CONDICIONAL DE SEGURIDAD: Solo pintamos la tabla si hay datos
                if res:
                    st.dataframe(pd.DataFrame(res).set_index("Pos"), use_container_width=True)
                else:
                    st.info("⏳ Los resultados detallados aún no están disponibles en la base de datos oficial. Inténtalo más tarde.")
            else: st.warning("Sin datos.")
        with t_mun:
            if st.button("Actualizar"): obtener_clasificacion_mundial.clear(); st.rerun()
            md = obtener_clasificacion_mundial(2026, MAPA_NUMEROS)
            if md:
                df_m = pd.DataFrame(md)
                st.dataframe(df_m.set_index("Pos"), use_container_width=True, height=600, column_config={"Puntos": st.column_config.ProgressColumn("Puntos", format="%d", min_value=0, max_value=int(df_m['Puntos'].max()))})

    # --- TAB 5: NORMAS ---
    with tabs[4]:
        st.markdown("## 📜 Reglamento Oficial F1 2026")
        
        st.markdown("""
        ### 🏎️ 1. Pronósticos de Carrera (Top 10)
        Solo puntúan los pilotos que coloques dentro de tu Top 10 para la carrera del domingo.
        * **4 Puntos:** Acierto de la posición **exacta** del piloto.
        * **2 Puntos:** El piloto acaba en el **Podio (Top 3)**, lo pusiste en el Top 3, pero fallaste su posición exacta.
        * **1 Punto:** El piloto acaba en la zona de puntos (**Top 10**), lo pusiste en tu Top 10, pero fallaste su posición exacta.
        
        ### 🏆 2. Pronóstico del Mundial
        Predicción de la clasificación final de los 22 pilotos al terminar la temporada.
        * **30 Puntos:** Acertar la posición **exacta** de un piloto.
        * **10 Puntos:** Fallar por **1 sola posición** (ej. pones a un piloto 3º y termina 2º o 4º).

        ### ⏱️ 3. Cierres y Privacidad
        * **Bloqueo:** Las porras de cada Gran Premio se cierran automáticamente a la hora oficial de inicio de la sesión.
        * **Ver Apuestas:** Las apuestas de los demás jugadores están encriptadas y son **completamente secretas**. Solo podrás verlas en la pestaña "Ver Apuestas" una vez que el evento haya cambiado a estado "CERRADO".
        """)

    # --- TAB 6: ADMIN RESULTADOS ---
    if st.session_state.rol_usuario == "admin":
        with tabs[5]:
            st.subheader("⚙️ Resultados (Solo Carrera)")
            l_ids = df_cal['id_evento'].tolist(); l_ns = df_cal['nombre_mostrar'].tolist()
            idx = st.selectbox("Evento:", range(len(l_ns)), format_func=lambda x: l_ns[x])
            
            c1, c2 = st.columns([1,2])
            with c1:
                if st.button("📥 Importar API (2026)"):
                    res_api = importar_resultado_carrera_api(idx+1, 2026, MAPA_NUMEROS)
                    if res_api: st.session_state.temp_res = res_api; st.success(f"{len(res_api)} OK")
                    else: st.error("Error API")
            with c2:
                defs = st.session_state.get('temp_res', [])
                final = st.multiselect("Orden Oficial:", PILOTOS_LISTA, default=defs)
                if st.button("Guardar Oficial"):
                    f = [l_ids[idx]] + final
                    while len(f)<23: f.append("")
                    f.append("TRUE")
                    guardar_resultado(f); st.success("Guardado")

    # --- TAB 7: ADMIN USUARIOS ---
    if st.session_state.rol_usuario == "admin":
        with tabs[6]:
            if st.button("Refrescar"): obtener_datos_maestros.clear(); st.rerun()
            pens = df_users[df_users['rol']=='pendiente']
            if not pens.empty:
                for _, r in pens.iterrows():
                    c1,c2,c3,c4 = st.columns([2,2,1,1])
                    c1.write(r['usuario']); c2.caption(r['liga_privada'])
                    if c3.button("✅", key=f"ok_{r['usuario']}"): aprobar_usuario(r['usuario']); st.rerun()

                    if c4.button("❌", key=f"no_{r['usuario']}"): borrar_usuario(r['usuario']); st.rerun()

