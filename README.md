# DenuPe — Backend de IA y resolución territorial

<p align="center">
  <strong>Microservicio REST para clasificación de denuncias y apoyo a la identificación territorial de entidades públicas.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Modelo-categor%C3%ADas%20v3-6A5ACD" alt="Modelo categorías v3" />
  <img src="https://img.shields.io/badge/Despliegue-Render-46E3B7?logo=render&logoColor=black" alt="Render" />
  <img src="https://img.shields.io/badge/Licencia-no%20especificada-lightgrey" alt="Licencia no especificada" />
</p>

## 1. Descripción

DenuPe Backend es un servicio desarrollado con **Python y FastAPI** que complementa la aplicación móvil [DenuPe](https://github.com/Zarabia-22/denupe). Recomienda una categoría a partir del texto de una denuncia y ayuda a resolver el distrito y la posible entidad receptora usando la ubicación GPS, un catálogo territorial y fuentes geográficas.

El servicio entrega sugerencias explicables y puede abstenerse cuando la evidencia no es suficiente. **No presenta denuncias ni realiza derivaciones administrativas**: la selección manual y la decisión final permanecen bajo control de la persona usuaria o del personal responsable.

## 2. Demo y apoyo visual

- **API desplegada — entorno de pruebas:** [https://denupe-ia-backend-hu-ia02-test.onrender.com](https://denupe-ia-backend-hu-ia02-test.onrender.com)
- **Swagger UI:** [Explorar y probar los endpoints](https://denupe-ia-backend-hu-ia02-test.onrender.com/docs)
- **Estado del servicio:** [Health check](https://denupe-ia-backend-hu-ia02-test.onrender.com/health)
- **Código fuente:** [Zarabia-22/denupe-ia-backend](https://github.com/Zarabia-22/denupe-ia-backend)
- **Aplicación cliente:** [Zarabia-22/denupe](https://github.com/Zarabia-22/denupe)

El enlace corresponde al servicio de pruebas HU-IA02; no debe interpretarse como una URL de producción ni como garantía de disponibilidad permanente. La documentación Swagger permite enviar solicitudes de ejemplo y revisar los esquemas de entrada y salida. No se incluyen capturas ni GIF porque el backend es una API sin interfaz gráfica propia.

## 3. Tabla de contenidos

- [Descripción](#1-descripción)
- [Demo y apoyo visual](#2-demo-y-apoyo-visual)
- [Tabla de contenidos](#3-tabla-de-contenidos)
- [Características principales](#4-características-principales)
- [Stack tecnológico](#5-stack-tecnológico)
- [Prerrequisitos](#6-prerrequisitos)
- [Instalación y configuración](#7-instalación-y-configuración)
- [Ejemplos de uso](#8-ejemplos-de-uso)
- [Roadmap y limitaciones conocidas](#9-roadmap-y-limitaciones-conocidas)
- [Contribución y licencia](#10-contribución-y-licencia)
- [Arquitectura y referencia técnica](#11-arquitectura-y-referencia-técnica)

## 4. Características principales

### Clasificación inteligente de denuncias
- Recibe título y descripción y recomienda una de las ocho categorías de DenuPe.
- Normaliza el texto y utiliza TF-IDF de palabras y caracteres con un clasificador de regresión logística.
- Evalúa confianza, margen entre clases y cobertura del vocabulario antes de emitir una sugerencia.
- Se abstiene si la entrada es ambigua, contiene vocabulario insuficiente o no supera los controles establecidos.

### Resolución territorial y catálogo
- Resuelve el distrito desde coordenadas GPS mediante intersección con límites geográficos.
- Obtiene departamento, provincia, distrito y UBIGEO a partir del punto; no confía en los datos territoriales escritos por el cliente como fuente de autoridad.
- Consulta en InsForge la matriz de ocho categorías por distrito y el resolutor sectorial asociado.
- Expone el catálogo distrital y las entidades disponibles para una categoría y ubicación.

### Recomendación de entidades
- Contrasta las reglas territoriales con directorios locales y servicios cartográficos disponibles.
- Integra verificaciones geográficas para jurisdicciones PNP y concesiones eléctricas, además de reglas sectoriales documentadas.
- Devuelve una institución concreta solo cuando la evidencia disponible permite identificarla de forma suficiente y única.
- Cuando no puede confirmarla, devuelve abstención y conserva la selección manual. `revision_competencia` es una bandeja interna de DenuPe, no una institución pública.

### Operación y protección básica
- Validación estricta de solicitudes mediante Pydantic.
- Límite de tamaño de cuerpo HTTP, cuota de solicitudes por IP, identificador de solicitud y cabeceras de seguridad.
- Pruebas automatizadas con pytest y HTTPX.
- Empaquetado mediante Docker y configuración de despliegue para Render.

### Ocho categorías admitidas

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

Los códigos deben coincidir con el catálogo usado por la aplicación y la base de datos. La existencia de una categoría en la matriz territorial no significa que exista una entidad concreta verificada para derivar cualquier denuncia de esa categoría.

## 5. Stack tecnológico

| Tecnología | Uso |
|---|---|
| Python 3.11 | Lenguaje y entorno de ejecución. |
| FastAPI | API REST y documentación OpenAPI/Swagger. |
| Uvicorn | Servidor ASGI. |
| Pydantic | Validación de los contratos JSON. |
| scikit-learn | TF-IDF y clasificación multiclase. |
| NumPy / SciPy | Operaciones numéricas y soporte científico. |
| Joblib | Carga de los artefactos del modelo. |
| InsForge / PostgreSQL | Catálogo territorial y funciones RPC. |
| Servicios geográficos oficiales | Resolución espacial de límites y jurisdicciones. |
| pytest / HTTPX | Pruebas unitarias y de integración. |
| Docker | Construcción de la imagen del servicio. |
| Render | Alojamiento del servicio web. |
| GitHub Actions | Automatización de validaciones y entrenamiento. |

Las versiones instaladas se encuentran fijadas en `requirements.txt` y `requirements-dev.txt`.

## 6. Prerrequisitos

Para ejecutar el proyecto localmente se necesita:

- Python **3.11**.
- Git.
- pip y soporte para entornos virtuales de Python.
- Acceso a un proyecto InsForge para probar las funciones territoriales.
- Credencial administrativa de InsForge disponible como secreto del backend, no en la aplicación Flutter.
- Conexión a internet para consultar los servicios geográficos externos.

Para ejecutar el contenedor también se necesita Docker. No es necesario configurar InsForge para ejecutar únicamente el endpoint de clasificación de categorías; sí es necesario para los endpoints que consultan la matriz territorial.

## 7. Instalación y configuración

### 7.1 Clonar el repositorio

```bash
git clone https://github.com/Zarabia-22/denupe-ia-backend.git
cd denupe-ia-backend
```

### 7.2 Crear y activar el entorno virtual

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 7.3 Instalar dependencias

Para desarrollo y pruebas:

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Para instalar solo las dependencias de ejecución:

```bash
pip install -r requirements.txt
```

### 7.4 Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto para tu entorno local. No lo subas al repositorio. Exporta las variables en la terminal o utiliza el mecanismo de configuración local que tengas habilitado; el servicio lee las variables del entorno del proceso.

| Variable | Descripción |
|---|---|
| `INSFORGE_URL` | URL base del proyecto InsForge. |
| `INSFORGE_API_KEY` | Clave administrativa usada exclusivamente desde el servidor. |
| `INSFORGE_TIMEOUT_SECONDS` | Tiempo máximo de espera para RPC de InsForge; valor predeterminado: 8 segundos. |
| `DISTRITOS_MAPSERVER_URL` | URL del servicio cartográfico de límites distritales, si se desea sobrescribir el valor predeterminado. |
| `DISTRITOS_TIMEOUT_SECONDS` | Tiempo máximo de espera de la consulta geográfica distrital. |
| `PNP_MAPSERVER_URL` | URL base del servicio geográfico PNP, si se configura. |
| `PNP_TIMEOUT_SECONDS` | Tiempo máximo de espera de la consulta PNP. |
| `OSINERGMIN_MAPSERVER_URL` | URL del servicio geográfico de concesiones eléctricas, si se configura. |
| `OSINERGMIN_TIMEOUT_SECONDS` | Tiempo máximo de espera de la consulta OSINERGMIN. |
| `MAX_REQUEST_BODY_BYTES` | Tamaño máximo del cuerpo HTTP; predeterminado: 16.384 bytes. |
| `RATE_LIMIT_PER_MINUTE` | Máximo de solicitudes por IP y minuto; predeterminado: 120 por proceso. |
| `CORS_ORIGINS` | Orígenes web permitidos, separados por comas. |

Configura únicamente las variables necesarias para los servicios que vayas a utilizar. Los valores predeterminados de las URLs geográficas están definidos por el código. **Nunca publiques `INSFORGE_API_KEY`, no la incluyas en Flutter y no la escribas en capturas, logs o ejemplos.**

### 7.5 Ejecutar el servidor

```bash
uvicorn app.main:app --reload
```

La API estará disponible normalmente en `http://127.0.0.1:8000`.

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json
- Salud: http://127.0.0.1:8000/health

### 7.6 Ejecutar las pruebas

```bash
python -m pytest -q
```

## 8. Ejemplos de uso

### 8.1 Comprobar el servicio

```bash
curl http://127.0.0.1:8000/health
```

### 8.2 Recomendar una categoría

```bash
curl -X POST "http://127.0.0.1:8000/api/ia/sugerir-categoria" \
  -H "Content-Type: application/json" \
  -d '{
    "titulo": "Baches en la pista principal",
    "descripcion": "El pavimento está dañado y hay varios huecos en la calzada."
  }'
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

Los valores numéricos son ejemplos de formato, no una predicción garantizada. Si la evidencia no supera los umbrales, el servicio devuelve `sugerida: false` y un motivo para mantener la selección manual.

### 8.3 Resolver distrito y consultar la matriz territorial

```bash
curl "http://127.0.0.1:8000/api/territorio/catalogo-distrital?latitud=-12.12&longitud=-77.03"
```

La ubicación se utiliza para identificar el polígono distrital y obtener el UBIGEO. El servicio consulta la matriz de categorías de ese distrito en InsForge.

### 8.4 Recomendar una entidad

```bash
curl -X POST "http://127.0.0.1:8000/api/ia/sugerir-entidad" \
  -H "Content-Type: application/json" \
  -d '{
    "categoria": "Limpieza y residuos",
    "departamento": "Lima",
    "provincia": "Lima",
    "distrito": "Miraflores",
    "titulo": "Basura acumulada en la avenida",
    "descripcion": "Hay bolsas de residuos y desperdicios sin recoger en la vía pública.",
    "latitud": -12.12,
    "longitud": -77.03
  }'
```

El distrito, provincia y departamento efectivos se resuelven desde el GPS. La respuesta contiene `sugerida`, `entidad` y `motivo`. Si no se identifica una institución concreta de manera suficiente, el servicio se abstiene; no se debe interpretar la abstención como una derivación a una entidad pública.

### 8.5 Endpoints disponibles

| Método | Endpoint | Propósito |
|---|---|---|
| `GET` | `/health` | Estado básico del servicio. |
| `GET` | `/health/ready` | Disponibilidad del modelo y directorio local. |
| `POST` | `/api/ia/sugerir-categoria` | Recomendación de categoría desde texto. |
| `GET` | `/api/territorio/resolver-distrito` | Resolución de distrito mediante GPS. |
| `GET` | `/api/territorio/catalogo-distrital` | Matriz de categorías del distrito. |
| `POST` | `/api/ia/sugerir-entidad` | Recomendación de entidad con GPS. |
| `GET` | `/api/entidades/disponibles` | Listado de opciones para categoría y ubicación. |

Códigos HTTP relevantes: `200` solicitud procesada (puede incluir abstención), `413` cuerpo demasiado grande, `422` datos inválidos o punto no resoluble, `429` límite de solicitudes excedido, `503` catálogo InsForge no disponible y `500` error interno.

## 9. Roadmap y limitaciones conocidas

### Próximas mejoras
- Incorporar un conjunto de denuncias reales anonimizadas y etiquetadas para evaluar el clasificador con datos independientes.
- Medir el rendimiento por categoría, distrito, ambigüedad y casos fuera del dominio de entrenamiento.
- Calibrar las probabilidades y revisar periódicamente los umbrales de abstención.
- Ampliar y verificar los directorios de entidades y sus competencias con fuentes oficiales vigentes.
- Completar la identificación de la entidad competente para las categorías y subcategorías que aún requieren revisión manual.
- Incorporar autenticación de solicitudes mediante tokens del proveedor de identidad o un gateway antes de exponer la API públicamente.
- Evaluar un limitador distribuido para despliegues con varias instancias.

### Limitaciones conocidas
- El entrenamiento actual utiliza **2.400 ejemplos sintéticos** (300 por categoría), no denuncias reales.
- Las métricas del benchmark sintético no demuestran la precisión del modelo en producción. Las probabilidades de `predict_proba` no están calibradas.
- La matriz de InsForge relaciona ocho categorías con resolutores sectoriales por distrito, pero esa relación no prueba por sí sola qué institución concreta debe recibir cada denuncia.
- El directorio municipal local documentado tiene cobertura inicial de 50 distritos de Lima Metropolitana y Callao. La matriz territorial nacional no equivale a un directorio nacional completo de instituciones concretas.
- Algunas competencias solo se recomiendan bajo condiciones específicas. Por ejemplo, transporte público urbano de pasajeros se distingue de la categoría genérica de tránsito y transporte; vialidad e infraestructura puede requerir identificar primero la jerarquía y el tramo de la vía.
- La API no implementa autenticación JWT propia. CORS no es un mecanismo de autenticación y una clave incluida en una aplicación móvil puede extraerse.
- El limitador actual mantiene contadores en memoria y opera por proceso; no comparte estado entre instancias.

## 10. Contribución y licencia

### Contribuir
Se aceptan propuestas de mejora, correcciones y reportes de errores mediante GitHub:

1. Revisa los issues existentes y abre uno nuevo si el problema no está reportado.
2. Crea una rama descriptiva desde la rama de desarrollo vigente, por ejemplo `feat/nueva-validacion`, `fix/error-resolucion-gps` o `docs/actualizar-guia`.
3. Realiza cambios acotados y agrega o actualiza pruebas para el comportamiento modificado.
4. Ejecuta `python -m pytest -q` y verifica que no se expongan secretos ni datos personales.
5. Abre un Pull Request con resumen, justificación, pruebas ejecutadas, posibles impactos y evidencia relevante.

Los cambios que afecten competencias públicas, fuentes geográficas o reglas de derivación deben incluir la fuente oficial, fecha de consulta, ámbito territorial y casos de abstención. No se deben añadir instituciones o competencias sin evidencia verificable.

- **Reportar errores:** [GitHub Issues](https://github.com/Zarabia-22/denupe-ia-backend/issues)
- **Proponer cambios:** [Pull Requests](https://github.com/Zarabia-22/denupe-ia-backend/pulls)

### Licencia
En la rama `main` no se encontró un archivo `LICENSE`. Por tanto, el repositorio **no declara actualmente una licencia de código abierto**. No debe asumirse que el código está bajo MIT, GPL u otra licencia. Antes de reutilizarlo, redistribuirlo o incorporarlo en otro producto, solicita autorización al titular o acuerda y agrega una licencia explícita.

## 11. Arquitectura y referencia técnica

### Flujo general

```text
                 Aplicación móvil DenuPe
                          |
                          v
                       FastAPI
                          |
             +------------+-------------+
             |                          |
             v                          v
     Sugerencia de categoría     Resolución territorial
             |                          |
       Normalización de texto      Coordenadas GPS
             |                          |
       TF-IDF palabras y            Polígono distrital
       caracteres                   + UBIGEO
             |                          |
       Regresión logística         Catálogo InsForge
             |                     (matriz por categoría)
       Umbrales y abstención             |
             |                     Resolutor sectorial
             +------------+-------------+
                          |
                    Respuesta JSON
```

### Módulos principales

| Archivo | Responsabilidad |
|---|---|
| `app/main.py` | Inicialización de FastAPI, middleware y rutas. |
| `app/schemas.py` | Contratos y validaciones Pydantic. |
| `app/predictor.py` | Carga del modelo y recomendación de categoría. |
| `app/text_processing.py` | Normalización y cobertura del vocabulario. |
| `app/categorias.py` | Códigos y nombres de las ocho categorías. |
| `app/entidades.py` | Directorios, resolución territorial y recomendación/listado de entidades. |
| `app/insforge_catalog.py` | Cliente RPC para el catálogo territorial InsForge. |
| `app/middleware.py` | Límite de cuerpo, cuota por IP, request ID y cabeceras. |
| `training/train.py` | Preparación de datos, comparación y entrenamiento del modelo. |
| `models/` | Modelo, vectorizador y métricas. |
| `data/` | Datos sintéticos y catálogos locales. |
| `tests/` | Pruebas de API, modelo, catálogos y resolución territorial. |

### Modelo de clasificación

El conjunto de entrenamiento contiene 2.400 ejemplos sintéticos, 300 por categoría, derivados de 480 casos base con cinco variantes de redacción cada uno. La división agrupada y estratificada utiliza 1.680 ejemplos para entrenamiento, 360 para validación y 360 para prueba. Se comparan cinco configuraciones de modelos; la selección se realiza con validación y el conjunto de prueba se reserva para evaluación.

El benchmark documentado reporta **96,67 % de accuracy y 96,66 % de F1 macro** en el conjunto de prueba sintético (348 aciertos de 360). El filtro de recomendación emitió 343 sugerencias y acertó 340 de ellas. Estas cifras describen exclusivamente ese benchmark artificial; no son una garantía de precisión sobre denuncias reales.

Artefactos generados:
- `models/modelo_categorias.joblib.gz`
- `models/vectorizador_tfidf.joblib.gz`
- `models/metricas.json`

Para reentrenar:

```bash
pip install -r requirements-dev.txt
python -m training.train
python -m pytest -q
```

### Catálogo territorial y abstención

Para operaciones territoriales, el backend resuelve las coordenadas sobre el servicio de límites distritales, obtiene el UBIGEO y consulta en InsForge las funciones RPC `consultar_matriz_distrital_por_ubigeo` y `consultar_entidades_por_ubigeo`. La matriz debe contener exactamente las ocho categorías. Si faltan credenciales, falla la consulta o la respuesta es incompleta, el servicio falla de forma cerrada.

La existencia de un resolutor sectorial no equivale a una institución concreta confirmada. Las reglas locales y las consultas geográficas se aplican con condiciones específicas; ante falta de evidencia, resultados ambiguos o fuentes no disponibles, se conserva la selección manual o se utiliza la bandeja interna de revisión de competencia de DenuPe.

### Seguridad y privacidad

- El middleware limita el cuerpo HTTP a 16 KiB por defecto y aplica una cuota predeterminada de 120 solicitudes por IP y minuto por proceso.
- Las respuestas incorporan un identificador de solicitud y cabeceras de seguridad.
- El backend no registra deliberadamente el título, descripción, coordenadas ni datos personales de la denuncia.
- La clave administrativa de InsForge debe mantenerse únicamente como secreto del servidor.
- Los archivos Joblib deben proceder de una fuente confiable, ya que su deserialización puede ejecutar código.
- Las recomendaciones no sustituyen la revisión humana ni ejecutan una derivación administrativa.

### Despliegue

El repositorio incluye `Dockerfile` y `render.yaml`. La configuración define un servicio web Docker en Render y usa `/health` como health check. Para desplegarlo, configura las variables privadas en el panel del proveedor y vincula la rama correspondiente. La existencia de estos archivos no garantiza que un servicio esté activo; verifica el estado del despliegue y consulta sus endpoints.

---

<p align="center">
  Proyecto DenuPe · Backend de inteligencia artificial y resolución territorial
</p>
