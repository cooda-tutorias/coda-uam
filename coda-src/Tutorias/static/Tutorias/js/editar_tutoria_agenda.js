(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const openButton = document.getElementById("btnAbrirModalCita");
    if (!openButton) return;

    const tutorId = openButton.dataset.tutorId;
    const slotInput = document.getElementById("id_horario_tutor");
    const dateInput = document.getElementById("id_fecha");
    const selectedDateInput = document.getElementById("id_fecha_seleccionada");
    const selectedRangeInput = document.getElementById("id_franja_seleccionada");
    const suggestedDateInput = document.getElementById("id_fecha_sugerida");
    const summary = document.getElementById("resumenCita");
    const modalElement = document.getElementById("modalAgendarCita");
    const confirmButton = document.getElementById("btnAceptarCita");
    const slotsBlock = document.getElementById("bloqueSlots");
    const suggestionBlock = document.getElementById("bloqueSugerencia");
    const rangesContainer = document.getElementById("contenedorFranjas");
    const suggestionInput = document.getElementById("inputSugerencia");

    let calendar = null;
    let modal = null;
    let selectedSlot = null;

    function showSummary(text, type) {
      summary.className = `alert alert-${type} mt-3 mb-0`;
      summary.textContent = text;
    }

    function resetSelector() {
      selectedSlot = null;
      calendar = SelectorFechaTutoria.limpiarSelector({
        calendario: calendar,
        contenedorFranjas: rangesContainer,
        botonConfirmar: confirmButton,
      });
      slotInput.value = "";
      selectedDateInput.value = "";
      selectedRangeInput.value = "";
      suggestedDateInput.value = "";
    }

    openButton.addEventListener("click", async function () {
      modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      resetSelector();

      try {
        const slots = await SelectorFechaTutoria.consultarHorariosTutor(tutorId);
        if (slots.length) {
          slotsBlock.style.display = "block";
          suggestionBlock.style.display = "none";
          calendar = SelectorFechaTutoria.crearCalendario({
            elemento: "#calendarioContainer",
            slots,
            alCambiarFecha(date) {
              SelectorFechaTutoria.cargarFranjas({
                tutorId,
                fecha: date,
                contenedor: rangesContainer,
                botonConfirmar: confirmButton,
                prefijoId: "edicion-franja",
                alSeleccionar(selection) {
                  selectedSlot = selection;
                },
              });
            },
          });
        } else {
          slotsBlock.style.display = "none";
          suggestionBlock.style.display = "block";
          SelectorFechaTutoria.inicializarFechaSugerida(suggestionInput);
          confirmButton.disabled = false;
        }
        modal.show();
      } catch (error) {
        console.error("No se pudieron consultar los horarios del tutor.", error);
        showSummary("No se pudieron consultar los horarios. Inténtalo de nuevo.", "danger");
      }
    });

    confirmButton.addEventListener("click", function () {
      if (slotsBlock.style.display === "block") {
        if (!selectedSlot) return;
        slotInput.value = selectedSlot.horarioId;
        selectedDateInput.value = selectedSlot.fecha;
        selectedRangeInput.value = selectedSlot.fechaHora;
        suggestedDateInput.value = "";
        dateInput.value = selectedSlot.fechaHora.slice(0, 16);
        showSummary(
          `Nueva fecha: ${selectedSlot.fecha} de ${selectedSlot.horaInicio} a ${selectedSlot.horaFin}.`,
          "success",
        );
      } else {
        if (!suggestionInput.value || !SelectorFechaTutoria.validarDiaHabil(suggestionInput)) {
          suggestionInput.reportValidity();
          return;
        }
        slotInput.value = "";
        selectedDateInput.value = "";
        selectedRangeInput.value = "";
        suggestedDateInput.value = suggestionInput.value;
        dateInput.value = suggestionInput.value;
        showSummary(`Nueva fecha sugerida: ${suggestionInput.value}.`, "warning");
      }
      modal.hide();
    });

    if (dateInput.value && (slotInput.value || suggestedDateInput.value)) {
      showSummary(`Nueva fecha seleccionada: ${dateInput.value}.`, "info");
    }
  });
})();