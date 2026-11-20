# DenuPe — Backend de IA y resolución territorial

Microservicio REST que complementa la aplicación móvil [DenuPe](https://github.com/Zarabia-22/denupe). Está desarrollado con **Python y FastAPI** y reúne dos capacidades: recomendar una categoría para una denuncia a partir de su texto y ayudar a identificar entidades públicas relacionadas con la categoría y la ubicación GPS.

El backend devuelve **recomendaciones**, no presenta denuncias ni ejecuta una derivación administrativa. La persona usuaria conserva la selección manual y la decisión final. Cuando no existe evidencia suficiente, el servicio se abstiene en lugar de inventar una institución competente.

- **Framework:** FastAPI.
- **Servidor ASGI:** Uvicorn.
- **Clasificación:** scikit-learn (TF-IDF + regresión logística).
- **Validación de datos:** Pydantic.
- **Catálogo territorial:** InsForge (PostgreSQL y funciones RPC).
- **Datos geográficos:** servicios cartográficos oficiales consultados desde el backend.
- **Despliegue:** Docker y Render.
- **Pruebas:** pytest y HTTPX.

## 1. ¿Qué hace el backend?

1. Recibe el título y la descripción de una denuncia.
2. Normaliza el texto y analiza sus términos mediante un modelo de clasificación multiclase.
3. Recomienda una de las ocho categorías de DenuPe cuando la predicción supera los controles de calidad; si no, solicita mantener la selección manual.
4. Para las operaciones territoriales, recibe coordenadas GPS, resuelve el distrito y obtiene su UBIGEO mediante intersección geográfica.
5. Consulta en InsForge la matriz de ocho categorías asociada al UBIGEO y recupera el resolutor sectorial de la categoría.
6. Contrasta la información disponible en los catálogos y servicios geográficos para intentar identificar una institución concreta.
7. Si la institución no puede confirmarse de forma única, devuelve abstención o mantiene como alternativa la bandeja interna de revisión de competencia de DenuPe.

## 2. Arquitectura y flujo de funcionamiento

```text
                 Aplicación móvil DenuPe
                          |
                          v
                    API FastAPI
                          |
             +------------+-------------+
             |                          |
             v                          v
     Recomendación de categoría   Resolución territorial
             |                          |
             v                          v
     Normalización de texto       GPS (latitud/longitud)
             |                          |
             v                          v
       TF-IDF palabras y           Polígono distrital
       caracteres                  + UBIGEO
             |                          |
             v                          v
     Regresión logística          Catálogo InsForge
             |                    (matriz de 8 categorías)
             v                          |
     Umbrales y abstención              v
             |                    Resolutor sectorial
             |                          |
             +------------+-------------+
                          |
                          v
                Respuesta JSON a Flutter
             (sugerencia o selección manual)
```

### Componentes principales

| Archivo / módulo | Responsabilidad |
|---|---|
| `app/main.py` | Crea la aplicación FastAPI, configura middleware, ciclo de vida, CORS y rutas HTTP. |
| `app/schemas.py` | Define los contratos de entrada y salida con Pydantic: campos obligatorios, longitudes, rangos y validación de coordenadas. |
| `app/predictor.py` | Carga los artefactos del modelo y calcula la recomendación de categoría o la abstención. |
| `app/text_processing.py` | Normaliza el texto y calcula la cobertura del vocabulario del vectorizador. |
| `app/categorias.py` | Mantiene el catálogo y los códigos de las ocho categorías. |
| `app/entidades.py` | Contiene la lógica de directorio, resolución territorial y recomendación/listado de entidades. |
| `app/insforge_catalog.py` | Cliente HTTP del backend para consultar las funciones RPC del catálogo territorial InsForge. |
| `app/middleware.py` | Protege las solicitudes con límite de tamaño, cuota por IP, identificador de solicitud y cabeceras de seguridad. |
| `training/train.py` | Valida los datos, separa grupos, compara modelos, elige el umbral y genera los artefactos. |
| `models/` | Guarda el modelo, el vectorizador y las métricas del entrenamiento. |
| `data/` | Contiene los conjuntos de entrenamiento y los catálogos locales usados por la resolución de entidades. |
| `tests/` | Pruebas unitarias y de integración del modelo, API, catálogos y resolución territorial. |

## 3. Funciones principales y cómo trabajan

### 3.1 Recomendación de categoría

**Entrada:** título y descripción de la denuncia.

Flujo:

1. `DenunciaEntrada` valida que el título tenga entre 5 y 100 caracteres y la descripción entre 10 y 500. Se rechazan campos adicionales y textos vacíos.
2. `normalizar_texto()` estandariza el texto para reducir diferencias de mayúsculas, tildes, signos y variantes de escritura.
3. `cobertura_vocabulario()` mide qué proporción de términos puede reconocer el vocabulario entrenado.
4. El vectorizador TF-IDF transforma el texto en características numéricas de palabras y fragmentos de caracteres.
5. El clasificador de regresión logística calcula las puntuaciones para las ocho clases.
6. Se revisan la confianza, la diferencia entre las dos clases más probables, la cobertura y la cantidad mínima de términos reconocidos.
7. Si los controles no se cumplen, la API devuelve `sugerida: false` para que la persona elija manualmente.

Funciones y responsabilidades:

- `cargar_modelo()`: carga una sola vez los artefactos mediante caché y comprueba que correspondan a la versión 3 y a las ocho categorías.
- `sugerir_categoria(titulo, descripcion)`: ejecuta el flujo de predicción y construye la respuesta.
- `normalizar_texto(texto)`: prepara el texto para el vectorizador.
- `cobertura_vocabulario(texto, vectorizador)`: calcula la cobertura léxica y los términos reconocidos.

**Categorías admitidas:**

| Código | Nombre mostrado |
|---|---|
| `alumbrado` | Alumbrado público |
| `seguridad` | Seguridad ciudadana |
| `limpieza` | Limpieza y residuos |
| `agua` | Agua y saneamiento |
| `transito` | Tránsito y transporte |
| `areas_verdes` | Parques y áreas verdes |
| `infraestructura` | Vialidad e infraestructura |
| `otros` | Otros |

### 3.2 Resolución del distrito mediante GPS

La ubicación escrita por el cliente no se toma como autoridad territorial. Para las operaciones que requieren jurisdicción, el backend:

1. Recibe latitud y longitud.
2. Consulta la capa poligonal de límites distritales configurada para el servicio.
3. Busca el polígono que intersecta el punto.
4. Obtiene departamento, provincia, distrito y UBIGEO.
5. Rechaza el punto cuando no pertenece a un único polígono o no puede validarse.

La resolución GPS es una identificación operativa del distrito; no constituye una determinación legal de límites territoriales.

### 3.3 Consulta del catálogo territorial en InsForge

El módulo `app/insforge_catalog.py` realiza solicitudes HTTP autenticadas desde el servidor a las funciones RPC:

- `consultar_matriz_distrital_por_ubigeo(p_ubigeo)`: recupera la matriz del distrito y exige exactamente ocho categorías, una por código.
- `consultar_entidades_por_ubigeo(p_ubigeo, p_categoria_code)`: recupera el resolutor sectorial relacionado con una categoría y un UBIGEO; exige un único resultado.

Funciones internas:

- `_configuracion()`: valida que existan `INSFORGE_URL` e `INSFORGE_API_KEY` y que la clave tenga el formato administrativo esperado.
- `_rpc(nombre, argumentos)`: envía la solicitud HTTP a InsForge, aplica timeout y valida la estructura de la respuesta.
- `consultar_matriz_distrital(ubigeo)`: valida UBIGEO y la presencia de las ocho categorías.
- `consultar_resolutor_categoria(ubigeo, categoria_code)`: obtiene una única regla sectorial.

La integración falla de forma cerrada: ante credenciales ausentes, error de red, respuesta inválida o matriz incompleta, no sustituye el resultado con una asignación inventada.

### 3.4 Recomendación y listado de entidades

- `cargar_directorio()`: carga y valida el directorio local de instituciones.
- `sugerir_entidad(denuncia)`: aplica las reglas y fuentes disponibles para intentar identificar una entidad concreta.
- `listar_entidades_disponibles(...)`: construye las opciones que se pueden mostrar para una categoría y jurisdicción.
- `resolver_distrito_por_punto(latitud, longitud)`: resuelve la ubicación mediante el punto GPS.
- `catalogo_distrital_por_categoria(...)`: función auxiliar del módulo de entidades para consultar la configuración territorial por categoría.

El endpoint de recomendación de entidad exige GPS. El distrito, provincia y departamento efectivos se sustituyen por los obtenidos desde las coordenadas. Antes de devolver una institución, se comprueba que exista la matriz y el resolutor sectorial de InsForge.

**Abstención y revisión humana:** que InsForge relacione una categoría con un resolutor sectorial no demuestra por sí solo qué institución concreta debe recibir una denuncia. Si la evidencia local o geográfica no permite identificar una entidad única, el backend no la presenta como competente. `revision_competencia` es una bandeja interna de DenuPe, no una entidad pública.

## 4. API REST

La documentación interactiva se genera automáticamente con FastAPI.

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Comprueba que el servicio responde. |
| `GET` | `/health/ready` | Comprueba que el modelo y el directorio local pueden cargarse; devuelve metadatos técnicos. |
| `POST` | `/api/ia/sugerir-categoria` | Recomienda una categoría desde el título y la descripción. |
| `GET` | `/api/territorio/resolver-distrito` | Resuelve el distrito y valida su matriz mediante GPS. |
| `GET` | `/api/territorio/catalogo-distrital` | Devuelve la matriz de ocho categorías del distrito resuelto por GPS. |
| `POST` | `/api/ia/sugerir-entidad` | Intenta recomendar una entidad concreta según categoría, denuncia y GPS. |
| `GET` | `/api/entidades/disponibles` | Lista entidades disponibles para una categoría y ubicación GPS. |

### Ejemplo: sugerir categoría

Solicitud:

```http
POST /api/ia/sugerir-categoria
Content-Type: application/json
```

```json
{
  "titulo": "Baches en la pista principal",
  "descripcion": "El pavimento está dañado y hay varios huecos en la calzada."
}
```

Respuesta ilustrativa:

```json
{
  "sugerida": true,
  "categoria": "Vialidad e infraestructura",
  "confianza_modelo": 0.86,
  "cobertura_vocabulario": 0.78,
  "motivo": null
}
```

Los valores numéricos son ilustrativos. Cuando la predicción es insuficiente, la respuesta informa `sugerida: false`, sin categoría recomendada y con un motivo.

### Ejemplo: consultar matriz distrital

```http
GET /api/territorio/catalogo-distrital?latitud=-12.12&longitud=-77.03
```

La respuesta contiene los datos territoriales resueltos, la matriz de categorías, el total de categorías y la fuente del catálogo.

### Ejemplo: recomendar entidad

```http
POST /api/ia/sugerir-entidad
Content-Type: application/json
```

```json
{
  "categoria": "Limpieza y residuos",
  "departamento": "Lima",
  "provincia": "Lima",
  "distrito": "Miraflores",
  "titulo": "Basura acumulada en la avenida",
  "descripcion": "Hay bolsas de residuos y desperdicios sin recoger en la vía pública.",
  "latitud": -12.12,
  "longitud": -77.03
}
```

La ubicación GPS determina el distrito efectivo. La respuesta sigue el contrato `sugerida`, `entidad` y `motivo`. Si no se confirma una institución concreta, `sugerida` será `false` y se explicará por qué debe conservarse la selección manual.

### Códigos HTTP relevantes

- `200`: consulta procesada; la respuesta puede indicar abstención.
- `422`: parámetros, campos o coordenadas inválidos; también se usa cuando no se puede resolver un punto territorial.
- `503`: el catálogo InsForge no está configurado o no se pudo consultar.
- `413`: cuerpo HTTP mayor al límite permitido.
- `429`: se excedió la cuota de solicitudes.
- `500`: error interno no controlado.

## 5. Entrenamiento del modelo

El clasificador de categorías se entrena con **2.400 ejemplos sintéticos**, 300 por categoría. No son denuncias ciudadanas reales.

- Los datos se agrupan por incidente base y cada incidente tiene cinco variantes de redacción.
- La separación por grupos evita que variantes del mismo incidente se distribuyan entre entrenamiento, validación y prueba.
- Las particiones son 1.680 ejemplos de entrenamiento, 360 de validación y 360 de prueba.
- Se comparan cinco configuraciones: tres regresiones logísticas y dos modelos Naive Bayes.
- La selección del modelo y del umbral se realiza con validación; el conjunto de prueba se reserva para la evaluación final.
- El vectorizador combina TF-IDF de palabras (unigramas y bigramas) y caracteres (fragmentos de 3 a 5 caracteres).
- El modelo seleccionado en el benchmark documentado es regresión logística.

Los artefactos generados son:

- `models/modelo_categorias.joblib.gz`
- `models/vectorizador_tfidf.joblib.gz`
- `models/metricas.json`

**Interpretación de métricas:** los resultados de accuracy y F1 del repositorio corresponden exclusivamente al conjunto de prueba sintético. No demuestran el rendimiento sobre denuncias reales. Para evaluar el uso real se necesitan denuncias anonimizadas y etiquetadas, procedentes de fuentes independientes, y análisis por categoría, distrito, ambigüedad y casos fuera de dominio. Las puntuaciones de probabilidad no están calibradas.

### Reentrenar

Requiere Python 3.11:

```bash
python -m venv .venv
# Activar el entorno virtual según el sistema operativo
pip install -r requirements-dev.txt
python -m training.train
python -m pytest -q
```

El entrenamiento actualiza los tres artefactos indicados. El workflow de GitHub Actions de entrenamiento también automatiza el proceso cuando cambian los datos o el código de entrenamiento.

## 6. Tecnologías y dependencias

| Tecnología | Uso |
|---|---|
| Python 3.11 | Lenguaje y entorno de ejecución. |
| FastAPI | Definición de rutas REST, validación integrada y documentación OpenAPI. |
| Uvicorn | Servidor ASGI que ejecuta la aplicación. |
| Pydantic | Validación estricta de los contratos JSON. |
| scikit-learn | Vectorización TF-IDF y algoritmos de clasificación. |
| NumPy / SciPy | Operaciones numéricas y soporte científico de scikit-learn. |
| Joblib | Serialización y carga de los artefactos entrenados. |
| InsForge | Catálogo territorial y RPC de matriz/resolutor por UBIGEO. |
| pytest / HTTPX | Pruebas automatizadas y cliente HTTP de pruebas. |
| Docker | Empaquetado reproducible del servicio. |
| Render | Alojamiento del servicio web. |

Las dependencias de ejecución están fijadas en `requirements.txt`; las herramientas de desarrollo y pruebas se agregan en `requirements-dev.txt`.

## 7. Configuración y ejecución local

### Requisitos

- Python 3.11.
- Git.
- Acceso a InsForge para probar los endpoints territoriales y de entidades.

### Instalación

```bash
git clone https://github.com/Zarabia-22/denupe-ia-backend.git
cd denupe-ia-backend

python -m venv .venv
# Activar el entorno virtual
pip install -r requirements-dev.txt
```

### Variables de entorno

| Variable | Descripción |
|---|---|
| `INSFORGE_URL` | URL base del proyecto InsForge. |
| `INSFORGE_API_KEY` | Clave administrativa de InsForge. Debe permanecer solo en el servidor. |
| `INSFORGE_TIMEOUT_SECONDS` | Timeout de RPC InsForge; valor predeterminado: 8 segundos. |
| `DISTRITOS_MAPSERVER_URL` | URL del servicio cartográfico de límites distritales, si se desea sobrescribir el valor predeterminado. |
| `DISTRITOS_TIMEOUT_SECONDS` | Timeout de la consulta geográfica distrital. |
| `PNP_MAPSERVER_URL` | URL base del servicio geográfico PNP, si se configura. |
| `PNP_TIMEOUT_SECONDS` | Timeout de consulta PNP; valor predeterminado documentado: 5 segundos. |
| `OSINERGMIN_MAPSERVER_URL` | URL del servicio geográfico de concesiones eléctricas, si se configura. |
| `OSINERGMIN_TIMEOUT_SECONDS` | Timeout de consulta OSINERGMIN; valor predeterminado documentado: 5 segundos. |
| `MAX_REQUEST_BODY_BYTES` | Tamaño máximo del cuerpo HTTP; predeterminado: 16.384 bytes. |
| `RATE_LIMIT_PER_MINUTE` | Máximo de solicitudes por IP y minuto; predeterminado: 120 por proceso. |
| `CORS_ORIGINS` | Lista separada por comas de orígenes web permitidos. |

Configura las variables privadas en el entorno local o en el panel de Render. **Nunca publiques `INSFORGE_API_KEY`, ni la incluyas en Flutter, en el repositorio o en capturas.**

### Ejecutar

```bash
uvicorn app.main:app --reload
```

Por defecto, la API estará disponible en `http://127.0.0.1:8000`.

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Salud: `http://127.0.0.1:8000/health`

### Ejecutar pruebas

```bash
python -m pytest -q
```

## 8. Despliegue con Docker y Render

El repositorio incluye `Dockerfile` y `render.yaml`.

El contenedor:

1. Parte de una imagen Python 3.11 slim.
2. Instala las dependencias de producción.
3. Copia los módulos de la aplicación, los artefactos del modelo y los catálogos de datos.
4. Inicia Uvicorn en el puerto asignado por Render.
5. Expone `/health` como health check.

Para desplegar, configura las variables de entorno privadas en Render y vincula el servicio con la rama correspondiente. La existencia de `render.yaml` no garantiza por sí sola que un despliegue esté activo; debe verificarse el estado del deploy y consultar el endpoint del servicio.

## 9. Seguridad, privacidad y limitaciones

- El middleware limita el cuerpo de cada solicitud (16 KiB por defecto) y aplica una cuota de 120 solicitudes por minuto y dirección IP por proceso.
- Las respuestas incluyen `X-Request-ID` y cabeceras como `X-Content-Type-Options`, `Referrer-Policy` y `Cache-Control: no-store`.
- El backend no registra deliberadamente el título, la descripción, las coordenadas ni datos personales de la denuncia.
- El limitador mantiene contadores en memoria. Para varias instancias debe sustituirse por Redis o un gateway gestionado.
- **La API no implementa autenticación JWT ni valida la identidad del ciudadano.** CORS no reemplaza autenticación y una clave incluida en una app móvil puede extraerse. Antes de exponerla públicamente se debe integrar la validación de tokens del proveedor de identidad o un gateway autenticado.
- La clave administrativa de InsForge solo debe utilizarse desde el backend y guardarse como secreto.
- Los artefactos Joblib deben proceder de una fuente confiable, ya que su deserialización puede ejecutar código.
- Los resultados de categoría y entidad son recomendaciones. No sustituyen la revisión de competencia ni ejecutan una derivación administrativa.
- La cobertura y la precisión de las entidades dependen de la vigencia y completitud de los directorios y servicios geográficos disponibles. Una matriz territorial completa no equivale a contar con una institución concreta verificada para cada categoría.

## 10. Integración con DenuPe

La aplicación Flutter consume el backend mediante su capa de servicios. La URL base se configura con `DENUPE_IA_URL` en el cliente móvil. El backend devuelve códigos/nombres de categoría y contratos de recomendación que la aplicación presenta al ciudadano.

La selección manual permanece disponible cuando el servicio no responde, la predicción es ambigua, no existe cobertura territorial suficiente o no se puede confirmar una entidad pública concreta.

Repositorio de la aplicación: https://github.com/Zarabia-22/denupe
