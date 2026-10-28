# DenuPe — Backend de clasificación de denuncias (IA v2)

Microservicio [FastAPI](https://fastapi.tiangolo.com/) para la aplicación móvil [DenuPe](https://github.com/Zarabia-22/denupe).
Sugiere una categoría a partir del **título y la descripción**. El usuario siempre puede elegir manualmente.

## Catálogo de ocho categorías

| Código | Categoría |
|---|---|
| `alumbrado` | Alumbrado público |
| `seguridad` | Seguridad ciudadana |
| `limpieza` | Limpieza y residuos |
| `agua` | Agua y saneamiento |
| `transito` | Tránsito y transporte |
| `areas_verdes` | Parques y áreas verdes |
| `infraestructura` | Vialidad e infraestructura |
| `otros` | Otros |

Los nombres coinciden con las categorías del SQL de la aplicación. **Ruido** pertenece a `Otros`, pues no existe como categoría independiente.

## Datos y tratamiento de texto

- `data/denuncias_simuladas_800.csv`: **800 denuncias ficticias**, exactamente 100 por categoría, con título, descripción, etiqueta y procedencia.
- Se escribieron 20 situaciones base por categoría, cada una con cinco variantes de formulación. Todos son casos inventados; **no son denuncias recogidas de ciudadanos**.
- `app/text_processing.py`: normaliza Unicode, tildes, mayúsculas, espacios, signos, números, correos y enlaces. El procesamiento ocurre en memoria.
- `training/train.py`: separa **grupos completos** de variantes: 560 ejemplos de entrenamiento, 120 de validación y 120 de prueba. Las cinco variantes de una situación nunca aparecen en particiones diferentes.
- Características: TF-IDF de palabras (1-2 palabras) y caracteres (3-5 caracteres) + regresión logística multiclase (`scikit-learn`). No hay reglas de palabras clave que asignen categorías: **las ocho clases se aprenden del conjunto de entrenamiento**.
- El umbral de aceptación se selecciona usando solamente validación. En predicción, si el texto no ofrece suficiente vocabulario reconocido, el máximo puntaje es bajo o hay poco margen frente a la segunda categoría, la API **se abstiene** y permite selección manual.

### Reproducir el entrenamiento

Requiere Python 3.11:

```bash
python -m venv .venv
# Activar .venv según el sistema operativo
pip install -r requirements-dev.txt
python -m training.train
python -m pytest -q
```

El entrenamiento reemplaza `models/modelo_categorias.joblib.gz`, `models/vectorizador_tfidf.joblib.gz` y `models/metricas.json`.
El flujo de GitHub Actions **Entrenar modelo de 8 categorías** lo ejecuta de forma reproducible al cambiar los datos o el entrenamiento, verifica las pruebas y versiona los artefactos generados en la rama de desarrollo.

**Importante:** la exactitud y F1 registradas en `models/metricas.json` corresponden a **casos sintéticos**. Al compartir situaciones base, las variantes siguen siendo similares aunque se evite su fuga entre entrenamiento y prueba; por ello **no representan el rendimiento en denuncias reales**. Antes de producción se requieren casos reales etiquetados, una evaluación externa, revisión de sesgos y recalibración del umbral. La probabilidad de la regresión logística no debe interpretarse como certeza calibrada.

## API

```bash
uvicorn app.main:app --reload
```

- `GET /health`: estado de salud y versión del clasificador.
- `GET /docs`: documentación interactiva Swagger.
- `POST /api/ia/sugerir-categoria`: recibe `titulo` (5-100 caracteres) y `descripcion` (10-500 caracteres).
- La respuesta mantiene el contrato de Flutter: `sugerida`, `categoria`, `confianza_modelo`, `cobertura_vocabulario` y `motivo`.

Ejemplo:

```json
{"titulo": "Baches en la pista principal", "descripcion": "El pavimento está dañado y hay varios huecos en la calzada."}
```

```json
{"sugerida": true, "categoria": "Vialidad e infraestructura", "confianza_modelo": 0.86, "cobertura_vocabulario": 0.78, "motivo": null}
```

**Los valores numéricos del ejemplo son ilustrativos.** También puede devolver `sugerida: false`, `categoria: null` y un motivo. Nunca asigna la categoría al ciudadano automáticamente.

## Integración Flutter

El cliente está en `lib/services/ai_category_service.dart` del repositorio principal, con el botón en `lib/screens/new_complaint_screen.dart`.
La URL se configura mediante `DENUPE_IA_URL` y la app relaciona el nombre devuelto con el catálogo real del backend de datos. Flutter cuenta con selección manual ante rechazo o falta de conexión.

## Despliegue

Se proporciona `Dockerfile` y `render.yaml` para Render (ruta de health-check `/health`). Una configuración no garantiza que un despliegue esté activo.
El contenedor solo carga artefactos de **ocho clases v2**, y fallará explícitamente si detecta artefactos antiguos. El servicio no accede a la base de datos ni presenta denuncias: solo sugiere categorías.

## Seguridad y limitaciones

Este es un prototipo académico. El endpoint no tiene autenticación ni limitación de tasa; hay que establecer controles de acceso y antiabuso antes de exposición pública. Las cargas incluyen texto redactado por ciudadanos: no se registra deliberadamente su contenido ni debe usarse información personal en pruebas públicas. Deserializar `joblib` puede ejecutar código, por lo que solo se deben cargar artefactos del repositorio de confianza. Usar HTTPS y verificar los mapeos de categorías de la base de datos.
