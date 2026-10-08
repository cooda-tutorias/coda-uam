document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('sol-form');
    const dialog = document.getElementById('sol-validation-dialog');
    const dialogPanel = dialog?.querySelector('[role="dialog"]');
    const errorsList = document.getElementById('sol-validation-list');
    const closeButton = document.getElementById('sol-validation-close');
    const stayButton = document.getElementById('sol-validation-stay');
    const firstFieldButton = document.getElementById('sol-validation-first');
    const serverErrors = document.getElementById('sol-server-validation-errors');

    if (!form || !dialog || !errorsList) return;

    const labels = {
        tema: 'Temas a tratar',
        otro_tema: 'Especifica el tema',
        fecha: 'Fecha y hora',
        fecha_sugerida: 'Fecha y hora',
        horario_tutor: 'Fecha y hora',
        descripcion: 'Información adicional',
    };
    const dateFields = new Set(['fecha', 'fecha_sugerida', 'horario_tutor', 'fecha_seleccionada', 'franja_seleccionada']);
    let currentErrors = [];
    let previousFocus = null;
    let previousBodyOverflow = '';

    function targetFor(fieldName) {
        if (dateFields.has(fieldName)) return document.getElementById('btnAbrirModalCita');
        if (fieldName === 'tema') return form.querySelector('input[name="tema"]');
        if (fieldName === 'otro_tema') return document.getElementById('id_otro_tema');
        return form.elements.namedItem(fieldName);
    }

    function fieldLabel(fieldName, control) {
        if (labels[fieldName]) return labels[fieldName];
        const fieldset = control?.closest('fieldset');
        const legend = fieldset?.querySelector('legend');
        if (legend) return legend.textContent.trim();
        return control?.labels?.[0]?.textContent.trim() || fieldName || 'Campo requerido';
    }

    function localizedMessage(message) {
        if (/required|obligatorio/i.test(message)) return 'Completa este campo.';
        return message || 'Revisa este campo.';
    }

    function closeDialog(restoreFocus) {
        dialog.classList.remove('is-open');
        dialog.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = previousBodyOverflow;
        if (restoreFocus && previousFocus?.focus) previousFocus.focus();
    }

    function focusField(error) {
        closeDialog(false);
        if (!error?.target) return;
        error.target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        error.target.focus({ preventScroll: true });
    }

    function showDialog(errors) {
        currentErrors = errors
            .filter(error => error.target)
            .sort(function (first, second) {
                const position = first.target.compareDocumentPosition(second.target);
                if (position & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
                if (position & Node.DOCUMENT_POSITION_PRECEDING) return 1;
                return 0;
            });
        errorsList.replaceChildren();
        currentErrors.forEach(function (error) {
            const item = document.createElement('li');
            const button = document.createElement('button');
            const fieldName = document.createElement('span');
            const message = document.createElement('span');

            button.type = 'button';
            button.className = 'sol-validation-item';
            fieldName.className = 'sol-validation-field';
            fieldName.textContent = error.label;
            message.className = 'sol-validation-message';
            message.textContent = error.message;
            button.append(fieldName, message);
            button.addEventListener('click', function () { focusField(error); });
            item.appendChild(button);
            errorsList.appendChild(item);
        });

        if (!currentErrors.length) return;
        previousFocus = document.activeElement;
        previousBodyOverflow = document.body.style.overflow;
        dialog.classList.add('is-open');
        dialog.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        closeButton.focus();
    }

    function collectClientErrors() {
        const invalidControls = Array.from(
            form.querySelectorAll('input:invalid, select:invalid, textarea:invalid')
        ).filter(control => !control.disabled && control.type !== 'hidden');
        const errorsByField = new Map();

        invalidControls.forEach(function (control) {
            const key = control.name || control.id;
            if (!key || errorsByField.has(key)) return;
            errorsByField.set(key, {
                label: fieldLabel(key, control),
                message: control.validity.valueMissing
                    ? 'Completa este campo.'
                    : 'Revisa el valor ingresado.',
                target: targetFor(key) || control,
            });
        });

        const scheduleFields = ['horario_tutor', 'fecha_sugerida', 'fecha_seleccionada', 'franja_seleccionada'];
        const scheduleSelected = scheduleFields.some(function (name) {
            const field = form.elements.namedItem(name);
            return field && field.value.trim();
        });
        if (!scheduleSelected && !errorsByField.has('fecha')) {
            errorsByField.set('fecha', {
                label: labels.fecha,
                message: 'Selecciona un horario disponible o sugiere una fecha.',
                target: targetFor('fecha'),
            });
        }

        return Array.from(errorsByField.values());
    }

    form.addEventListener('submit', function (event) {
        const errors = collectClientErrors();
        if (form.checkValidity() && !errors.some(error => error.label === labels.fecha)) return;
        event.preventDefault();
        showDialog(errors);
    });

    closeButton.addEventListener('click', function () { closeDialog(true); });
    stayButton.addEventListener('click', function () { closeDialog(true); });
    firstFieldButton.addEventListener('click', function () {
        focusField(currentErrors[0]);
    });
    dialog.addEventListener('click', function (event) {
        if (event.target === dialog) closeDialog(true);
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && dialog.classList.contains('is-open')) {
            closeDialog(true);
        }
    });

    if (serverErrors) {
        const errors = Array.from(serverErrors.querySelectorAll('[data-validation-field]')).map(function (node) {
            const fieldName = node.dataset.validationField;
            const target = targetFor(fieldName);
            return {
                label: fieldLabel(fieldName, target),
                message: localizedMessage(node.textContent.trim()),
                target: target,
            };
        });
        if (errors.length) showDialog(errors);
    }
});