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

Se incorpora el endpoint independiente `POST /api/ia/sugerir-entidad`. Recibe la categoría, departamento, provincia, distrito, título y descripción de la denuncia, además de latitud y longitud cuando la competencia requiere resolver una jurisdicción geográfica. Las municipalidades se consultan en `data/entidades_publicas.json`; las comisarías PNP y las empresas concesionarias eléctricas se resuelven mediante consultas espaciales a los servicios oficiales de GEOMININTER y OSINERGMIN, respectivamente. Si no existe evidencia territorial y temática suficiente, el servicio se abstiene.

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

La respuesta contiene `sugerida`, `entidad` (identificador, nombre, tipo, datos de contacto disponibles y ámbito territorial) y `motivo`. Si no hay coincidencia o existen candidatos equivalentes, devuelve el destino interno `revision_competencia`; no lo presenta como institución pública externa. La selección y derivación final deben seguir bajo control del ciudadano o del personal responsable.

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

Se incorpora `data/matriz_competencias.json`. Se habilitan recomendaciones para **Limpieza y residuos** y **Parques y áreas verdes** a la municipalidad distrital correspondiente, bajo las condiciones de la matriz; **Seguridad ciudadana / delitos** mediante jurisdicción PNP geográfica; **Alumbrado público** mediante concesión eléctrica OSINERGMIN; y la subcategoría explícita **Transporte público urbano de pasajeros** hacia ATU, únicamente para las provincias de Lima y Callao. La categoría genérica `Tránsito y transporte` no se deriva automáticamente.

Se mantienen bloqueadas las recomendaciones automáticas para:
- **Alumbrado público:** se resuelve mediante GPS y consulta espacial al polígono oficial de concesión eléctrica de OSINERGMIN (capa 33). Solo se recomienda cuando la coordenada intersecta exactamente un polígono y su código `CODEMP` está reconocido.
- **Transporte público urbano de pasajeros:** la subcategoría explícita se recomienda a ATU únicamente en las provincias de Lima y Callao, según la Ley 30900. La categoría genérica `Tránsito y transporte` continúa en abstención porque mezcla transporte público, señalización, semáforos y tránsito local.
- **Vialidad e infraestructura:** el D.S. N.° 015-2024-MTC asigna la Red Vial Nacional al MTC, la Red Vial Departamental/Regional a los gobiernos regionales y la Red Vial Provincial/Urbana a municipalidades provinciales/distritales. No se recomienda todavía una entidad porque falta integrar y validar una capa consultable que identifique el tramo exacto y posibles delegaciones o concesiones.
- **Seguridad / PNP:** se consulta la capa 2 `Jurisdicciones` (polígonos) para resolver espacialmente el punto de la denuncia y la capa 0 `Comisarias` (puntos) para comprobar la presencia del código devuelto. Las 46 referencias históricas del DU 085-2020 no se habilitan para asignación. La comprobación geográfica no certifica por sí sola la situación administrativa vigente de la dependencia; se mantiene revisión humana.

Fuentes normativas y de datos:
- Ley Orgánica de Municipalidades N.° 27972: https://cdn.www.gob.pe/uploads/document/file/2685861/Ley%20Organica%20de%20Municipalidades.pdf
- Capa geográfica de comisarías MININTER: https://geomininter.mininter.gob.pe/arcgis/rest/services/pnp/policia_nacional_peru/MapServer/0
- Padrón de comisarías operativas PNP 2026: https://www.gob.pe/institucion/pnp/informes-publicaciones/7531378-linea-base-de-informacion-georreferenciada-de-comisarias-basicas-relacion-de-comisarias-operativas-a-nivel-nacional-2026
- Comisarías PNP con demarcación territorial: https://www.gob.pe/institucion/pnp/informes-publicaciones/7173744-comisarias-de-la-policia-nacional-del-peru-con-demarcacion-territorial

Cuando no se identifica una institución pública única, el endpoint propone el destino interno `revision_competencia` (Bandeja de revisión de competencia de DenuPe). Este receptor permite que las denuncias válidas no queden sin destino, pero **no equivale a identificar a la entidad pública final**. El personal debe revisar y reasignar cuando corresponda.

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

### Agua y saneamiento (SEDAPAL)

