# DenuPe — Backend de IA (FastAPI)

Microservicio independiente de la aplicación Flutter [DenuPe](https://github.com/Zarabia-22/denupe). Implementa la sugerencia de categorías a partir de **título + descripción** mediante el **modelo entrenado por el usuario en Google Colab**: `TfidfVectorizer(lowercase=True, ngram_range=(1,2))` y `DecisionTreeClassifier(max_depth=10, random_state=42)`.

**Categorías:** Alumbrado, Limpieza, Ruido y Seguridad. Entrenado con 200 denuncias simuladas: 140 para entrenamiento y 60 para evaluación. El notebook registró un **83,33 %** de exactitud en las muestras simuladas. Esto no garantiza esa precisión en denuncias reales.

## Ejecutar localmente (Python 3.11)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

El modelo y su vectorizador están incluidos en `models/*.joblib.gz` (comprimidos sin cambiar el contenido de sus objetos originales); no necesitas Colab para ejecutar el servidor.

- Swagger: http://127.0.0.1:8000/docs
- Estado: http://127.0.0.1:8000/health
- Predicción: `POST /api/ia/sugerir-categoria`

Ejemplo de solicitud:

```json
{"titulo":"Basura acumulada en mi calle","descripcion":"Hay bolsas de basura y residuos que no han sido recogidos durante varios dias"}
```

Ejemplo de respuesta (valores numéricos ilustrativos):

```json
{"sugerida":true,"categoria":"Limpieza","confianza_modelo":1.0,"cobertura_vocabulario":0.625,"motivo":null}
```

Si el texto es poco informativo se devuelve `sugerida:false`, `categoria:null` y un `motivo`; el usuario debe conservar la opción manual. `confianza_modelo` es el resultado no calibrado de `predict_proba`, **no** un porcentaje de certeza real.

## Pruebas

```powershell
python -m pytest -q
```

GitHub Actions ejecuta estas pruebas después de cada push.

## Flutter

La rama de integración es [feature/integracion-ia-categoria-logica](https://github.com/Zarabia-22/denupe/tree/feature/integracion-ia-categoria-logica). Su botón «Sugerir categoría con IA» realiza la llamada real y permite elegir manualmente si el servicio está desconectado.

En el archivo `.env` de Flutter, configura:

```env
DENUPE_IA_URL=https://TU-URL-EN-RENDER.onrender.com
```

Para emulador Android local: `http://10.0.2.2:8000` (solo permitido en debug). La API responde con el nombre de la categoría; Flutter lo relaciona con las categorías reales de la base de datos, sin seleccionar arbitrariamente una cuando no hay correspondencia única.

## Despliegue

Incluye `Dockerfile` y `render.yaml`. En Render, crea un servicio Web con **runtime Docker**, rama `main`, instancia gratuita de pruebas y chequeo de salud `/health`. Render asignará una URL HTTPS pública al completar el despliegue.

El repositorio por sí solo no publica el servidor. El microservicio no usa la base de datos ni envía denuncias: **únicamente sugiere una categoría**.

### Seguridad y límites

- Es un **prototipo**: el endpoint no exige autenticación; antes de un lanzamiento público conviene validar tokens de usuario y aplicar rate limiting en la infraestructura.
- Las solicitudes contienen texto escrito por ciudadanos. La aplicación no registra deliberadamente su contenido. No introduzcas datos sensibles en pruebas públicas.
- `joblib` puede ejecutar código al deserializar; los artefactos solo deben proceder del repositorio controlado.
- La cobertura de vocabulario y el umbral de 0.75 son filtros heurísticos. No representan garantías sobre exactitud real.
- En Flutter usa siempre HTTPS en producción, y prueba las equivalencias de nombres frente a las categorías de la base de datos.
