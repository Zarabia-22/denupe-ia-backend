"""Catálogo oficial de categorías (migración inicial del repositorio DenuPe).

El modelo joblib existente fue entrenado solo en Alumbrado, Limpieza,
Ruido y Seguridad. Estas entradas representan el catálogo de la aplicación,
NO nuevas clases aprendidas por el modelo.
"""
CATEGORIAS = {
    "alumbrado": "Alumbrado público",
    "seguridad": "Seguridad ciudadana",
    "limpieza": "Limpieza y residuos",
    "agua": "Agua y saneamiento",
    "transito": "Tránsito y transporte",
    "areas_verdes": "Parques y áreas verdes",
    "infraestructura": "Vialidad e infraestructura",
    "otros": "Otros",
}

# Correspondencia de las etiquetas legadas del clasificador.
# "Ruido" no existe como categoría independiente en la aplicación.
ETIQUETAS_MODELO = {
    "Alumbrado": CATEGORIAS["alumbrado"],
    "Seguridad": CATEGORIAS["seguridad"],
    "Limpieza": CATEGORIAS["limpieza"],
    "Ruido": CATEGORIAS["otros"],
}

# Vocabulario explícito para categorías que aún no forman parte
# del entrenamiento del árbol. Se exige evidencia textual específica.
PATRONES_ADICIONALES = {
    "agua": (
        "fuga de agua", "tuberia rota", "tuberia reventada", "sin agua",
        "corte de agua", "cortes de agua", "desague", "alcantarilla",
        "alcantarillado", "aniego", "agua potable", "aguas residuales",
    ),
    "transito": (
        "semaforo", "señal de transito", "senal de transito",
        "señalizacion vial", "senalizacion vial", "congestion vehicular",
        "trafico vehicular", "paradero", "transporte publico", "cruce peatonal",
    ),
    "areas_verdes": (
        "arbol caido", "arboles caidos", "poda de arboles", "poda de arbol",
        "cesped", "jardines abandonados", "areas verdes", "area verde",
        "parque abandonado", "parque descuidado", "juegos infantiles rotos",
    ),
    "infraestructura": (
        "bache", "baches", "pista rota", "pistas rotas", "vereda rota",
        "veredas rotas", "hueco en la pista", "huecos en la pista",
        "pavimento dañado", "pavimento danado", "puente dañado",
        "puente danado", "calzada deteriorada",
    ),
}