Para la categoría **Agua y saneamiento**, el motor puede recomendar SEDAPAL cuando el distrito pertenece al ámbito documentado de Lima/Callao y el texto describe una incidencia de red (corte, fuga, tubería, aniego, desagüe o alcantarillado). La cobertura efectiva del predio y su conexión deben confirmarse con SEDAPAL; la recomendación no presume que todos los hogares estén conectados.

Fuentes: [Informe Defensorial sobre SEDAPAL](https://www.defensoria.gob.pe/wp-content/uploads/2025/03/Informe_Defensorial_Agua19.03.pdf) (ámbito de administración de SEDAPAL, 50 distritos de Lima y Callao) y [FONAFE](https://www.fonafe.gob.pe/empresasdelacorporacion/sedapalsa) (perfil institucional de SEDAPAL).

### Otras competencias

- **Limpieza y residuos:** municipalidad distrital, con base en el artículo 80 de la Ley 27972, para limpieza pública local: https://cdn.www.gob.pe/uploads/document/file/9972022/8133550-ley-organica-de-municipalidades-ley-n-27972.pdf.
- **Parques y áreas verdes:** municipalidad distrital solo cuando se trate de parque/jardín público de administración local; la gestión concreta del espacio debe confirmarse.
- **Transporte público urbano:** la ATU tiene jurisdicción en Lima y Callao para el sistema integrado de transporte terrestre urbano de personas (Ley 30900): https://www.leyes.congreso.gob.pe/documentos/2016_2021/adlp/normas_legales/30900_ley.pdf. La implementación habilita exclusivamente la subcategoría `Transporte público urbano de pasajeros`; no activa la categoría genérica `Tránsito y transporte`.
- **Alumbrado público:** OSINERGMIN indica que las deficiencias deben denunciarse ante la empresa eléctrica que brinda el servicio. La capa 33 `Área de Concesión` del servicio geográfico oficial publica polígonos y el dominio de códigos de empresa: https://gisem.osinergmin.gob.pe/serverosih/rest/services/Electricidad/ELECTRICIDAD/MapServer/33. Guía de atención: https://www.osinergmin.gob.pe/Paginas/Folletos/folletos/electricidad.html.
- **Vialidad:** el D.S. N.° 015-2024-MTC establece la distribución de responsabilidades por jerarquía vial (MTC para red nacional, gobiernos regionales para red departamental y gobiernos locales para red provincial/urbana): https://busquedas.elperuano.pe/dispositivo/NL/2325194-1. IDEP registra capas MTC 2025 para redes nacional, departamental y vecinal, pero varias solo ofrecen WMS; antes de automatizar la recomendación se debe confirmar una fuente de consulta de entidades/tramos con atributos y vigencia, además de delegaciones y concesiones: https://www.geoidep.gob.pe/catalogo-nacional-de-servicios-web/servicio-de-visualizacion-wms.

### Configuración y pruebas

- Variable opcional `PNP_MAPSERVER_URL`: permite configurar la URL base del MapServer oficial.
- Variable opcional `PNP_TIMEOUT_SECONDS`: timeout de consulta (por defecto 5 segundos).
- La consulta PNP y la consulta de concesiones eléctricas usan la biblioteca estándar de Python, sin agregar dependencias de producción.
- `OSINERGMIN_MAPSERVER_URL`: permite configurar la URL base del servicio oficial de concesiones eléctricas (opcional).
- `OSINERGMIN_TIMEOUT_SECONDS`: timeout de consulta OSINERGMIN (por defecto 5 segundos).
- Pruebas agregadas para exigir GPS, resolver jurisdicción PNP por polígono, confirmar el código en la capa operativa, resolver la concesionaria eléctrica por el polígono de OSINERGMIN, validar ATU en Lima y Callao y abstenerse ante categoría genérica, ámbito territorial incorrecto, ausencia de coordenadas, ambigüedad, códigos desconocidos o errores del servicio.

### Despliegue

El repositorio define `render.yaml` con runtime Docker, `/health` y despliegue por commit. El push a esta rama puede desplegar automáticamente solo si el servicio Render está vinculado a esta rama y tiene auto-deploy habilitado. No se debe afirmar que está desplegado hasta comprobar un deploy exitoso y consultar el endpoint en el servicio correspondiente.


## Robustez del PMV2

### Validación y límites HTTP
- Los contratos rechazan campos adicionales, textos vacíos y coordenadas incompletas o fuera de rango.
- El middleware limita el tamaño real del cuerpo HTTP (por defecto 16 KiB), aplica una cuota por IP (120 solicitudes/minuto por proceso) y agrega identificador de solicitud y cabeceras de seguridad.
- Variables: `MAX_REQUEST_BODY_BYTES` y `RATE_LIMIT_PER_MINUTE`.
- Las consultas espaciales a MININTER y OSINERGMIN tienen timeout configurable, limitan la consulta a dos resultados y aceptan respuestas JSON de hasta 1 MiB; ante error, estructura inválida o ambigüedad, el recomendador se abstiene.
- El limitador incluido mantiene contadores en memoria y es adecuado únicamente para una instancia. En despliegues con varias instancias debe trasladarse a Redis o a un gateway gestionado; no se debe confiar en `X-Forwarded-For` sin configurar proxies de confianza.

### Salud y diagnóstico
- `GET /health` conserva el contrato existente para Render.
- `GET /health/ready` comprueba que el modelo de ocho categorías está cargado y expone solo metadatos técnicos.
- Cada respuesta incluye `X-Request-ID`; no se registran deliberadamente títulos, descripciones, coordenadas ni datos personales.

### Catálogos
Los archivos JSON se validan al cargarse: estructura, campos obligatorios, tipos, identificadores duplicados y coherencia entre entidades habilitadas y competencias verificadas. Un catálogo corrupto produce un error explícito, nunca una recomendación silenciosamente incorrecta.

### Seguridad pendiente antes de exposición pública
Este backend no valida identidad de usuario ni JWT. CORS no es autenticación y una clave estática embebida en Flutter puede extraerse. Antes de abrir el endpoint públicamente, integrar validación de tokens del proveedor de identidad de DenuPe o colocar un gateway que autentique y limite tráfico. No habilitar derivación automática: las respuestas siguen siendo sugerencias y requieren decisión humana.


## Catálogo preconfigurado por distrito y resolución GPS

La cobertura inicial mantiene los **50 distritos de Lima Metropolitana y Callao**. El endpoint GET /api/territorio/catalogo-distrital expone una matriz de las ocho categorías para el distrito solicitado. Puede recibir el distrito administrativo o, preferentemente, latitud y longitud; cuando se envían coordenadas, el backend resuelve el distrito por intersección del punto con la capa poligonal distrital (capa 3) y valida el UBIGEO contra el catálogo local. El GPS prevalece sobre cualquier distrito escrito por el cliente.

Ejemplos:

```http
GET /api/territorio/resolver-distrito?latitud=-12.12&longitud=-77.03
GET /api/territorio/catalogo-distrital?latitud=-12.12&longitud=-77.03
GET /api/territorio/catalogo-distrital?departamento=Lima&provincia=Lima&distrito=Miraflores
```

La matriz configura las rutas para todas las categorías: municipalidad para limpieza y parques bajo sus condiciones locales; SEDAPAL para agua/saneamiento dentro del ámbito documentado de Lima y Callao; resolución espacial por GPS para PNP y concesionarias eléctricas; y revisión de competencia para tránsito genérico, vialidad sin titularidad de tramo verificada y Otros. Una ruta preconfigurada no significa que cualquier entidad sea competente para cualquier incidente: los casos sin prueba territorial o sectorial suficiente permanecen en revisión.

Fuente de límites distritales: servicio cartográfico del Estado, capa 3 Límite Distrital, atributos UBIGEO, NOMBDEP, NOMBPROV y NOMBDIST: https://ws.mineco.gob.pe/server/rest/services/cartografia_base_limites/MapServer/layers. La fuente publica polígonos en WGS84 (EPSG:4326). La plataforma Geo Perú advierte que los límites mostrados son referenciales y atribuidos al INEI; para controversias de demarcación debe prevalecer la delimitación oficial inscrita en RENLIM. La resolución GPS del PMV es una identificación operativa de distrito, no una determinación legal de límites.

Variables opcionales:
- DISTRITOS_MAPSERVER_URL: URL base del MapServer de límites distritales.
- DISTRITOS_TIMEOUT_SECONDS: timeout de consulta (por defecto 5 segundos).

Si la coordenada no cae en un único polígono, el UBIGEO no es válido, el servicio no responde o el distrito no forma parte de los 50 configurados, el endpoint no inventa el distrito y devuelve un error explícito para que la app solicite corrección o selección manual.
