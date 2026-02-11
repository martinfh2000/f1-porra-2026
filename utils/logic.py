from datetime import datetime
import pytz

def verificar_estado_evento(id_evento, df_cal):
    """Determina si un evento está ABIERTO o CERRADO."""
    try:
        idx = df_cal.index[df_cal['id_evento'] == id_evento].tolist()
        if not idx: return 'ERROR'
        evento = df_cal.iloc[idx[0]]
        # Hora actual en España
        ahora = datetime.now(pytz.timezone('Europe/Madrid'))
        if ahora > evento['fecha_dt']: 
            return 'CERRADO'
        return 'ABIERTO'
    except: return 'ERROR'

def calcular_puntos_carrera(prediccion, resultado):
    """4 pts acierto, 2 pts podio, 1 pt top 10."""
    pts = 0
    # Top 10 predicción
    for i, piloto in enumerate(prediccion[:10]):
        try: pos_real = resultado.index(piloto)
        except: pos_real = -1
        
        if pos_real == i: pts += 4
        elif i < 3 and pos_real < 3 and pos_real != -1: pts += 2
        elif pos_real < 10 and pos_real != -1: pts += 1
    return pts

def calcular_puntos_mundial(prediccion, resultado):
    """30 pts acierto exacto, 10 pts error de +/- 1 posición."""
    pts = 0
    for i, piloto in enumerate(prediccion):
        try:
            pos_real = resultado.index(piloto)
            diff = abs(i - pos_real)
            if diff == 0: pts += 30
            elif diff == 1: pts += 10
        except: pass
    return pts