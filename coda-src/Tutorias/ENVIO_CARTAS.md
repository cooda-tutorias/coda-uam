# Preparación de cartas para correo

En «Alumnado de la DCNI», la acción «Enviar cartas de asignación por correo»
abre el editor. «Preparar envío» guarda los mensajes en la sesión y abre el
formulario de plantillas, oficios y fecha. «Generar PDF para revisión» conserva
las cartas y abre la revisión con pestañas para alumnos y tutores. Cada
destinatario muestra el asunto y cuerpo personalizados junto al PDF exacto.
Un tutor con cartas de varias licenciaturas recibe un correo con todos sus PDF.

El envío requiere abrir al menos un PDF y confirmar los destinatarios. Los
correos inválidos se excluyen. Se usa `DEFAULT_FROM_EMAIL` y la configuración
SMTP existente; el cuerpo es texto plano. No se convierten nuevamente los PDF
ni se consultan datos actualizados al enviar: se usa el lote revisado.

El envío se procesa en un hilo de fondo, siguiendo el mecanismo de las
notificaciones existentes, y continúa si se cierra la página. El registro
temporal `envio.json` se escribe de forma atómica, con bloqueo entre procesos.
La revisión consulta el estado periódicamente. Los reintentos omiten correos
enviados; solo procesan pendientes o rechazos confirmados. «Enviado» significa
que el servidor de correo aceptó el mensaje, no confirmación de entrega.

Si se pierde la conexión durante un envío o el proceso web se interrumpe, el
resultado puede ser incierto. Esos correos aparecen «Por comprobar» y no se
repiten automáticamente. Los pendientes se pueden reintentar. El hilo no es
una cola de trabajo independiente: reiniciar el proceso web lo interrumpe.
Durante un envío se impide reemplazar el lote y la limpieza respeta su bloqueo.

El lote guarda los PDF y una copia de los nombres, correos, destinatarios y
licenciaturas usados para generarlos. Los mensajes y el identificador del lote
quedan en la sesión. Cambiar posteriormente los datos o las plantillas no
modifica las cartas preparadas ni los mensajes del lote.

Los mensajes predeterminados usan un tono formal. Para alumnos, el saludo fijo
es «Estimado(a)» y `{referencia_tutor}` se sustituye por «del profesor Dr. …» o
«de la profesora Dra. …». Para tutores se admiten `{saludo_tutor}` y
`{tratamiento_tutor}`. Ambos admiten `{url_tutorias}`, tomada de
`TUTORIAS_SITE_URL`. El sexo del tutor y la URL se conservan al preparar el lote;
no se requiere el sexo del alumno. Los borradores previos mantienen su texto.

Los archivos se guardan fuera de `MEDIA_ROOT`, por defecto en
`/tmp/coddaa-envios` dentro del contenedor. Solo la sesión que preparó el lote
puede acceder a sus PDF mediante vistas protegidas para CODDAA. Se conserva
un lote por sesión; preparar otro correctamente elimina el anterior. Si falla
la conversión, se elimina el lote parcial y se conserva el anterior.

Los lotes caducan a las 24 horas. La limpieza se ejecuta al preparar otro lote.
Para limpiar aunque no haya nuevos envíos, programar diariamente:

```sh
python manage.py limpiar_lotes_asignacion
```

El directorio puede configurarse con el ajuste Django `CARTAS_ENVIO_ROOT`.
Debe permanecer privado y fuera de las rutas servidas por el servidor web.
El directorio temporal predeterminado puede perderse al recrear el contenedor;
en ese caso se indica al usuario que prepare de nuevo. Si se despliega en
varios servidores, todos necesitan acceder al mismo directorio privado.

La descarga habitual de cartas Word/PDF sigue generando su ZIP en memoria y
no conserva lotes de envío. Esta implementación no requiere migraciones.
