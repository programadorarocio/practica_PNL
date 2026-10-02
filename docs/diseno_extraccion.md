# Parte 1 – Diseño de la Extracción

## 1. Categoría Seleccionada
- **Nombre de la categoría:** Fantástico
- **URL de la categoría:** `https://ww3.lectulandia.com/genero/fantastico/`
- **Cantidad de libros propuesta:** 144 libros (6 páginas de 24 libros cada una).
- **Criterio de selección de páginas:** Paginación secuencial mediante URLs con estructura `/genero/fantastico/page/{N}/` desde la página 1 hasta la 6.

---

## 2. Datos a Extraer

El dataset contendrá los siguientes campos:

| Campo | Descripción |
| :--- | :--- |
| `titulo` | Título del libro |
| `autores` | Autor o lista de autores de la obra (formato lista JSON) |
| `generos` | Género o lista de géneros asignados (formato lista JSON) |
| `serie` | Nombre de la serie / saga a la que pertenece la obra |
| `numero_serie` | Número de entrega / volumen dentro de la saga (ej. `1`, `3`, `4`) |
| `sinopsis` | Texto completo y normalizado de la sinopsis |
| `url_libro` | Dirección web de la ficha individual |
| `categoria_origen` | Categoría base seleccionada ("Fantástico") |
| `fecha_extraccion` | Fecha y hora en formato YYYY-MM-DD HH:MM:SS |
| `portada_url` | Enlace a la imagen de portada |

---

## 3. Localización de los Datos y Selectores HTML

| Dato | Tipo de página | Etiqueta HTML | Selector propuesto | Estrategia de discriminación |
| :--- | :--- | :--- | :--- | :--- |
| **URL de la ficha** | Listado de categoría | `<a>` | `a.card-click-target` | Filtrar enlaces que contengan `/book/` y construir URL absoluta `ww3.lectulandia.com/{href}/`. |
| **Título** | Ficha individual | `<div>` | `div#title` / `#title` | Extraer texto del elemento contenedor del título. |
| **Autores** | Ficha individual | `<a>` | `div#autor a.dinSource` | Extraer etiquetas `dinSource` ubicadas en `div#autor`. Guardar en formato lista JSON para mantener integridad. |
| **Géneros** | Ficha individual | `<a>` | `div#genero a.dinSource` | Extraer etiquetas `dinSource` ubicadas en `div#genero`. Guardar en formato lista JSON para mantener integridad. |
| **Serie** | Ficha individual | `<a>` | `div#serie a.dinSource` | Extraer el nombre de la saga desde `a.dinSource` (ej. "Carl el Mazmorrero"). |
| **Número de serie** | Ficha individual | `<span>` | `div#serie .tagTitle` | Extraer el valor numérico con expresión regular desde `.tagTitle` (ej. "Libro 3 de:" -> `3`). |
| **Sinopsis** | Ficha individual | `<div>` | `div#sinopsis` | Obtener texto de los elementos `<p>` o `<span>` internos, eliminando saltos de línea y espacios redundantes.|
| **Portada** | Ficha individual | `<img>` | `#cover img` / `img.cover` | Obtener el atributo `src`. |
---

## 4. Estrategia de Extracción

1. **Navegación e iteración por catálogo con Playwright:**
   - Iniciar una instancia de Chromium en modo *headless*.
   - Recorrer secuencialmente las 6 páginas de la categoría elegida.
   - Extraer el código HTML de cada página y parsearlo con BeautifulSoup.
2. **Recolección y desduplicación de URLs:**
   - Extraer todos los enlaces de tarjetas de libros (`a.card-click-target`).
   - Normalizar a URLs absolutas y filtrar duplicados en memoria.
3. **Extracción secuencial de fichas individuales:**
   - Visitar cada ficha con Playwright.
   - Obtener el HTML y delegar la extracción a BeautifulSoup.
   - Discriminar los elementos con clase `dinSource` según su contenedor padre (`#autor`, `#genero`, `#serie`).
   - En caso de ser parte de una serie, extraer el número representativo al orden dentro de la misma.
   - Limpiar y normalizar la sinopsis en un solo bloque de texto.
4. **Manejo de errores, Rate Limiting y Guardado Incremental:**
   - Pausas de 1 segundo entre peticiones a las páginas individuales para evitar saturar el servidor.
   - Manejo de excepciones en cada ficha para asegurar que el proceso continúe ante fallos puntuales de red.
   - Guardado incremental periódico en `data/libros.csv` con pandas para resguardar el progreso.

## 5. Posibles Problemas a Enfrentar en la Implementación

3. **Extracción secuencial de fichas individuales**
   - Según nuestro modelo de extracción, podemos tener campos faltantes o no definidos, estos figurarán como campos vacios en el CSV resultante. Se verá principalmente en los campos Serie y Número de Serie.
   - Podemos tener problemas a la hora de guardar los nombres de los autores ya que un CSV es una fuente de datos que no asegura la integridad de los mismos. Lo más sencillo sería utilizar el formato JSON para poder integrar esa lista de autores al CSV para facilitar su posterior recuperación y parseo.
   - La sinopsis puede presentar saltos de página que al ser filtrados o eliminados pueden llegar a causar problemas en la correcta separación del texto base (ej. "Se terminó \n el otro día..." pasará a ser "Se terminóel otro día...)

El resto de los puntos planteados, a primera vista, no parecen presentar grandes problemas a la hora de realizar su implementación.
