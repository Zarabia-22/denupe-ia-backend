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


## HU-IA02 — Recomendación de entidad pública

Se incorpora el endpoint independiente `POST /api/ia/sugerir-entidad`. Recibe la categoría, departamento, provincia, distrito, título y descripción de la denuncia. Consulta `data/entidades_publicas.json` y solo recomienda un registro cuando coinciden la jurisdicción, la categoría y términos relevantes de la descripción.

Ejemplo de solicitud:

```json
{
  "categoria": "Limpieza y residuos",
  "departamento": "Lima",
  "provincia": "Lima",
  "distrito": "Miraflores",
  "titulo": "Basura acumulada en la avenida",
  "descripcion": "Hay bolsas de residuos y desperdicios sin recoger en la vía pública."
}
```

La respuesta contiene `sugerida`, `entidad` (identificador, nombre, tipo, datos de contacto disponibles y ámbito territorial) y `motivo`. Si no hay coincidencia o existen candidatos equivalentes, devuelve `sugerida: false` y no asigna una institución. La selección y derivación final deben seguir bajo control del ciudadano o del personal responsable.

**Estado del directorio:** `data/entidades_publicas.json` contiene 50 registros municipales de Lima Metropolitana y Callao. Los registros tienen nombre y ámbito territorial contrastados con el directorio del INEI 2026. La matriz habilita únicamente Limpieza y residuos y Parques y áreas verdes; el campo `verificado_competencias` no debe interpretarse como autorización para las demás categorías. Las 46 referencias PNP históricas están separadas y deshabilitadas. La lógica municipal es una coincidencia territorial y temática basada en catálogo; no es un nuevo modelo de aprendizaje automático ni una validación legal individual de cada incidente.

Pruebas específicas: `tests/test_entidades.py` cubre directorio vacío, coincidencia territorial y temática, rechazo de otro distrito, categorías no habilitadas, exclusión de referencias PNP históricas, exigencia de GPS, resolución por polígono, comprobación del código en la capa de comisarías y abstención ante errores o resultados ambiguos.


### Cobertura territorial inicial: Lima Metropolitana y Callao

El catálogo `data/entidades_publicas.json` contiene 50 registros territoriales municipales: los 43 distritos de la provincia de Lima y los 7 distritos de la Provincia Constitucional del Callao. Para Lima (Cercado) se registra la Municipalidad Metropolitana de Lima y para Callao la Municipalidad Provincial del Callao; los demás registros corresponden a sus municipalidades distritales.

La relación territorial se basa en el Directorio Nacional de Gobiernos Regionales, Municipalidades Provinciales y Distritales 2026 del INEI: https://www.gob.pe/institucion/inei/informes-publicaciones/8058591-national-directory-of-regional-provincial-municipalities-district-governments-and-of-populated-centers-2026. La PCM identifica a la provincia de Lima como conformada por 43 distritos: https://www.gob.pe/institucion/pcm/campanas/4355-limametropolitana-informacion-territorial. El Callao se trata como provincia constitucional separada.

**Límite importante:** estos registros cubren municipalidades, no el directorio completo de entidades sectoriales. Las comisarías no se infieren a partir del distrito ni de las 46 referencias históricas. Para seguridad, la versión actual resuelve la jurisdicción mediante el polígono oficial de GEOMININTER y comprueba el código en la capa de comisarías. Los 50 registros municipales tienen `verificado_competencias: true` en el catálogo, pero la matriz solo habilita dos categorías: Limpieza y residuos y Parques y áreas verdes. No se deben usar las sugerencias como derivación automática sin revisión humana.


### Referencias PNP para Lima y Callao (no habilitadas para derivación)

Se añade `data/comisarias_pnp_referencia.json` con 46 referencias de comisarías que aparecen en el Anexo 01 del DU 085-2020. Se conservan como datos históricos de apoyo, no como un padrón vigente ni como una relación exhaustiva de todas las comisarías actuales. Cada registro lleva `habilitada_recomendacion: false` y la fecha/fuente correspondiente.

