(() => {
    const display = document.getElementById("cubiculo-lectura");
    const form = document.getElementById("editar-cubiculo");
    const edit = document.getElementById("editar-cubiculo-button");
    if (!form || !edit) return;

    const input = form.querySelector('[name="cubiculo"]');
    const original = form.dataset.original;
    input.classList.add("form-control-sm");
    const focusInput = () => {
        input.focus();
        input.select();
    };
    const cancel = () => {
        input.value = original;
        document.getElementById("cubiculo-errores").hidden = true;
        form.hidden = true;
        display.hidden = false;
        edit.focus();
    };

    edit.addEventListener("click", () => {
        display.hidden = true;
        form.hidden = false;
        focusInput();
    });
    document.getElementById("cancelar-cubiculo").addEventListener("click", cancel);
    input.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            event.preventDefault();
            cancel();
        }
    });
    if (!form.hidden) focusInput();
})();
