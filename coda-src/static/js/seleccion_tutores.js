/* La selección vive fuera de las filas paginadas de DataTables. */
$(function () {
    const element = document.getElementById("tabla-tutores");
    if (!element) return;
    const selected = new Set();
    const all = document.getElementById("seleccionar-tutores");
    const form = document.getElementById("acciones-tutores");
    const actions = document.getElementById("acciones-tutores-button");
    const summary = document.getElementById("seleccion-tutores-resumen");
    const error = document.getElementById("seleccion-tutores-error");
    let busy = false;
    const table = $(element).DataTable({
        language: {
            search: "Buscar:", lengthMenu: "Mostrar _MENU_ entradas",
            info: "Mostrando _START_ a _END_ de _TOTAL_ entradas",
            infoEmpty: "Mostrando 0 entradas", infoFiltered: "(filtrado de _MAX_ entradas totales)",
            emptyTable: "No hay tutores disponibles", zeroRecords: "No se encontraron coincidencias",
            paginate: {first: "Primero", last: "Último", next: "Siguiente", previous: "Anterior"}
        },
        pageLength: 10,
        lengthMenu: [5, 10, 25, 50],
        order: element.dataset.ordenNombre === "true" ? [[2, "asc"]] : [],
        columnDefs: [{targets: 0, orderable: false, searchable: false}]
    });
    const filteredIds = () => table.rows({search: "applied", page: "all"}).nodes().toArray()
        .map(row => row.querySelector("[data-tutor-id]").dataset.tutorId);
    function sync() {
        const ids = filteredIds();
        const count = ids.filter(id => selected.has(id)).length;
        all.disabled = ids.length === 0;
        all.checked = ids.length > 0 && count === ids.length;
        all.indeterminate = count > 0 && count < ids.length;
        table.rows().nodes().toArray().forEach(row => {
            const checkbox = row.querySelector("[data-tutor-id]");
            checkbox.checked = selected.has(checkbox.dataset.tutorId);
        });
        actions.disabled = busy || selected.size === 0;
        actions.textContent = busy ? "Generando PDF…" : `Acciones (${selected.size})`;
        const outside = selected.size - count;
        summary.textContent = `${selected.size} seleccionados` +
            (outside ? `; ${outside} fuera de la búsqueda` : "");
    }
    $(element).on("change", "[data-tutor-id]", function () {
        if (this.checked) selected.add(this.dataset.tutorId);
        else selected.delete(this.dataset.tutorId);
        sync();
    });
    all.addEventListener("change", () => {
        filteredIds().forEach(id => all.checked ? selected.add(id) : selected.delete(id));
        sync();
    });
    table.on("draw", sync);
    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (busy || selected.size === 0) return;
        const data = new FormData(form);
        selected.forEach(id => data.append("tutores", id));
        busy = true;
        error.hidden = true;
        sync();
        try {
            const response = await fetch(form.action, {method: "POST", body: data});
            if (!response.ok || !response.headers.get("content-type")?.includes("application/pdf")) {
                throw new Error("No se pudo generar el PDF. Comprueba tu sesión y que los tutores seleccionados sigan disponibles.");
            }
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement("a");
            link.href = url;
            link.download = "qr-tutores.pdf";
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 60000);
        } catch (failure) {
            error.textContent = failure.message;
            error.hidden = false;
        } finally {
            busy = false;
            sync();
        }
    });
    sync();
});
