(function () {
    "use strict";

    const config = window.pushSettings;
    if (!config) return;

    const elements = {
        globalSwitch: document.getElementById("pushGlobalSwitch"),
        loading: document.getElementById("pushLoading"),
        pageMessage: document.getElementById("pushPageMessage"),
        unsupported: document.getElementById("pushUnsupported"),
        iosInstall: document.getElementById("pushIosInstall"),
        permissionDenied: document.getElementById("pushPermissionDenied"),
        recheckPermission: document.getElementById("pushRecheckPermission"),
        currentSection: document.getElementById("currentDeviceSection"),
        currentCard: document.getElementById("currentDeviceCard"),
        otherSection: document.getElementById("otherDevicesSection"),
        otherList: document.getElementById("otherDevicesList"),
    };

    let localSubscription = null;
    let serverState = {
        enabled: Boolean(config.initialPreference),
        current_device: null,
        current_endpoint_matches: false,
        other_devices: [],
    };

    function getInstallationId() {
        const storageKey = "coddaa_push_installation_id";
        try {
            let value = window.localStorage.getItem(storageKey);
            if (!value) {
                value = window.crypto.randomUUID();
                window.localStorage.setItem(storageKey, value);
            }
            return value;
        } catch (error) {
            return window.crypto.randomUUID();
        }
    }

    const installationId = getInstallationId();

    function getCookie(name) {
        const cookie = document.cookie
            .split(";")
            .map(value => value.trim())
            .find(value => value.startsWith(`${name}=`));
        return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : null;
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(payload || {}),
        });
        let data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        if (!response.ok) {
            throw new Error(data.error || data.message || "No fue posible completar la operación.");
        }
        return data;
    }

    function urlFor(template, deviceId) {
        return template.replace("/0/", `/${deviceId}/`);
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function setMessage(message, type) {
        elements.pageMessage.className = `alert alert-${type || "info"}`;
        elements.pageMessage.textContent = message;
        elements.pageMessage.classList.toggle("d-none", !message);
    }

    function browserDetails() {
        const ua = navigator.userAgent;
        let browser = "Navegador";
        let operatingSystem = "Sistema no identificado";

        if (/Edg\//.test(ua)) browser = "Microsoft Edge";
        else if (/CriOS|Chrome\//.test(ua)) browser = "Chrome";
        else if (/FxiOS|Firefox\//.test(ua)) browser = "Firefox";
        else if (/Safari\//.test(ua)) browser = "Safari";

        if (/Android/.test(ua)) operatingSystem = "Android";
        else if (/iPad|iPhone|iPod/.test(ua) || (ua.includes("Mac") && navigator.maxTouchPoints > 1)) operatingSystem = "iOS/iPadOS";
        else if (/Mac OS X/.test(ua)) operatingSystem = "macOS";
        else if (/Windows/.test(ua)) operatingSystem = "Windows";
        else if (/Linux/.test(ua)) operatingSystem = "Linux";

        return {
            browser,
            operating_system: operatingSystem,
            device_name: `${browser} · ${operatingSystem}`,
        };
    }

    function isIosWithoutInstallation() {
        const ua = navigator.userAgent;
        const isIos = /iPad|iPhone|iPod/.test(ua) || (ua.includes("Mac") && navigator.maxTouchPoints > 1);
        const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
        return isIos && !standalone;
    }

    function pushSupported() {
        return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    }

    function statusBadge(status) {
        return status === "ACTIVE"
            ? '<span class="small text-success fw-semibold"><span aria-hidden="true">●</span> Activo</span>'
            : '<span class="small text-muted fw-semibold">Pausado</span>';
    }

    function deviceHeading(device) {
        return `
            <div>
              <div class="d-flex align-items-center gap-2" data-device-heading>
                <div class="fw-bold" data-device-name>${escapeHtml(device.device_name)}</div>
                <button type="button"
                        class="btn btn-link btn-sm p-0 push-rename-button"
                        data-push-action="rename"
                        aria-label="Cambiar nombre del dispositivo"
                        title="Cambiar nombre">
                  <i class="bi bi-pencil" aria-hidden="true"></i>
                </button>
              </div>
              <div class="small text-muted">${escapeHtml(device.browser)} · ${escapeHtml(device.operating_system)}</div>
            </div>`;
    }

    function deviceActions(device, isCurrent) {
        const toggleAction = device.status === "ACTIVE"
            ? '<button class="btn btn-link text-secondary btn-sm" data-push-action="pause">Pausar</button>'
            : '<button class="btn btn-link btn-sm" data-push-action="activate">Activar</button>';
        const testAction = device.status === "ACTIVE" && serverState.enabled && isCurrent
            ? '<button class="btn btn-outline-primary btn-sm" data-push-action="test">Enviar notificación de prueba</button>'
            : "";
        return `
            <div class="push-device-actions d-flex flex-wrap align-items-center gap-2 mt-3">
              ${testAction}
              ${toggleAction}
              <button class="btn btn-link text-danger btn-sm" data-push-action="delete">Eliminar</button>
            </div>`;
    }

    function renderDevice(device, isCurrent) {
        return `
            <div data-device-id="${device.id}" data-current="${isCurrent}">
              <div class="d-flex justify-content-between align-items-start gap-3">
                ${deviceHeading(device)}
                ${statusBadge(device.status)}
              </div>
              ${deviceActions(device, isCurrent)}
            </div>`;
    }

    function render() {
        elements.loading.classList.add("d-none");
        elements.globalSwitch.checked = serverState.enabled;
        elements.unsupported.classList.add("d-none");
        elements.iosInstall.classList.add("d-none");
        elements.permissionDenied.classList.add("d-none");
        elements.currentSection.classList.add("d-none");
        elements.otherSection.classList.toggle("d-none", serverState.other_devices.length === 0);

        // En iOS/iPadOS las APIs de Web Push pueden no estar expuestas hasta
        // abrir el sitio como aplicación desde la pantalla de inicio. Por eso
        // este caso debe evaluarse antes que la compatibilidad genérica.
        if (isIosWithoutInstallation()) {
            elements.iosInstall.classList.remove("d-none");
        } else if (!pushSupported()) {
            elements.unsupported.classList.remove("d-none");
        } else if (Notification.permission === "denied") {
            elements.permissionDenied.classList.remove("d-none");
        } else if (serverState.current_device && serverState.current_endpoint_matches && localSubscription) {
            elements.currentCard.innerHTML = renderDevice(serverState.current_device, true);
            elements.currentSection.classList.remove("d-none");
        } else if (serverState.enabled) {
            const syncError = Boolean(localSubscription);
            elements.currentCard.innerHTML = `
                <div class="fw-bold mb-1">${escapeHtml(browserDetails().device_name)}</div>
                <p class="text-muted mb-3">${syncError
                    ? "Las notificaciones no están activadas en este dispositivo :(."
                    : "Las notificaciones no están activadas en este dispositivo."}</p>
                <button class="btn btn-primary btn-sm" data-push-action="register">
                  ${syncError ? "Activar en este dispositivo" : "Activar en este dispositivo"}
                </button>`;
            elements.currentSection.classList.remove("d-none");
        }

        elements.otherList.innerHTML = serverState.other_devices.map(device => `
            <div class="push-device-row py-4">
              ${renderDevice(device, false)}
            </div>`).join("");
    }

    async function getPushRegistration() {
        if (!pushSupported()) return null;
        const expectedPath = new URL(config.serviceWorkerUrl, window.location.href).pathname;
        const registrations = await navigator.serviceWorker.getRegistrations();
        return registrations.find(registration => {
            const worker = registration.active || registration.waiting || registration.installing;
            return worker && new URL(worker.scriptURL).pathname === expectedPath;
        }) || null;
    }

    async function getLocalSubscription() {
        if (!pushSupported()) return null;
        const registration = await getPushRegistration();
        return registration ? registration.pushManager.getSubscription() : null;
    }

    async function refreshState() {
        localSubscription = await getLocalSubscription();
        serverState = await postJson(config.urls.state, {
            endpoint: localSubscription ? localSubscription.endpoint : null,
            installation_id: installationId,
        });
        render();
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = "=".repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
        const rawData = window.atob(base64);
        return Uint8Array.from([...rawData].map(character => character.charCodeAt(0)));
    }

    async function activateCurrentDevice() {
        if (isIosWithoutInstallation()) throw new Error("Primero agrega el sitio a la pantalla de inicio.");
        if (!pushSupported()) throw new Error("Este navegador no admite notificaciones push.");
        if (Notification.permission === "denied") {
            render();
            throw new Error("Las notificaciones están bloqueadas en la configuración del navegador.");
        }

        let permission = Notification.permission;
        if (permission === "default") permission = await Notification.requestPermission();
        if (permission !== "granted") {
            render();
            throw new Error("No se concedió permiso para mostrar notificaciones.");
        }

        const registration = await navigator.serviceWorker.register(config.serviceWorkerUrl);
        localSubscription = await registration.pushManager.getSubscription();
        if (!localSubscription) {
            localSubscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(config.vapidPublicKey),
            });
        }

        const details = browserDetails();
        await postJson(config.urls.register, {
            subscription: localSubscription.toJSON(),
            browser: details.browser,
            operating_system: details.operating_system,
            device_name: details.device_name,
            installation_id: installationId,
            status_type: "subscribe",
        });
        await refreshState();
    }

    async function updateGlobalPreference(enabled) {
        elements.globalSwitch.disabled = true;
        try {
            serverState.enabled = (await postJson(config.urls.preference, { enabled })).enabled;
            if (enabled && !serverState.current_device && pushSupported() && !isIosWithoutInstallation()) {
                await activateCurrentDevice();
            } else {
                render();
            }
        } catch (error) {
            elements.globalSwitch.checked = serverState.enabled;
            setMessage(error.message, "danger");
        } finally {
            elements.globalSwitch.disabled = false;
        }
    }

    async function handleDeviceAction(button) {
        const action = button.dataset.pushAction;
        if (action === "register") {
            await activateCurrentDevice();
            setMessage("Este dispositivo quedó activo para recibir notificaciones.", "success");
            return;
        }

        const container = button.closest("[data-device-id]");
        const deviceId = container.dataset.deviceId;
        const isCurrent = container.dataset.current === "true";

        if (action === "rename") {
            startRenamingDevice(button, deviceId);
            return;
        } else if (action === "save-name") {
            const input = button.closest("[data-device-heading]").querySelector("[data-device-name-input]");
            await postJson(urlFor(config.urls.renameTemplate, deviceId), {
                device_name: input.value,
            });
            setMessage("Nombre del dispositivo actualizado.", "success");
        } else if (action === "cancel-name") {
            render();
            return;
        } else if (action === "pause" || action === "activate") {
            const status = action === "pause" ? "PAUSED" : "ACTIVE";
            await postJson(urlFor(config.urls.statusTemplate, deviceId), { status });
            setMessage(status === "ACTIVE" ? "Dispositivo activado." : "Dispositivo pausado.", "success");
        } else if (action === "delete") {
            if (!window.confirm("¿Quieres eliminar este dispositivo de tus notificaciones?")) return;
            await postJson(urlFor(config.urls.deleteTemplate, deviceId), {});
            if (isCurrent && localSubscription) {
                await localSubscription.unsubscribe();
                localSubscription = null;
            }
            setMessage("Dispositivo eliminado.", "success");
        } else if (action === "test") {
            const result = await postJson(urlFor(config.urls.testTemplate, deviceId), {
                endpoint: localSubscription ? localSubscription.endpoint : null,
            });
            setMessage(result.message || "Notificación de prueba enviada.", "success");
        }
        await refreshState();
    }

    function startRenamingDevice(button, deviceId) {
        const device = [serverState.current_device, ...serverState.other_devices]
            .find(item => item && String(item.id) === String(deviceId));
        if (!device) return;

        const heading = button.closest("[data-device-heading]");
        heading.innerHTML = `
            <label class="visually-hidden" for="push-device-name-${deviceId}">Nombre del dispositivo</label>
            <input type="text"
                   class="form-control form-control-sm"
                   id="push-device-name-${deviceId}"
                   data-device-name-input
                   maxlength="150">
            <button type="button" class="btn btn-primary btn-sm" data-push-action="save-name" aria-label="Guardar nombre" title="Guardar">
              <i class="bi bi-check-lg" aria-hidden="true"></i>
            </button>
            <button type="button" class="btn btn-link text-secondary btn-sm p-1" data-push-action="cancel-name" aria-label="Cancelar edición" title="Cancelar">
              <i class="bi bi-x-lg" aria-hidden="true"></i>
            </button>`;
        const input = heading.querySelector("[data-device-name-input]");
        input.value = device.device_name;
        input.focus();
        input.select();
    }

    elements.globalSwitch.addEventListener("change", event => {
        setMessage("", "info");
        updateGlobalPreference(event.target.checked);
    });
    elements.recheckPermission.addEventListener("click", () => window.location.reload());
    document.addEventListener("click", async event => {
        const button = event.target.closest("[data-push-action]");
        if (!button) return;
        button.disabled = true;
        setMessage("", "info");
        try {
            await handleDeviceAction(button);
        } catch (error) {
            setMessage(error.message, "danger");
            render();
        } finally {
            button.disabled = false;
        }
    });

    document.addEventListener("keydown", event => {
        if (!event.target.matches("[data-device-name-input]")) return;
        if (event.key === "Enter") {
            event.preventDefault();
            event.target.closest("[data-device-heading]").querySelector('[data-push-action="save-name"]').click();
        } else if (event.key === "Escape") {
            event.preventDefault();
            render();
        }
    });

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await refreshState();
        } catch (error) {
            elements.loading.classList.add("d-none");
            setMessage("No pudimos consultar la configuración. Intenta recargar la página.", "danger");
        }
    });
}());
