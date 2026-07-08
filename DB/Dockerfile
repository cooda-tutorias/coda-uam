# La imagen base de PostgreSQL está en el compose.yaml, por lo que no es necesario especificarla aquí.

# Establece la contraseña de PostgreSQL
ENV POSTGRES_PASSWORD=postgres

# Expone el puerto 8484 para acceder desde la máquina local
EXPOSE 5432

# El volumen persistente se define en compose.yaml para reutilizar data/db

# Inicializa la base de datos y crea una base de datos llamada "prueba"
COPY init.sql /docker-entrypoint-initdb.d/

# Define la base de datos que se creará automáticamente al iniciar el contenedor
ENV POSTGRES_DB=coda
