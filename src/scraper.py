import os
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright
from urllib.parse import urljoin
import pandas as pd
import json
from datetime import datetime
import re

BASE_URL = "https://ww3.lectulandia.com"
CATEGORIA_URL = "https://ww3.lectulandia.com/genero/fantastico/"
CATEGORIA_NOMBRE = "Fantástico"
NUM_PAGINAS = 6
OUTPUT_CSV = os.path.join("data", "libros.csv")

# Lista global de URLs extraídas
URLS_LIBROS: list[str] = []

async def extraer_urls_libros(page: Page, categoria_url: str, num_paginas: int = 6) -> list[str]:
    """
    Recorre las páginas de la categoría con Playwright y extrae las URLs
    de las fichas de libros utilizando BeautifulSoup.
    
    Retorna una lista de URLs absolutas sin duplicados.
    """
    urls_encontradas: list[str] = []
    #Se utiliza un set para evitar duplicados de URLs ya vistas
    urls_vistas: set[str] = set()

    for num_pag in range(1, num_paginas + 1):
        # La primera página no tiene el sufijo "page/1/", por lo que se maneja como un caso especial
        # Formato de paginación de Lectulandia: https://ww3.lectulandia.com/genero/fantastico/page/2/
        url_actual = categoria_url if num_pag == 1 else urljoin(categoria_url, f"page/{num_pag}/")
        
        print(f"[Página {num_pag}/{num_paginas}] Navegando a: {url_actual}")

        try:
            #Esperamos a que la página cargue completamente antes de extraer el contenido
            await page.goto(url_actual, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(1.0)

            #Recuperamos el contenido HTML de la página y lo parseamos con BeautifulSoup
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Las cards de cada libro están dentro de las etiquetas <a> con la clase card-click-target
            enlaces_tarjetas = soup.select("a.card-click-target")

            #Iteramos todas las cards de la página para obtener las URLs y las contabilizamos
            libros_pagina = 0
            for a_tag in enlaces_tarjetas:
                href = a_tag.get("href")
                #Type checking - href tiene que ser un string y contener "/book/" 
                #para ser considerado una URL de libro válida
                if isinstance(href, str) and "/book/" in href:
                    url_completa = urljoin(BASE_URL, href)
                    if url_completa not in urls_vistas:
                        urls_vistas.add(url_completa)
                        urls_encontradas.append(url_completa)
                        libros_pagina += 1
                    else:
                        print(f"URL duplicada encontrada y omitida: {url_completa}")

            print(f"Encontrados en esta página: {libros_pagina} libros (Total acumulado: {len(urls_encontradas)})")

            # Rate limiting
            if num_pag < num_paginas:
                await asyncio.sleep(1.0)

        except Exception as e:
            print(f"Error al procesar la página {url_actual}: {e}")
            continue

    return urls_encontradas

def parsear_ficha_libro(html: str, url_libro: str, categoria_origen: str) -> dict:
    """
    Analiza el HTML de la ficha individual de un libro mediante BeautifulSoup
    y extrae los campos requeridos discriminando los tags 'dinSource'.
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Título ---
    titulo_el = soup.select_one("div#title") or soup.select_one("#title")
    titulo = titulo_el.get_text(strip=True) if titulo_el else ""

    # --- Diferenciación de dinSource por tipo (Autor, Género, Serie) ---
    # --- Autores (Lista) ---
    tags_autor = soup.select("div#autor a.dinSource")
    lista_autores = []
    for a in tags_autor:
        nombre = a.get_text(strip=True)
        if nombre:
            lista_autores.append(nombre)
    autores = json.dumps(lista_autores, ensure_ascii=False)

    # --- Géneros (Lista) ---
    tags_genero = soup.select("div#genero a.dinSource")
    lista_generos = []
    for g in tags_genero:
        genero_texto = g.get_text(strip=True)
        if genero_texto:
            lista_generos.append(genero_texto)
    generos = json.dumps(lista_generos, ensure_ascii=False)

    # --- Serie y Número de orden ---
    serie_div = soup.select_one("div#serie")
    serie = ""
    numero_serie = ""
    if serie_div:
        tag_title = serie_div.select_one(".tagTitle")
        tag_a = serie_div.select_one("a.dinSource")
        
        serie = tag_a.get_text(strip=True) if tag_a else ""
        prefijo_orden = tag_title.get_text(strip=True) if tag_title else ""
        
        # Extraer exclusivamente el número de entrega (ej: "Libro 4 de:" -> 4)
        if prefijo_orden:
            match = re.search(r"\d+", prefijo_orden)
            if match:
                numero_serie = int(match.group(0))

    # --- Sinopsis ---
    sinopsis_el = soup.select_one("div#sinopsis")
    sinopsis = ""
    if sinopsis_el:
        # Reemplazar <br> por espacio y extraer texto usando un separador único
        for br in sinopsis_el.find_all("br"):
            br.replace_with(" ")
        # Obtener todo el texto de la sinopsis con espacios entre elementos
        texto_limpio = sinopsis_el.get_text(separator=" ", strip=True)
        # Normalizar secuencias de espacios y saltos en uno solo
        texto_limpio = re.sub(r"\s+", " ", texto_limpio).strip()
        sinopsis = texto_limpio

    # --- Portada ---
    cover_el = soup.select_one("#cover img") or soup.select_one("img.cover")
    portada_url = ""
    if cover_el:
        src = cover_el.get("src", "")
        if isinstance(src, str):
            portada_url = src

    return {
        "titulo": titulo,
        "autores": autores,
        "generos": generos,
        "serie": serie,
        "numero_serie": numero_serie,
        "sinopsis": sinopsis,
        "url_libro": url_libro,
        "categoria_origen": categoria_origen,
        "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "portada_url": portada_url,
    }


async def extraer_todos_los_libros(page: Page, urls: list[str], categoria_origen: str) -> list[dict]:
    """
    Visita secuencialmente cada ficha de libro, extrae los datos y realiza
    guardados incrementales para prevenir pérdida de información.
    """
    registros: list[dict] = []
    total = len(urls)

    # Asegurar que el directorio de salida exista
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

    print(f"\nIniciando scraping detallado de {total} libros...")

    for i, url in enumerate(urls, 1):
        try:
            print(f"[{i}/{total}] Scraping ficha: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            await asyncio.sleep(0.5)

            html = await page.content()
            libro_data = parsear_ficha_libro(html, url, categoria_origen)

            registros.append(libro_data)
            print(f"   └── Título: {libro_data['titulo']} | Autor(es): {libro_data['autores']} | Géneros: {libro_data['generos']}")

            # Guardado incremental cada 10 registros y al final
            if i % 10 == 0 or i == total:
                df_temp = pd.DataFrame(registros)
                df_temp.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
                print(f"   [Guardado incremental] {len(registros)} registros guardados en {OUTPUT_CSV}")

            # Rate limiting ético entre fichas
            await asyncio.sleep(1.0)

        except Exception as e:
            print(f"   Error al scrapear libro {url}: {e}")
            continue

    return registros

async def main():
    global URLS_LIBROS

    async with async_playwright() as p:
        # Configurar el navegador
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Extracción de URLs de la categoría
            print("Iniciando extracción de URLs de libros...")
            URLS_LIBROS = await extraer_urls_libros(page, CATEGORIA_URL, NUM_PAGINAS)

            print(f"\nExtracción de URLs finalizada:")
            print(f"Total de libros únicos recolectados: {len(URLS_LIBROS)}")

            if not URLS_LIBROS:
                print("No se encontraron URLs de libros para procesar.")
                return

            # Scraping secuencial de cada libro
            libros = await extraer_todos_los_libros(page, URLS_LIBROS, CATEGORIA_NOMBRE)

            # Resumen final del dataset
            df_final = pd.DataFrame(libros)
            print(f"\nProceso finalizado con éxito.")
            print(f"Dataset guardado en: {OUTPUT_CSV}")
            print(f"Dimensiones del dataset: {df_final.shape[0]} filas x {df_final.shape[1]} columnas")
            print(f"Columnas generadas: {list(df_final.columns)}")

        except Exception as e:
            print(f"Error general en la ejecución: {e}")

        finally:
            await browser.close()
            print("Navegador cerrado.")


if __name__ == "__main__":
    asyncio.run(main())