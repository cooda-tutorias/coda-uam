self.addEventListener('push', function(event) {
    // Valores predeterminados en caso de notificación silenciosa o fallo de payload
    let head = "🔔 Solicitud de tutoría 🙏",
    body = "Has recibido una solicitud de tutoría. Revisa la plataforma.",
    icon = "/static/img/icon.png",
    url = self.location.origin;

    // Si hay datos, intenta leerlos
    if (event.data) {
        try {
            // 1. Obtenemos el texto crudo DIRECTAMENTE
            const textPayload = event.data.text();
            console.log('SW DEBUG: Texto crudo recibido:', textPayload);

            // 2. Intentamos parsearlo manualmente a JSON
            let data = JSON.parse(textPayload);

            // 2.1 Por alguna razón data tiene los campos, pero aún es una cadena.
            // Esto ocurrió solamente porque por error serialicé el payload
            // antes de mandarlo en el send_user_notification. Pero esa función no
            // debería serializarlo, ya que lo hace internamente.+
            // Lo dejo aquí por si acaso. Pero si no hay errores, hay que quitar
            // este if ... else completo.
            if (typeof data == 'string') {
                data = JSON.parse(data);
            }
            else {
                console.log('SW DEBUG: JSON el tipo original ya era:', typeof data);
            }

            console.log('SW DEBUG: JSON parseado con éxito:', data);

            // 2.2 Sobrescribimos los valores predeterminados si vienen en el payload
            head = data.head || head;
            body = data.body || body;
            icon = data.icon || icon;
            url = data.url || url;

            console.log('SW DEBUG: Datos personalizados cargados.');

        } catch (e) {
            console.error('SW ERROR: Fallo al leer o parsear el payload.', e);
            // Si falla, se usarán los valores predeterminados definidos arriba.
        }
    } else {
        console.log('SW DEBUG: Notificación silenciosa (sin event.data)');
    }

    // Opciones que definen cómo se muestra la notificación.
    const options = {
        body: body,
        icon: icon, 
        badge: icon, // Android usa esto para el icono pequeño en barra de estado
        vibrate: [100, 50, 100], // Android vibra, iOS lo ignora (no da error)
        data: { url: url },
        // Añadimos tag para que no se acumulen infinitamente si mandas muchas.
        // Actualización: pero si ponemos tag, aunque se cambia la información de la
        // notificación, no baja el banner (globito) de la notificación.
        // Conclusión: mejor no poner tag ni renotify porque no es necesario.
        // tag: 'tutor-notification', 
        //renotify: true
    };

    // 3. Mostramos la notificación (siempre dentro de event.waitUntil)
    event.waitUntil(
        self.registration.showNotification(head, options)
    );
});


// Evento para manejar el clic en la notificación
self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    const relativeUrl = event.notification.data?.url || '/';
    const targetUrl = new URL(relativeUrl, self.location.origin);

    console.log('SW CLICK: URL recibida:', relativeUrl);
    console.log('SW CLICK: URL absoluta:', targetUrl.href);

    event.waitUntil(
        self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        }).then(async function (clientList) {
            console.log(
                'SW CLICK: Ventanas encontradas:',
                clientList.map(client => client.url)
            );

            const appClients = clientList.filter(function (client) {
                const clientUrl = new URL(client.url);

                // Al inspeccionar el Service Worker, Chrome expone su ventana de
                // depuración como WindowClient. No debe reutilizarse como pestaña
                // de la aplicación.
                return clientUrl.origin === targetUrl.origin &&
                    clientUrl.pathname !== self.location.pathname;
            });

            // Da prioridad a la ventana enfocada y después a una visible.
            const existingClient =
                appClients.find(client => client.focused) ||
                appClients.find(client => client.visibilityState === 'visible') ||
                appClients[0];

            if (existingClient) {
                console.log('SW CLICK: Reutilizando:', existingClient.url);

                try {
                    // Esta pestaña puede estar fuera del scope /static/js/ del
                    // Service Worker. Por ello la enfocamos y pedimos a la propia
                    // página que haga la navegación mediante postMessage.
                    await existingClient.focus();
                    existingClient.postMessage({
                        type: 'PUSH_NAVIGATE',
                        url: targetUrl.href
                    });
                    console.log('SW CLICK: Navegación enviada a la pestaña');
                    return existingClient;
                } catch (error) {
                    console.error('SW CLICK: Error al enfocar o comunicar:', error);
                    return;
                }
            }

            console.log('SW CLICK: Abriendo una ventana nueva');
            return self.clients.openWindow(targetUrl.href);
        }).catch(function (error) {
            console.error('SW CLICK: Error general:', error);
        })
    );
});
