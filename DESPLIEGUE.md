# Despliegue

Guía para levantar el sistema en un servidor con Docker. Para ejecución local
de desarrollo, ver `README.md`.

---

## Requisito que condiciona el dimensionamiento: Ollama

Los embeddings del RAG corren siempre por Ollama con `nomic-embed-text`. No es
configurable por entorno: está fijado en `adapters/llm/ollama_provider.py` y
la razón es de integridad de datos, no de rendimiento. Vectores generados por
modelos distintos no son comparables entre sí, de modo que cambiar el modelo
de embedding obliga a regenerar el índice completo del corpus.

Consecuencia práctica: **sin un Ollama alcanzable, la pantalla "Trabajar con
IA" falla** al buscar casos similares. Los tableros de resultados y
seguimiento funcionan igual, porque leen CSV y PostgreSQL.

De ahí salen dos perfiles de despliegue:

| Perfil | Alcance | Recursos |
|---|---|---|
| **Completo** | Incluye generación de casos en vivo | ~8 GB de RAM (Ollama + PostgreSQL + aplicación) |
| **Solo tableros** | Resultados y análisis, sin generación | ~2 GB |

---

## Antes de desplegar

### Congelar versiones

Usar el `requirements-lock.txt` incluido para reproducir las dependencias.
Solo para mantenimiento, si se necesita regenerar el lock desde un entorno
validado, ejecutar:

```bash
pip freeze > requirements-lock.txt
```

El `Dockerfile` lo usa si existe y advierte por consola si falta.

> En Windows, `pip freeze` puede emitir paquetes con rutas locales
> (`@ file:///...`). Revisar y quitar esas líneas antes de publicar el lock.

### Compatibilidad verificada

Las dependencias declaradas tienen wheel para Python 3.13 en Linux x86-64,
incluida `psycopg[binary]`, que es la única que compila código nativo. No hace
falta compilador en el servidor.

---

## Pasos

```bash
# 1. Código en el servidor
cd agente-qa-gherkin

# 2. Credenciales. El .env se lee en ejecución y nunca entra en la imagen.
cp env.example .env
# completar: Jira, Xray, DB_PASSWORD

# 3. Infraestructura
docker compose up -d db ollama

# 4. Modelos de generación y embeddings (una sola vez)
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama list

# 5. Esquema de base de datos
docker compose run --rm app alembic upgrade head

# 6. Aplicación
docker compose up -d app
docker compose logs -f app
```

La aplicación queda en `http://<ip>:8501`. Comprobar `docker compose ps`
y abrir la interfaz. Validar el acceso autorizado a Jira/Xray, recuperar una
HU de prueba y verificar el flujo de Vera y Gio en un entorno de pruebas.
La etiqueta `latest` de Ollama no garantiza reproducibilidad exacta; registrar
la versión y el identificador de imagen realmente validados antes de fijarlos.
Los datos externos y las credenciales autorizadas son necesarios para
reproducir las integraciones y los resultados históricos.

### Perfil "solo tableros"

Quitar el servicio `ollama` de `docker-compose.yml` y el `depends_on` que lo
referencia. La aplicación arranca igual y los tableros funcionan. Verificar
antes que las pantallas que se vayan a usar no consulten el RAG.

---

## Datos

La imagen no incluye los archivos de datos: `.dockerignore` los excluye
deliberadamente. Se montan como volumen de solo lectura
(`./datos:/app/datos:ro` en el compose).

Cuando el volumen está vacío, las páginas que dependen de un archivo muestran
el aviso correspondiente en lugar de fallar: ese caso está contemplado en el
código.

Los datos del corpus provienen de un entorno productivo. Su extracción fuera
de la red interna requiere la autorización que corresponda en cada
organización; es una decisión de gobierno de datos, no técnica.

---

## Seguridad

Resuelto en esta configuración:

- Ni PostgreSQL ni Ollama exponen puertos al exterior. Solo la aplicación, en
  el 8501.
- El contenedor corre con un usuario sin privilegios, no como root.
- El `.env` no se incluye en la imagen.

Pendiente de resolver según el entorno de destino:

- **TLS.** El puerto 8501 en HTTP plano expone la sesión. Para exposición
  permanente, anteponer un proxy con certificado.
- **Control de acceso.** La aplicación implementa `requerir_sesion()`;
  conviene revisar qué valida antes de publicarla en una red abierta.
