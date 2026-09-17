# Usa la imagen base de Python para Django
FROM python:3.9

# Conversión local de plantillas Word a PDF sin GUI y fuentes de sustitución habituales.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui libreoffice-core-nogui fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Python cache
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia el archivo requirements.txt e instala las dependencias
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Copia el resto del código de la aplicación al directorio de trabajo del contenedor
COPY . /app/

# Ejecuta migrate durante la construcción de la imagen
# RUN python manage.py migrate

# Expone el puerto 8000 para acceder a la aplicación Django
EXPOSE 8000

# Comando predeterminado para ejecutar el servidor Django
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
