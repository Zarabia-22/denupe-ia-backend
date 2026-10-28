"""Normalización reutilizable para entrenamiento e inferencia.

No guarda texto del ciudadano ni elimina información fuera del proceso en memoria.
"""
import re
import unicodedata

PALABRAS_VACIAS = frozenset("""
a al algo ante bajo cada cerca con contra como cuando de del desde donde durante el ella
en entre era es esa esas ese eso estos esta estan este fue ha hay la las le les lo los
mas me mi mis mucho muy ni no nos nuestro o para pero por porqué porque que se ser si
sin sobre su sus te tiene toda todo todos un una unas uno unos ya
acerca ademas alli aqui avenida barrio calle calles casa casas colegio cuadra distrito
esquina frente gente hecho lugar mercado vecinos vecinas vecino vecina varios varias
zona problema reporto reportamos reportar solicito solicitar necesito existe ocurre
ocurren sucede sucede hace dias dia semana semanas hoy ayer
""".split())


def normalizar_texto(texto: str) -> str:
    """Unifica Unicode, mayúsculas, tildes, signos, espacios y datos identificables."""
    texto = unicodedata.normalize("NFKD", str(texto).casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"https?://\S+|www\.\S+", " ", texto)
    texto = re.sub(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", " ", texto)
    texto = re.sub(r"\b\d{6,}\b", " ", texto)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\b\d+\b", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def cobertura_vocabulario(texto: str, vectorizador) -> tuple[float, int, int]:
    """Cobertura por términos relevantes aprendidos; ignora texto de contexto común."""
    vocabulario = vectorizador.transformer_list[0][1].vocabulary_
    terminos = [
        token for token in normalizar_texto(texto).split()
        if len(token) > 2 and token not in PALABRAS_VACIAS
    ]
    if not terminos:
        return 0.0, 0, 0
    reconocidos = sum(1 for token in terminos if token in vocabulario)
    return reconocidos / len(terminos), reconocidos, len(terminos)
