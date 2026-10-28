# DenuPe — Backend de clasificación de denuncias (IA v3)

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

El entrenamiento usa **2.400 denuncias simuladas**, 300 por cada una de las 8 categorías:

| Archivo | Registros | Casos base |
|---|---:|---:|
| `data/denuncias_simuladas_800.csv` | 800 | 160 |
| `data/denuncias_simuladas_adicionales_1600.csv` | 1.600 | 320 |
| **Total** | **2.400** | **480** |

Cada uno de los 480 casos tiene cinco variantes de redacción, por lo que el modelo practica distintas expresiones de situaciones semejantes. Son **datos inventados**, no denuncias ciudadanas auténticas.

El procesamiento incluye normalización de Unicode, tildes, mayúsculas, signos, números, correos, enlaces y espacios; TF-IDF de palabras (unigramas y bigramas) más fragmentos de caracteres (3 a 5); y clasificación multiclase sin reglas manuales de clasificación. Los cinco ejemplos de un mismo caso se mantienen siempre en la misma partición.

La división estratificada por categoría es de 1.680 ejemplos de entrenamiento, 360 de validación y 360 de prueba, con semilla reproducible. La selección compara **cinco configuraciones de modelos** mediante validación, sin utilizar el conjunto de prueba para elegir el modelo. El sistema también dispone de un umbral de abstención: si la confianza, la cobertura de vocabulario o el margen entre categorías es insuficiente, mantiene la elección manual.

### Métricas verificadas sobre datos simulados

- **96,67 % accuracy** y **96,66 % F1 macro** sobre las 360 denuncias del conjunto de prueba (348 aciertos).
- Modelo elegido con validación: **LogisticRegression(C=15)**, sobre TF-IDF de palabras y caracteres.
- De 360 solicitudes evaluadas, el filtro de recomendación **sugiere 343** (95,28 % de cobertura) y acierta en **340** de las 343 emitidas (99,13 % de precisión selectiva).
- `models/metricas.json` contiene los resultados completos, la matriz de confusión y las métricas por clase.
- `tests/test_training.py` incluye una comprobación que exige al menos 90 % de exactitud y de F1 macro **en este benchmark simulado**.

**Interpretación:** la métrica corresponde a un banco artificial de prueba con formatos de redacción compartidos; aunque los casos base no cruzan las divisiones, puede ser más sencillo que denuncias reales. No demuestra una precisión real de 96,67 %, ni garantiza una exactitud mínima en producción. Para validar con rigor en condiciones reales se necesitan denuncias reales anonimizadas, etiquetadas, de fuentes y periodos independientes, evaluación por distrito y categoría, y revisión de ambigüedades, negaciones y casos fuera de dominio. Las probabilidades de `predict_proba` no están calibradas.

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
El flujo de GitHub Actions **Entrenar modelo de ocho categorias** lo ejecuta de forma reproducible al cambiar los datos o el entrenamiento, verifica las pruebas y versiona los artefactos generados en la rama de desarrollo.

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
El contenedor solo carga artefactos de **ocho clases v3**, y fallará explícitamente si detecta artefactos antiguos. El servicio no accede a la base de datos ni presenta denuncias: solo sugiere categorías.

## Seguridad y limitaciones

Este es un prototipo académico. El endpoint no tiene autenticación ni limitación de tasa; hay que establecer controles de acceso y antiabuso antes de exposición pública. Las cargas incluyen texto redactado por ciudadanos: no se registra deliberadamente su contenido ni debe usarse información personal en pruebas públicas. Deserializar `joblib` puede ejecutar código, por lo que solo se deben cargar artefactos del repositorio de confianza. Usar HTTPS y verificar los mapeos de categorías de la base de datos.