La PNP publicó una línea base de 1,332 comisarías básicas operativas al 15/01/2026 (https://www.gob.pe/institucion/pnp/informes-publicaciones/7531378-linea-base-de-informacion-georreferenciada-de-comisarias-basicas-relacion-de-comisarias-operativas-a-nivel-nacional-2026) y un documento de comisarías con demarcación territorial identificada en mapa (https://www.gob.pe/institucion/pnp/informes-publicaciones/7173744-comisarias-de-la-policia-nacional-del-peru-con-demarcacion-territorial). La implementación usa el servicio geográfico oficial de GEOMININTER para la intersección espacial y confirmación del código; las 46 referencias del DU 085-2020 siguen deshabilitadas. La respuesta no asigna una comisaría usando únicamente el distrito administrativo.


### Matriz de competencias y límites de derivación

Se incorpora `data/matriz_competencias.json`. En esta primera versión solo se habilitan recomendaciones municipales para **Limpieza y residuos** y **Parques y áreas verdes**, con alcance distrital y respaldo general en la Ley Orgánica de Municipalidades (Ley N.° 27972). Las municipalidades de los 50 distritos reciben estas dos categorías en `categorias_habilitadas`.

Se mantienen bloqueadas las recomendaciones automáticas para:
- **Alumbrado público:** falta identificar la empresa concesionaria/titular del servicio y diferenciar instalaciones municipales.
- **Tránsito y transporte:** debe determinarse si corresponde a competencia distrital, metropolitana, ATU, MTC u otra autoridad según vía y servicio.
- **Vialidad e infraestructura:** se debe clasificar la jerarquía y titularidad de la vía antes de derivar.
- **Seguridad / PNP:** se consulta la capa 2 `Jurisdicciones` (polígonos) para resolver espacialmente el punto de la denuncia y la capa 0 `Comisarias` (puntos) para comprobar la presencia del código devuelto. Las 46 referencias históricas del DU 085-2020 no se habilitan para asignación. La comprobación geográfica no certifica por sí sola la situación administrativa vigente de la dependencia; se mantiene revisión humana.

Fuentes normativas y de datos:
- Ley Orgánica de Municipalidades N.° 27972: https://cdn.www.gob.pe/uploads/document/file/2685861/Ley%20Organica%20de%20Municipalidades.pdf
- Capa geográfica de comisarías MININTER: https://geomininter.mininter.gob.pe/arcgis/rest/services/pnp/policia_nacional_peru/MapServer/0
- Padrón de comisarías operativas PNP 2026: https://www.gob.pe/institucion/pnp/informes-publicaciones/7531378-linea-base-de-informacion-georreferenciada-de-comisarias-basicas-relacion-de-comisarias-operativas-a-nivel-nacional-2026
- Comisarías PNP con demarcación territorial: https://www.gob.pe/institucion/pnp/informes-publicaciones/7173744-comisarias-de-la-policia-nacional-del-peru-con-demarcacion-territorial

La recomendación es una ayuda informativa: no ejecuta una derivación administrativa ni sustituye la revisión de la entidad competente. Cuando una categoría no esté habilitada o no haya registro territorial verificable, el endpoint responde `sugerida: false`.


## Validación territorial y despliegue HU-IA02 (actualización)

### Policía Nacional: resolución por punto geográfico

El endpoint `POST /api/ia/sugerir-entidad` admite ahora `latitud` y `longitud` opcionales. Para categorías de seguridad/delitos exige ambas coordenadas y consulta el servicio oficial GEOMININTER:
- Capa 2 `Jurisdicciones`: geometría poligonal; realiza una consulta espacial `esriSpatialRelIntersects` con el punto de la denuncia.
- Capa 0 `Comisarias`: comprueba que el código `cod_cpnp` devuelto por el polígono exista también en la capa operativa publicada.
- Si faltan coordenadas, el servicio falla, la geometría no identifica exactamente una jurisdicción o el código no está en la capa operativa, devuelve `sugerida: false`.

Servicio y esquema de capas: https://geomininter.mininter.gob.pe/arcgis/rest/services/pnp/policia_nacional_peru/MapServer/layers. La capa de jurisdicciones publica geometría poligonal y campos `cod_cpnp`, `comisaria`, `departamento`, `provincia`, `distrito`; la capa de comisarías publica puntos y los mismos códigos de identificación. La línea base PNP 2026 declara 1,332 comisarías básicas operativas a nivel nacional (corte 15/01/2026): https://www.gob.pe/institucion/pnp/informes-publicaciones/7531378-linea-base-de-informacion-georreferenciada-de-comisarias-basicas-relacion-de-comisarias-operativas-a-nivel-nacional-2026. La verificación en el MapServer es una comprobación de presencia en la capa geográfica, no certifica por sí sola el estatus administrativo actual de cada dependencia; mantener revisión humana para casos sensibles.

Ejemplo de solicitud para seguridad:

```json
{
  "categoria": "Seguridad ciudadana",
  "departamento": "Lima",
  "provincia": "Lima",
  "distrito": "Miraflores",
  "titulo": "Robo en la vía pública",
  "descripcion": "Reporto un robo cerca del parque.",
  "latitud": -12.12,
  "longitud": -77.03
}
```

### Otras competencias

- **Limpieza y residuos:** municipalidad distrital, con base en el artículo 80 de la Ley 27972, para limpieza pública local: https://cdn.www.gob.pe/uploads/document/file/9972022/8133550-ley-organica-de-municipalidades-ley-n-27972.pdf.
- **Parques y áreas verdes:** municipalidad distrital solo cuando se trate de parque/jardín público de administración local; la gestión concreta del espacio debe confirmarse.
- **Transporte público urbano:** ATU tiene jurisdicción en toda la provincia de Lima y la Provincia Constitucional del Callao para el sistema integrado de transporte terrestre urbano de personas (Ley 30900, art. 3): https://www.leyes.congreso.gob.pe/documentos/2016_2021/adlp/normas_legales/30900_ley.pdf. La categoría general actual no separa ese supuesto de tránsito local, por lo que no se habilita en bloque.
- **Alumbrado público:** Osinergmin indica que las deficiencias deben denunciarse ante la empresa eléctrica que brinda el servicio: https://www.osinergmin.gob.pe/Paginas/Folletos/folletos/electricidad.html. Se mantiene bloqueado hasta integrar polígonos vigentes de concesión eléctrica.
- **Vialidad:** se mantiene bloqueada hasta identificar titularidad/jerarquía de la vía.

### Configuración y pruebas

- Variable opcional `PNP_MAPSERVER_URL`: permite configurar la URL base del MapServer oficial.
- Variable opcional `PNP_TIMEOUT_SECONDS`: timeout de consulta (por defecto 5 segundos).
- La consulta PNP usa la biblioteca estándar de Python, sin agregar dependencias de producción.
- Pruebas agregadas para exigir GPS, resolver polígono y confirmar el código en capa operativa, y abstenerse cuando no aparece en dicha capa.

### Despliegue

El repositorio define `render.yaml` con runtime Docker, `/health` y despliegue por commit. El push a esta rama puede desplegar automáticamente solo si el servicio Render está vinculado a esta rama y tiene auto-deploy habilitado. No se debe afirmar que está desplegado hasta comprobar un deploy exitoso y consultar el endpoint en el servicio correspondiente.
