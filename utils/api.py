import streamlit as st
from urllib.request import Request, urlopen
import json
from datetime import datetime
import pytz

HEADERS = {'User-Agent': 'Mozilla/5.0 (App Porra F1)'}

@st.cache_data(ttl=600)
def obtener_lista_sesiones_finalizadas(year=2026):
    """Obtiene Carreras y Clasificaciones (Ignorando Sprints)."""
    url = f"https://api.jolpi.ca/ergast/f1/{year}.json"
    try:
        req = Request(url, headers=HEADERS); res = urlopen(req)
        data = json.loads(res.read().decode('utf-8'))
        races = data['MRData']['RaceTable']['Races']
        now = datetime.now(pytz.utc)
        final = []
        for r in races:
            # 1. CARRERA
            dt_str = f"{r['date']}T{r['time']}".replace('Z','')
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
            if dt < now:
                final.append({"label": f"🏁 {r['raceName']} - CARRERA", "round": r['round'], "year": r['season'], "type": "Race", "date": dt})

            # 2. CLASIFICACIÓN (Solo visualización)
            if 'Qualifying' in r:
                q_date = r['Qualifying']['date']
                q_time = r['Qualifying']['time']
                dt_q = datetime.strptime(f"{q_date}T{q_time}".replace('Z',''), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
                if dt_q < now:
                     final.append({"label": f"⏱️ {r['raceName']} - CLASIFICACIÓN", "round": r['round'], "year": r['season'], "type": "Qualifying", "date": dt_q})

        final.sort(key=lambda x: x['date'], reverse=True)
        return final
    except: return []

@st.cache_data(ttl=60)
def importar_resultado_carrera_api(round_num, year, mapa_numeros):
    """Importa solo RESULTADO DE CARRERA para el Admin (puntos)."""
    url = f"https://api.jolpi.ca/ergast/f1/{year}/{round_num}/results.json"
    try:
        req = Request(url, headers=HEADERS); res = urlopen(req)
        data = json.loads(res.read().decode('utf-8'))
        orden = []
        if data['MRData']['RaceTable']['Races']:
            table = data['MRData']['RaceTable']['Races'][0]['Results']
            for row in table:
                num_api = row['Driver'].get('permanentNumber')
                if num_api:
                    nombre_app = mapa_numeros.get(int(num_api)) 
                    if nombre_app: orden.append(nombre_app)
        return orden
    except: return []

@st.cache_data(ttl=600)
def obtener_detalles_sesion(round_num, year, type_s):
    """Detalles para Live Center (Muestra tiempos si es Qualy, Puntos si es Carrera)."""
    endpoint = "results" if type_s == "Race" else "qualifying"
    url = f"https://api.jolpi.ca/ergast/f1/{year}/{round_num}/{endpoint}.json"
    res_list = []
    try:
        req = Request(url, headers=HEADERS); res = urlopen(req)
        data = json.loads(res.read().decode('utf-8'))
        
        # La estructura cambia según el endpoint
        key = 'Results' if type_s == "Race" else 'QualifyingResults'
        if data['MRData']['RaceTable']['Races']:
            table = data['MRData']['RaceTable']['Races'][0][key]
            for r in table:
                piloto = r['Driver'].get('code', r['Driver']['familyName'][:3].upper())
                
                # Diferencia visual: Qualy = Tiempos, Carrera = Puntos
                if type_s == "Qualifying":
                    # Intentamos coger el mejor tiempo disponible
                    info = r.get('Q3', r.get('Q2', r.get('Q1', 'Sin Tiempo')))
                else:
                    info = f"{r.get('points',0)} pts"
                    
                res_list.append({
                    "Pos": r['position'], 
                    "Piloto": piloto, 
                    "Escudería": r['Constructor']['name'],
                    "Info": info
                })
        return res_list
    except: return []

@st.cache_data(ttl=3600)
def obtener_clasificacion_mundial(year, mapa_numeros):
    url = f"https://api.jolpi.ca/ergast/f1/{year}/driverStandings.json"
    try:
        req = Request(url, headers=HEADERS); res = urlopen(req)
        data = json.loads(res.read().decode('utf-8'))
        lista = data['MRData']['StandingsTable']['StandingsLists']
        tabla = []
        if lista:
            drivers = lista[0]['DriverStandings']
            for d in drivers:
                num = int(d['Driver'].get('permanentNumber', 0))
                nombre = mapa_numeros.get(num, d['Driver']['familyName']) 
                tabla.append({
                    "Pos": int(d['position']),
                    "Piloto": nombre,
                    "Escudería": d['Constructors'][0]['name'],
                    "Puntos": float(d['points']),
                    "Victorias": int(d['wins'])
                })
        return tabla

    except: return []
