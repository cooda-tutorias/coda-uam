// ./coda-src/static/js/webpush_toggle_setup.js

// === Función para obtener el token CSRF ===
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// === Convertir la clave VAPID pública de base64url a Uint8Array ===
function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);

    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

// === Tomar la clave VAPID desde el template ===
const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);




// === Lógica Principal del Toggle ===
document.addEventListener('DOMContentLoaded', async function () {
    const toggleSwitch = document.getElementById('pushNotificationSwitch');
    
    if (!toggleSwitch) return;

    // A. VERIFICACIÓN INICIAL (Estado al cargar la página)
    // 1. Detección de iOS (incluye iPads que fingen ser Macs)
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || 
                  (navigator.userAgent.includes("Mac") && navigator.maxTouchPoints > 1);
    
    // 2. Detectar si ya está instalado el sitio web como App (Standalone)
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                         window.navigator.standalone === true;


    if (isIOS && !isStandalone) {
        console.log("Detectado iOS en modo Navegador. Deshabilitando switch.");
        
        toggleSwitch.disabled = true;
        toggleSwitch.checked = false;

        // Crear el mensaje de ayuda
        const helpText = document.createElement('div');
        helpText.className = "alert alert-warning mt-3 small shadow-sm";
        helpText.style.borderRadius = "10px";
        helpText.innerHTML = `
            <div class="d-flex align-items-start">
                <i class="fas fa-info-circle fs-4 me-2 mt-1"></i>
                <div>
                    <strong>Requiere instalación</strong><br>
                    Para activar las notificaciones en este dispositivo, toca el botón 
                    <i class="bi bi-box-arrow-up"></i> (Compartir) y selecciona 
                    <b>"Agregar a Inicio"</b>. Luego abre la App desde tu pantalla principal.
                </div>
            </div>`;
        
        // Insertar mensaje visualmente después del contenedor del switch
        // (Asegúrate de que el selector apunte al lugar correcto en tu HTML)
        const switchContainer = toggleSwitch.closest('.card-body') || toggleSwitch.parentElement;
        switchContainer.appendChild(helpText);
    }
    else if ('serviceWorker' in navigator && 'PushManager' in window) {
        try {
            const registration = await navigator.serviceWorker.getRegistration('/static/js/coddaa-service-worker.js');
            if (registration) {
                const subscription = await registration.pushManager.getSubscription();
                
                // ESTO IMPLMENTA UNA SOFT UNSUBSCRIBE (solamente usa una bandera pero NO borra la suscripción):
                // El navegador puede tener la suscripción (subscription !== null), 
                // pero necesitamos saber si en TU BASE DE DATOS está activo.
                // Como no podemos consultar tu BD directamente desde aquí sin una petición extra,
                // asumimos lo siguiente para la UI inicial:
                
                // Opción simple: Si existe suscripción en el navegador, mostramos ON.
                // (Si el usuario lo había apagado, al recargar la página aparecerá ON si no borramos la cookie/cache, 
                //  pero al menos está sincronizado con la capacidad del navegador).
                if (subscription) {
                    // ...pero el SERVIDOR dice que NO estamos suscritos (serverIsSubscribed es false)
                    if (!serverIsSubscribed) {
                        console.log("Modo Soft-Unsubscribe: Navegador listo, pero usuario inactivo en BD.");
                        toggleSwitch.checked = false; // Mantenemos APAGADO visualmente
                    } else {
                        // Coinciden: Navegador tiene sub y Servidor dice activo.
                        toggleSwitch.checked = true; 
                    }
                } else {
                    toggleSwitch.checked = false;
                }
            }
        } catch (error) {
            console.error('Error verificando estado del SW:', error);
        }
    } 
    else {
        toggleSwitch.disabled = true;
        console.warn('Este navegador no soporta notificaciones Push.');
    }

    // B. ESCUCHAR EL CAMBIO (Evento Click)
    toggleSwitch.addEventListener('change', function (e) {
        if (this.checked) {
            // Usuario mueve a ON
            handleActivation();
        } else {
            // Usuario mueve a OFF
            handleDeactivation();
        }
    });

    // === Función de Activación (Inteligente) ===
    function handleActivation() {
        const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);

        navigator.serviceWorker.register('/static/js/coddaa-service-worker.js?v=9')
            .then(function (registration) {
                return registration.pushManager.getSubscription()
                .then(function(existingSubscription) {
                    // CASO 1: Reactivación (Soft Subscribe)
                    // Si ya existe una suscripción "durmiente", la usamos.
                    if (existingSubscription) {
                        return existingSubscription;
                    }

                    // CASO 2: Primera vez o Hard Unsubscribe previo
                    // Pedimos permiso y creamos una nueva.
                    return Notification.requestPermission().then(function (permission) {
                        if (permission !== 'granted') {
                            throw new Error('Permiso denegado');
                        }
                        return registration.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: convertedVapidKey
                        });
                    });

                    return null;
                });
            })
            .then(function (subscription) {
                console.log('📡 Suscripción activa:', subscription);
                // Enviamos a Django para que guarde/reactive
                sendSubscriptionToBackEnd(subscription, 'subscribe');
            })
            .catch(function (err) {
                console.error('❌ Error al activar:', err);
                toggleSwitch.checked = false; 
                alert("No se pudieron activar las notificaciones.");
            });
    }

    // === Función de Desactivación (SOFT UNSUBSCRIBE) ===
    function handleDeactivation() {
        navigator.serviceWorker.getRegistration('/static/js/coddaa-service-worker.js')
            .then(function (registration) {
                if (!registration) return;
                return registration.pushManager.getSubscription();
            })
            .then(function (subscription) {
                if (!subscription) return;

                // PASO CRÍTICO: "Soft Unsubscribe"
                // 1. Avisamos a Django que borre el registro de la BD.
                sendSubscriptionToBackEnd(subscription, 'unsubscribe');

                // 2. NO llamamos a subscription.unsubscribe().
                // Dejamos la suscripción viva en el navegador, pero huérfana en el servidor.
                console.log('✅ Notificaciones desactivadas en servidor (Soft Unsubscribe local).');
            })
            .catch(function (e) {
                console.error('❌ Error al desactivar:', e);
                // Opcional: regresar el toggle a ON si falló la conexión
            });
    }

    // === Comunicación con Django ===
    function sendSubscriptionToBackEnd(subscription, statusType) {
        const sub = subscription.toJSON();
        console.log('🔍 Suscripción JSON:', sub);
        const payload = {
            subscription: {
                endpoint: sub.endpoint,
                keys: {
                    auth: sub.keys.auth,
                    p256dh: sub.keys.p256dh
                }
            },
            browser: 'chrome', 
            group: '',
            status_type: statusType // 'subscribe' guarda, 'unsubscribe' borra en Django
        };

        console.log(`🚀 Enviando a Django (${statusType}):`, payload);

        fetch('/webpush/save_information/', {
            method: 'POST',
            body: JSON.stringify(payload),
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
        .then(async response => {
            if (response.ok) {
                console.log(`✅ Servidor actualizado: ${statusType}`);
            } else {
                console.error(`❌ Servidor falló: ${statusType}`, response.status);
                // Si falló el 'subscribe', podrías apagar el toggle visualmente aquí
            }
        })
        .catch(e => {
            console.error('💥 Error de red:', e);
        });
    }
});
