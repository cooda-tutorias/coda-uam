(function (global) {
    "use strict";

    function obtenerSiguienteDiaHabilALasDiez(fechaBase = new Date()) {
        const fecha = new Date(fechaBase);

        fecha.setDate(fecha.getDate() + 1);

        while (fecha.getDay() === 0 || fecha.getDay() === 6) {
            fecha.setDate(fecha.getDate() + 1);
        }

        fecha.setHours(10, 0, 0, 0);
        return fecha;
    }

    function formatearFechaHoraLocal(fecha) {
        const anio = fecha.getFullYear();
        const mes = String(fecha.getMonth() + 1).padStart(2, "0");
        const dia = String(fecha.getDate()).padStart(2, "0");
        const horas = String(fecha.getHours()).padStart(2, "0");
        const minutos = String(fecha.getMinutes()).padStart(2, "0");

        return `${anio}-${mes}-${dia}T${horas}:${minutos}`;
    }

    function validarDiaHabil(input) {
        input.setCustomValidity("");
        if (!input.value) return true;

        const diaSemana = new Date(input.value).getDay();
        if (diaSemana === 0 || diaSemana === 6) {
            input.setCustomValidity(
                "Selecciona un día hábil de lunes a viernes."
            );
            return false;
        }

        return true;
    }

    function inicializarFechaSugerida(input, fechaBase = new Date()) {
        const siguienteDiaHabil = obtenerSiguienteDiaHabilALasDiez(fechaBase);
        const valorInicial = formatearFechaHoraLocal(siguienteDiaHabil);

        input.min = valorInicial;
        input.value = valorInicial;
        validarDiaHabil(input);

        if (input.dataset.validacionDiaHabil !== "true") {
            input.addEventListener("input", function () {
                validarDiaHabil(input);
            });
            input.dataset.validacionDiaHabil = "true";
        }
        return valorInicial;
    }

    async function consultarHorariosTutor(tutorId) {
        const respuesta = await fetch(`/api/slots-tutor/${tutorId}/`);

        if (!respuesta.ok) {
            throw new Error(
                `No fue posible consultar los horarios: ${respuesta.status}`
            );
        }

        const data = await respuesta.json();
        return data.slots || [];
    }

    function crearCalendario({ elemento, slots, alCambiarFecha }) {
        const diasActivos = [
            ...new Set(slots.map(slot => slot.dia_semana_num)),
        ];

        return global.flatpickr(elemento, {
            inline: true,
            locale: "es",
            minDate: "today",
            dateFormat: "Y-m-d",
            enable: [
                function (fecha) {
                    const diaSemana = (fecha.getDay() + 6) % 7;
                    return diasActivos.includes(diaSemana);
                },
            ],
            onChange: function (_, fechaSeleccionada) {
                alCambiarFecha(fechaSeleccionada);
            },
        });
    }

    function crearIdFranja({ prefijo, fecha, franja, indice }) {
        const hora = franja.hora_inicio.replace(":", "");
        return `${prefijo}-${fecha}-${franja.slot_id}-${hora}-${indice}`;
    }

    async function consultarFranjas(tutorId, fecha) {
        const parametros = new URLSearchParams({ fecha });
        const respuesta = await fetch(
            `/api/franjas-disponibles/${tutorId}/?${parametros}`
        );

        if (!respuesta.ok) {
            throw new Error(
                `No fue posible consultar las franjas: ${respuesta.status}`
            );
        }

        const data = await respuesta.json();
        return data.franjas || [];
    }

    function renderizarFranjas({
        franjas,
        fecha,
        contenedor,
        botonConfirmar,
        prefijoId,
        alSeleccionar,
    }) {
        contenedor.innerHTML = "";

        if (franjas.length === 0) {
            contenedor.innerHTML = `
                <small class="text-muted">
                    No hay horarios libres ese día.
                </small>
            `;
            return;
        }

        franjas.forEach((franja, indice) => {
            const opcionId = crearIdFranja({
                prefijo: prefijoId,
                fecha,
                franja,
                indice,
            });

            const opcion = document.createElement("input");
            opcion.type = "radio";
            opcion.className = "btn-check";
            opcion.name = `${prefijoId}-opcion`;
            opcion.id = opcionId;
            opcion.autocomplete = "off";

            const etiqueta = document.createElement("label");
            etiqueta.className =
                "btn btn-horario-slot btn-sm text-start w-100";
            etiqueta.htmlFor = opcionId;
            etiqueta.textContent =
                `${franja.hora_inicio} - ${franja.hora_fin}`;

            opcion.addEventListener("change", function () {
                if (!opcion.checked) return;

                alSeleccionar({
                    horarioId: franja.slot_id,
                    fecha,
                    fechaHora: franja.datetime_iso,
                    horaInicio: franja.hora_inicio,
                    horaFin: franja.hora_fin,
                });

                botonConfirmar.disabled = false;
            });

            contenedor.appendChild(opcion);
            contenedor.appendChild(etiqueta);
        });
    }

    async function cargarFranjas(configuracion) {
        const {
            tutorId,
            fecha,
            contenedor,
            botonConfirmar,
        } = configuracion;

        botonConfirmar.disabled = true;
        contenedor.innerHTML = `
            <div class="py-3 text-center">
                <span class="spinner-border spinner-border-sm text-primary"></span>
                Cargando horarios...
            </div>
        `;

        try {
            const franjas = await consultarFranjas(tutorId, fecha);
            renderizarFranjas({ ...configuracion, franjas });
        } catch (error) {
            console.error(error);
            contenedor.innerHTML = `
                <small class="text-danger">
                    No fue posible cargar los horarios.
                </small>
            `;
        }
    }

    function limpiarSelector({
        calendario,
        contenedorFranjas,
        botonConfirmar,
        campos = [],
    }) {
        if (calendario) {
            calendario.destroy();
        }

        contenedorFranjas.innerHTML = `
            <small class="text-muted">
                Elige un día para consultar sus horarios.
            </small>
        `;

        campos.forEach(campo => {
            campo.value = "";
        });

        botonConfirmar.disabled = true;
        return null;
    }

    global.SelectorFechaTutoria = Object.freeze({
        obtenerSiguienteDiaHabilALasDiez,
        formatearFechaHoraLocal,
        validarDiaHabil,
        inicializarFechaSugerida,
        consultarHorariosTutor,
        crearCalendario,
        cargarFranjas,
        limpiarSelector,
    });
})(window);
